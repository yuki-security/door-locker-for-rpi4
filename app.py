import os
import re
import time
import hmac
import uuid
import hashlib
import base64
import logging
from datetime import datetime, timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler

import requests
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, Response, abort, render_template, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    ButtonsTemplate,
    DatetimePickerAction,
    FlexSendMessage,
    FollowEvent,
    MessageEvent,
    PostbackAction,
    PostbackEvent,
    TemplateSendMessage,
    TextMessage,
    TextSendMessage,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

LOG_FILE = os.path.join(BASE_DIR, "switchbot_bot.log")
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger = logging.getLogger("SwitchBotLogger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(file_handler)
logger.info("=== Door Locker (SwitchBot LINE Bot) started ===")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
BOT_BASIC_ID = os.getenv("BOT_BASIC_ID", "@YOUR_BOT_BASIC_ID")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "YOUR_LINE_USER_ID")
SECRET_DASHBOARD_KEY = os.getenv("SECRET_DASHBOARD_KEY", "")
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
TOTP_SECRET = os.getenv("TOTP_SECRET", "")
SWITCHBOT_TOKEN = os.getenv("SWITCHBOT_TOKEN", "")
SWITCHBOT_SECRET = os.getenv("SWITCHBOT_SECRET", "")
DEVICE_ID = os.getenv("DEVICE_ID", "")
HUB_DEVICE_ID = os.getenv("HUB_DEVICE_ID", "")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
scheduler = BackgroundScheduler()
scheduler.start()

# user_id -> expiration datetime or None (permanent)
authenticated_users = {}
# user_id -> {count, blocked_until}
failed_attempts = {}


def require_dashboard_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not DASHBOARD_PASSWORD:
            return view(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.username != DASHBOARD_USER or auth.password != DASHBOARD_PASSWORD:
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Dashboard"'},
            )
        return view(*args, **kwargs)

    return wrapped


def is_user_authenticated(user_id):
    if user_id not in authenticated_users:
        return False
    expiry = authenticated_users[user_id]
    if expiry is not None and datetime.now() > expiry:
        del authenticated_users[user_id]
        logger.info("Temporary access EXPIRED for user [%s]", user_id)
        return False
    return True


def record_failed_attempt(user_id):
    now = datetime.now()
    data = failed_attempts.get(user_id, {"count": 0, "blocked_until": None})
    if data["blocked_until"] and now < data["blocked_until"]:
        return True
    data["count"] += 1
    if data["count"] >= 3:
        data["blocked_until"] = now + timedelta(minutes=15)
        data["count"] = 0
        failed_attempts[user_id] = data
        logger.warning(
            "SECURITY ALERT: User [%s] BLOCKED for 15m due to repeated failures.",
            user_id,
        )
        return True
    failed_attempts[user_id] = data
    return False


def is_user_blocked(user_id):
    data = failed_attempts.get(user_id)
    if not data or not data["blocked_until"]:
        return False
    if datetime.now() > data["blocked_until"]:
        failed_attempts[user_id]["blocked_until"] = None
        return False
    return True


def notify_admin(message_text):
    if ADMIN_USER_ID and ADMIN_USER_ID != "YOUR_LINE_USER_ID":
        try:
            line_bot_api.push_message(ADMIN_USER_ID, TextSendMessage(text=message_text))
        except Exception as exc:
            logger.error("Failed to send admin notification: %s", exc)


