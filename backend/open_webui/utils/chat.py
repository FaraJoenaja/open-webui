import time
import logging
import sys
import uuid
from typing import Any
import json
import asyncio
import inspect
import random

import backend.api.hooks.post_message as post_message

from fastapi import Request, status
from starlette.responses import Response, StreamingResponse, JSONResponse
from open_webui.models.users import UserModel
from open_webui.socket.main import (
    sio,
    get_event_call,
    get_event_emitter,
)
from open_webui.functions import generate_function_chat_completion
from open_webui.routers.openai import (
    generate_chat_completion as generate_openai_chat_completion,
)
from open_webui.routers.ollama import (
    generate_chat_completion as generate_ollama_chat_completion,
)
from open_webui.routers.pipelines import (
    process_pipeline_inlet_filter,
    process_pipeline_outlet_filter,
)
from open_webui.models.functions import Functions
from open_webui.models.models import Models
from open_webui.utils.plugin import load_function_module_by_id
from open_webui.utils.models import get_all_models, check_model_access
from open_webui.utils.payload import convert_payload_openai_to_ollama
from open_webui.utils.response import (
    convert_response_ollama_to_openai,
    convert_streaming_response_ollama_to_openai,
)
from open_webui.utils.filter import (
    get_sorted_filter_ids,
    process_filter_functions,
)
from open_webui.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL, BYPASS_MODEL_ACCESS_CONTROL

# ✅ เพิ่มส่วนนี้
from backend.log_to_gsheet import write_log

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


async def generate_direct_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    models: dict,
):
    log.info("generate_direct_chat_completion")

    metadata = form_data.pop("metadata", {})
    user_id = metadata.get("user_id")
    session_id = metadata.get("session_id")
    request_id = str(uuid.uuid4())

    event_caller = get_event_call(metadata)
    channel = f"{user_id}:{session_id}:{request_id}"

    if form_data.get("stream"):
        q = asyncio.Queue()

        async def message_listener(sid, data):
            await q.put(data)

        sio.on(channel, message_listener)

        res = await event_caller({
            "type": "request:chat:completion",
            "data": {
                "form_data": form_data,
                "model": models[form_data["model"]],
                "channel": channel,
                "session_id": session_id,
            },
        })

        log.info(f"res: {res}")

        if res.get("status", False):
            async def event_generator():
                nonlocal q
                try:
                    while True:
                        data = await q.get()
                        if isinstance(data, dict):
                            if "done" in data and data["done"]:
                                break
                            yield f"data: {json.dumps(data)}\n\n"
                        elif isinstance(data, str):
                            yield data
                except Exception as e:
                    log.debug(f"Error in event generator: {e}")

            async def background():
                try:
                    del sio.handlers["/"][channel]
                except Exception:
                    pass

            return StreamingResponse(
                event_generator(), media_type="text/event-stream", background=background
            )
        else:
            raise Exception(str(res))
    else:
        res = await event_caller({
            "type": "request:chat:completion",
            "data": {
                "form_data": form_data,
                "model": models[form_data["model"]],
                "channel": channel,
                "session_id": session_id,
            },
        })

        if "error" in res and res["error"]:
            raise Exception(res["error"])

        return res


async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    bypass_filter: bool = False,
):
    log.debug(f"generate_chat_completion: {form_data}")
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    if hasattr(request.state, "metadata"):
        form_data["metadata"] = {
            **form_data.get("metadata", {}),
            **request.state.metadata,
        }

    if getattr(request.state, "direct", False) and hasattr(request.state, "model"):
        models = {
            request.state.model["id"]: request.state.model,
        }
        log.debug(f"direct connection to model: {models}")
    else:
        models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise Exception("Model not found")

    model = models[model_id]

    if getattr(request.state, "direct", False):
        return await generate_direct_chat_completion(
            request, form_data, user=user, models=models
        )

    if not bypass_filter and user.role == "user":
        try:
            check_model_access(user, model)
        except Exception as e:
            raise e

    if model.get("owned_by") == "arena":
        model_ids = model.get("info", {}).get("meta", {}).get("model_ids")
        filter_mode = model.get("info", {}).get("meta", {}).get("filter_mode")

        if model_ids and filter_mode == "exclude":
            model_ids = [
                m["id"]
                for m in list(request.app.state.MODELS.values())
                if m.get("owned_by") != "arena" and m["id"] not in model_ids
            ]

        selected_model_id = random.choice(model_ids) if model_ids else random.choice(
            [m["id"] for m in list(request.app.state.MODELS.values()) if m.get("owned_by") != "arena"]
        )

        form_data["model"] = selected_model_id

        if form_data.get("stream") is True:
            async def stream_wrapper(stream):
                yield f"data: {json.dumps({'selected_model_id': selected_model_id})}\n\n"
                async for chunk in stream:
                    yield chunk

            response = await generate_chat_completion(
                request, form_data, user, bypass_filter=True
            )
            return StreamingResponse(
                stream_wrapper(response.body_iterator),
                media_type="text/event-stream",
                background=response.background,
            )
        else:
            return {
                **(await generate_chat_completion(
                    request, form_data, user, bypass_filter=True
                )),
                "selected_model_id": selected_model_id,
            }

    if model.get("pipe"):
        return await generate_function_chat_completion(
            request, form_data, user=user, models=models
        )

    if model.get("owned_by") == "ollama":
        form_data = convert_payload_openai_to_ollama(form_data)
        response = await generate_ollama_chat_completion(
            request=request,
            form_data=form_data,
            user=user,
            bypass_filter=bypass_filter,
        )
        if form_data.get("stream"):
            response.headers["content-type"] = "text/event-stream"
            return StreamingResponse(
                convert_streaming_response_ollama_to_openai(response),
                headers=dict(response.headers),
                background=response.background,
            )
        else:
            return convert_response_ollama_to_openai(response)

    # ✅ ตรงนี้คือการเรียก openai ปกติ และเพิ่ม write_log
    res = await generate_openai_chat_completion(
        request=request,
        form_data=form_data,
        user=user,
        bypass_filter=bypass_filter,
    )

    try:
        write_log(user.name, form_data.get("prompt", "-"), str(res))
    except Exception as e:
        print("🛑 Logging to Google Sheet failed:", e)

    return res


chat_completion = generate_chat_completion
