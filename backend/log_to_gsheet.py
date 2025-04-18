import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

def write_log(user, question, answer):
    try:
        secret_path = "/etc/secrets/GSPREAD_KEY"  # หรือให้ตั้งเป็น env var ก็ได้
        with open(secret_path) as f:
            credentials_dict = json.load(f)

        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive',
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        gc = gspread.authorize(credentials)
        sheet = gc.open("Lexza GPT Log").sheet1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, user, question, answer])

        print("✅ GSheet log success")

    except Exception as e:
        print("🛑 GSheet log error:", e)
