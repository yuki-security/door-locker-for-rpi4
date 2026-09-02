#!/usr/bin/env python3
"""Register a SwitchBot Open API webhook for physical lock events."""
import os
import time
import uuid
import hmac
import hashlib
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SWITCHBOT_TOKEN")
SECRET = os.getenv("SWITCHBOT_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or (
    os.getenv("PUBLIC_BASE_URL", "").rstrip("/") + "/switchbot-webhook"
)


def setup_webhook():
    if not TOKEN or not SECRET or not WEBHOOK_URL.endswith("/switchbot-webhook"):
        raise SystemExit("SWITCHBOT_TOKEN / SWITCHBOT_SECRET / WEBHOOK_URL (or PUBLIC_BASE_URL) を .env に設定してください。")

    nonce = str(uuid.uuid4())
    timestamp = str(int(round(time.time() * 1000)))
    string_to_sign = f"{TOKEN}{timestamp}{nonce}".encode("utf-8")
    sign = base64.b64encode(
        hmac.new(SECRET.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256).digest()
    ).decode()
    headers = {
        "Authorization": TOKEN,
        "t": timestamp,
        "sign": sign,
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }
    payload = {
        "action": "setupWebhook",
        "url": WEBHOOK_URL,
        "deviceList": "ALL",
    }
    response = requests.post(
        "https://api.switchbot.net/v1.1/webhook/setupWebhook",
        headers=headers,
        json=payload,
        timeout=15,
    )
    print("Response:", response.json())


if __name__ == "__main__":
    setup_webhook()
