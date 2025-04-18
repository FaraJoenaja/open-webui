import gspread
from oauth2client.service_account import ServiceAccountCredentials
import sys
from datetime import datetime
import os
import json

# โหลด credentials จาก Secret File
secret_path = "/etc/secrets/GSPREAD_KEY"
with open(secret_path) as f:
    credentials_dict = json.load(f)

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
gc = gspread.authorize(credentials)

sheet = gc.open("Lexza GPT Log").sheet1

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
user = "admin"
question = sys.argv[1]
answer = sys.argv[2]

sheet.append_row([timestamp, user, question, answer])
print("✅ บันทึกเรียบร้อยแล้ว")
