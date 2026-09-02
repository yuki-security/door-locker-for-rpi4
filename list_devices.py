#!/usr/bin/env python3
"""List SwitchBot devices so you can copy DEVICE_ID / HUB_DEVICE_ID into .env."""
import os
import time
import uuid
import hmac
import hashlib
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("SWITCHBOT_TOKEN")
secret = os.getenv("SWITCHBOT_SECRET")
if not token or not secret:
    raise SystemExit("SWITCHBOT_TOKEN と SWITCHBOT_SECRET を .env に設定してください。")

nonce = str(uuid.uuid4())
timestamp = str(int(round(time.time() * 1000)))
sign = base64.b64encode(
    hmac.new(secret.encode(), f"{token}{timestamp}{nonce}".encode(), hashlib.sha256).digest()
).decode()
res = requests.get(
    "https://api.switchbot.net/v1.1/devices",
    headers={"Authorization": token, "t": timestamp, "sign": sign, "nonce": nonce},
    timeout=15,
).json()

body = res.get("body", {})
print("=== deviceList ===")
for device in body.get("deviceList", []):
    print(f"{device.get('deviceName')} ({device.get('deviceType')}): {device.get('deviceId')}")
print("=== infraredRemoteList ===")
for device in body.get("infraredRemoteList", []):
    print(f"{device.get('deviceName')} ({device.get('remoteType')}): {device.get('deviceId')}")
