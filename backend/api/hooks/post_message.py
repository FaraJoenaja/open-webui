# backend/api/hooks/post_message.py

import subprocess
import sys

def handle(message, user, chat_id):
    try:
        subprocess.run([
            "python3",
            "/app/backend/log_to_gsheet.py",
            message,
            user
        ])
    except Exception as e:
        print("🔥 Failed to log to Google Sheet:", e)
