from starlette.background import BackgroundTask

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

            async def log_response():
                try:
                    prompt = form_data.get("prompt")
                    if not prompt and isinstance(form_data.get("messages"), list):
                        prompt = form_data["messages"][-1].get("content", "-")

                    answer = ""
                    while not q.empty():
                        data = await q.get()
                        if isinstance(data, dict) and "content" in data:
                            answer += data["content"]
                    write_log(user.name, prompt or "-", answer)
                except Exception as e:
                    print("\U0001F6D1 Logging to Google Sheet failed (stream):", e)

            async def background():
                try:
                    del sio.handlers["/"][channel]
                except Exception:
                    pass

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                background=BackgroundTask(log_response)
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