def get_current_dynamic_key(offset=0):
    time_window = int(time.time() // 1800) + offset
    msg = f"{TOTP_SECRET}:{time_window}".encode("utf-8")
    key_hash = hmac.new(TOTP_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"KEY_{key_hash[:8].upper()}"


def switchbot_headers():
    nonce = str(uuid.uuid4())
    timestamp = str(int(round(time.time() * 1000)))
    string_to_sign = f"{SWITCHBOT_TOKEN}{timestamp}{nonce}".encode("utf-8")
    secret = SWITCHBOT_SECRET.encode("utf-8")
    sign = base64.b64encode(hmac.new(secret, string_to_sign, digestmod=hashlib.sha256).digest())
    return {
        "Authorization": SWITCHBOT_TOKEN,
        "t": timestamp,
        "sign": str(sign, "utf-8"),
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }


def operate_switchbot_lock(command_type, user_info="System"):
    url = f"https://api.switchbot.net/v1.1/devices/{DEVICE_ID}/commands"
    payload = {
        "command": command_type,
        "parameter": "default",
        "commandType": "command",
    }
    try:
        response = requests.post(url, headers=switchbot_headers(), json=payload, timeout=15)
        res_json = response.json()
        logger.info(
            "SwitchBot Command [%s] Executed by [%s] - Status: %s",
            command_type,
            user_info,
            res_json.get("statusCode"),
        )
        action_str = "🔓 開錠" if command_type == "unlock" else "🔒 施錠"
        notify_admin(
            f"🔔【操作検知】\n{action_str}が実行されました。\n実行者: {user_info}\n時刻: {datetime.now().strftime('%H:%M:%S')}"
        )
        return res_json
    except Exception as exc:
        logger.error("SwitchBot API Error [%s] by [%s]: %s", command_type, user_info, exc)
        return {}


def get_meter_status():
    if not HUB_DEVICE_ID:
        return "⚠ HUB_DEVICE_ID が設定されていません。"
    url = f"https://api.switchbot.net/v1.1/devices/{HUB_DEVICE_ID}/status"
    try:
        res = requests.get(url, headers=switchbot_headers(), timeout=15).json()
        body = res.get("body", {})
        temp = body.get("temperature")
        humidity = body.get("humidity")
        if temp is not None and humidity is not None:
            return f"🌡 現在のお部屋の状況\n・温度: {temp} ℃\n・湿度: {humidity} %"
        return "⚠ 温湿度データの取得に失敗しました。"
    except Exception as exc:
        logger.error("Meter API Error: %s", exc)
        return "⚠ センサーとの通信エラーが発生しました。"


@app.route("/qr", methods=["GET"])
def view_qr():
    current_key = get_current_dynamic_key()
    line_url = f"https://line.me/R/oaMessage/{BOT_BASIC_ID}/?{current_key}"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ドアロックくん - 認証QRコード</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <style>
    body {{ font-family: -apple-system, sans-serif; text-align: center; background: #0f172a; color: white; padding: 40px 20px; }}
    .card {{ background: #1e293b; padding: 30px; border-radius: 16px; display: inline-block; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
    #qrcode {{ display: flex; justify-content: center; margin: 20px 0; background: white; padding: 16px; border-radius: 12px; }}
    .key-text {{ font-family: monospace; font-size: 18px; color: #38bdf8; margin-top: 10px; }}
    .info {{ color: #94a3b8; font-size: 14px; margin-top: 15px; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>🔑 ドアロックくん 認証用QRコード</h2>
    <p class="info">LINEのカメラで読み取って申請してください</p>
    <div id="qrcode"></div>
    <div class="key-text">CURRENT KEY: {current_key}</div>
    <p class="info">※このQRコードは30分ごとに自動変更されます</p>
  </div>
  <script>
    new QRCode(document.getElementById("qrcode"), {{ text: "{line_url}", width: 220, height: 220 }});
    setTimeout(() => location.reload(), 30000);
  </script>
</body>
</html>
"""


@app.route("/logs", methods=["GET"])
@require_dashboard_auth
def view_logs():
    key = request.args.get("key", "")
    if not SECRET_DASHBOARD_KEY or key != SECRET_DASHBOARD_KEY:
        return "403 Forbidden: Invalid Access Key", 403

    parsed_logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as handle:
            for line in reversed(handle.readlines()[-100:]):
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"\[(.*?)\] (.*?): (.*)", line)
                if match:
                    parsed_logs.append(
                        {"time": match.group(1), "level": match.group(2), "msg": match.group(3)}
                    )
                else:
                    parsed_logs.append({"time": "-", "level": "INFO", "msg": line})

    active_uids = [uid for uid in list(authenticated_users.keys()) if is_user_authenticated(uid)]
    return render_template("logs.html", logs=parsed_logs, authenticated_users=active_uids)


@app.route("/switchbot-webhook", methods=["POST"])
def switchbot_webhook():
    data = request.get_json(silent=True) or {}
    context = data.get("context", {})
    device_mac = context.get("deviceMac", "")
    if device_mac and DEVICE_ID and device_mac.upper() != DEVICE_ID.upper():
        return "OK", 200

    lock_state = context.get("lockState", "")
    event_type = context.get("eventType", "")
    action_str = "🔓 開錠" if lock_state == "UNLOCKED" else "🔒 施錠"
    source_map = {
        "KEYPAD": "顔認証/キーパッド操作",
        "MANUAL": "手動（ツマミ操作）",
        "APP": "SwitchBot公式アプリ",
        "COMMAND": "API / LINE Bot経由",
    }
    operator = source_map.get(event_type, f"外部操作 ({event_type})")
    logger.info("Physical Operation Detected: [%s] via [%s]", action_str, operator)
    if event_type and event_type != "COMMAND":
        notify_admin(
            f"🔔【操作検知】\n{action_str}が実行されました。\n操作方法: {operator}\n時刻: {datetime.now().strftime('%H:%M:%S')}"
        )
    return "OK", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE Signature received")
        abort(400)
    return "OK"


@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    try:
        user_name = line_bot_api.get_profile(user_id).display_name
    except Exception:
        user_name = "不明なユーザー"
    logger.info("New Follower Added: %s (%s)", user_name, user_id)
    welcome_text = (
        "友だち追加ありがとうございます！\n\n"
        f"👤 あなたのユーザー名: {user_name}\n"
        f"🔑 あなたのマイID:\n{user_id}\n\n"
        "※鍵を利用するには設置されている専用QRコードを読み取って利用申請を行ってください。"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))
    notify_admin(f"👤 新しい友だち追加がありました！\n・名前: {user_name}\n・ユーザーID:\n{user_id}")


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    try:
        user_name = line_bot_api.get_profile(user_id).display_name
    except Exception:
        user_name = user_id

    if is_user_blocked(user_id):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="🚨 誤った操作が連続で検出されたため、一時的にセキュリティロックがかかっています。\n15分後にやり直してください。"
            ),
        )
        return

    if user_text == "マイID":
        logger.info("User [%s] requested My ID", user_name)
        flex_content = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "👤 マイID確認", "weight": "bold", "size": "md", "color": "#38bdf8"},
                    {"type": "text", "text": f"ユーザー名: {user_name}", "size": "xs", "color": "#94a3b8", "margin": "xs"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": user_id, "size": "xs", "wrap": True, "margin": "md", "color": "#f8fafc"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {"type": "message", "label": "📋 IDをトークに送信", "text": user_id},
                        "style": "primary",
                        "color": "#0284c7",
                    }
                ],
            },
        }
        line_bot_api.reply_message(
            event.reply_token, FlexSendMessage(alt_text="マイIDのお知らせ", contents=flex_content)
        )
        return

    if user_text == AUTH_SECRET_KEY or user_text.startswith("KEY_"):
        current_key = get_current_dynamic_key()
        prev_key = get_current_dynamic_key(offset=-1)
        if user_text == AUTH_SECRET_KEY or user_text in (current_key, prev_key):
            logger.info("User [%s] (%s) requested AUTH with valid key", user_name, user_id)
            if is_user_authenticated(user_id):
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="すでに登録済みです。「開けて」と送信してください。"),
                )
            elif user_id == ADMIN_USER_ID:
                authenticated_users[user_id] = None
                operate_switchbot_lock("unlock", f"ADMIN:{user_name}")
                logger.info("ADMIN [%s] Auto-Approved and Unlocked", user_name)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="👑 管理者として認証されました！\n鍵を開けました。"),
                )
            elif ADMIN_USER_ID and ADMIN_USER_ID != "YOUR_LINE_USER_ID":
                approval_template = TemplateSendMessage(
                    alt_text="【登録申請】鍵の開錠申請",
                    template=ButtonsTemplate(
                        title="🔑 登録申請が届きました",
                        text=f"{user_name} さんからの申請。承認タイプを選択してください。",
                        actions=[
                            PostbackAction(label="⭕ 永久承認", data=f"action=approve_perm&uid={user_id}"),
                            PostbackAction(label="⏳ 2時間のみ許可", data=f"action=approve_2h&uid={user_id}"),
                            DatetimePickerAction(
                                label="📅 期限を指定",
                                data=f"action=approve_custom&uid={user_id}",
                                mode="datetime",
                            ),
                            PostbackAction(label="❌ 拒否する", data=f"action=reject&uid={user_id}"),
                        ],
                    ),
                )
                line_bot_api.push_message(ADMIN_USER_ID, approval_template)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="📩 管理者に利用申請を送信しました。\n承認されるまでお待ちください。"),
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠ 管理者IDが未設定です。管理者に連絡してください。"),
                )
        else:
            logger.warning("User [%s] submitted expired/invalid key: %s", user_name, user_text)
            if record_failed_attempt(user_id):
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="🚨 無効なキーが連続で入力されたため、15分間操作をロックしました。"),
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠ このQRコードは有効期限が切れています。\n最新のQRコードを読み直してください。"),
                )
        return

    if user_text == "開けて":
        if is_user_authenticated(user_id):
            logger.info("User [%s] requested UNLOCK -> Executing", user_name)
            operate_switchbot_lock("unlock", user_name)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔓 鍵を開けたよ！"))
        else:
            logger.warning("Unauthenticated User [%s] requested UNLOCK -> Denied", user_name)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="🔒 初回登録（承認）が必要です。\n設置されている専用QRコードを読み取ってください。"),
            )
        return

    if user_text == "閉めて":
        logger.info("User [%s] requested LOCK -> Executing", user_name)
        operate_switchbot_lock("lock", user_name)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔒 鍵を閉めたよ！"))
        return

    if user_text == "予約":
        date_picker = TemplateSendMessage(
            alt_text="時刻選択",
            template=ButtonsTemplate(
                title="開錠予約",
                text="開錠する時間を設定してください",
                actions=[DatetimePickerAction(label="⏰ 時刻を選ぶ", data="action=reserve_unlock", mode="time")],
            ),
        )
        line_bot_api.reply_message(event.reply_token, date_picker)
        return

    if user_text == "予約取消":
        try:
            scheduler.remove_job("unlock_job")
            reply_text = "✅ 開錠の予約を取り消しました！"
        except JobLookupError:
            reply_text = "現在、取り消す予約はありません。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    if user_text in ("ヘルプ", "help", "Help"):
        logger.info("User [%s] requested Help", user_name)
        help_text = (
            "📖 ドアロックくん利用ガイド\n"
            "───────────────────\n\n"
            "🔓 開けて\n・鍵を開錠します。\n※初回利用時は指定QRコードから管理者承認が必要です。\n\n"
            "🔒 閉めて\n・鍵を施錠します。\n\n"
            "🌡 室温 / 温度 / 湿度\n・ハブまたは温湿度計の値を表示します。\n\n"
            "⏰ 予約 / 予約取消\n・指定時刻の開錠予約、または予約のキャンセルを行います。\n\n"
            "👤 マイID\n・あなたのLINEユーザーIDを表示します。\n\n"
            "🔄 リセット\n・現在の登録状態を取り消します。"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))
        return

    if user_text in ("室温", "温度", "湿度", "環境"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=get_meter_status()))
        return

    if user_text == "リセット":
        if user_id in authenticated_users:
            del authenticated_users[user_id]
            logger.info("User [%s] registration removed", user_name)
            reply_text = "🔄 ユーザー登録を取り消しました。"
        else:
            reply_text = "未登録の状態です。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id

    if "action=approve" in data or "action=reject" in data:
        if user_id != ADMIN_USER_ID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠ 管理者のみが操作できます。"))
            return
        params = dict(param.split("=", 1) for param in data.split("&"))
        target_uid = params.get("uid")
        try:
            target_name = line_bot_api.get_profile(target_uid).display_name
        except Exception:
            target_name = target_uid

        if data.startswith("action=approve_perm"):
            authenticated_users[target_uid] = None
            operate_switchbot_lock("unlock", f"Approved (Perm) by Admin for {target_name}")
            logger.info("Admin Approved (Perm) user [%s] (%s)", target_name, target_uid)
            line_bot_api.push_message(
                target_uid,
                TextSendMessage(text="🎉 管理者に【無期限承認】されました！\n鍵を開けました。次回からは「開けて」で開錠できます。"),
            )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ {target_name} さんを無期限承認して鍵を開けました。"),
            )
        elif data.startswith("action=approve_2h"):
            authenticated_users[target_uid] = datetime.now() + timedelta(hours=2)
            operate_switchbot_lock("unlock", f"Approved (2H) by Admin for {target_name}")
            logger.info("Admin Approved (2H) user [%s] (%s)", target_name, target_uid)
            line_bot_api.push_message(
                target_uid,
                TextSendMessage(text="⏳ 管理者に【2時間限定】で承認されました！\n鍵を開けました。2時間後に権限は自動解除されます。"),
            )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"⏱ {target_name} さんを2時間限定で承認し、鍵を開けました。"),
            )
        elif data.startswith("action=approve_custom"):
            selected_datetime_str = (event.postback.params or {}).get("datetime")
            if selected_datetime_str:
                expiration_dt = datetime.strptime(selected_datetime_str, "%Y-%m-%dT%H:%M")
                if expiration_dt <= datetime.now():
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="⚠ 過去の日時は設定できません。未来の日時を選んでください。"),
                    )
                    return
                authenticated_users[target_uid] = expiration_dt
                operate_switchbot_lock(
                    "unlock",
                    f"Approved (Until {selected_datetime_str}) by Admin for {target_name}",
                )
                time_formatted = expiration_dt.strftime("%Y年%m月%d日 %H:%M")
                line_bot_api.push_message(
                    target_uid,
                    TextSendMessage(
                        text=f"📅 管理者に【期間限定】で承認されました！\n鍵を開けました。\n※利用期限: {time_formatted} まで有効です。"
                    ),
                )
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"📅 {target_name} さんを {time_formatted} まで限定で承認し、鍵を開けました。"),
                )
        elif data.startswith("action=reject"):
            logger.info("Admin Rejected user [%s] (%s)", target_name, target_uid)
            line_bot_api.push_message(target_uid, TextSendMessage(text="❌ 登録申請が拒否されました。"))
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"🚫 {target_name} さんの申請を拒否しました。"),
            )
        return

    if data == "action=reserve_unlock":
        time_str = event.postback.params["time"]
        hour, minute = map(int, time_str.split(":"))
        try:
            scheduler.add_job(
                operate_switchbot_lock,
                "cron",
                hour=hour,
                minute=minute,
                args=["unlock", f"Scheduled Reservation by {user_id}"],
                id="unlock_job",
                replace_existing=True,
            )
            logger.info("Unlock Reservation set at %s by %s", time_str, user_id)
            reply_text = f"✅ {time_str}に開錠を予約しました！"
        except Exception:
            reply_text = "予約処理に失敗しました。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT)
