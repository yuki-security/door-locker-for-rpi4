#!/usr/bin/env python3
"""Upload assets/施錠する.png as the LINE rich menu (tap sends 「閉めて」)."""
from __future__ import annotations

import io
import os
import sys

from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import MessageAction, RichMenu, RichMenuArea, RichMenuBounds, RichMenuSize
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

LINE_SIZES = (
    (2500, 1686),
    (2500, 843),
    (1200, 810),
    (1200, 405),
    (800, 540),
    (800, 270),
)
RICH_MENU_NAME = "door-locker-lock"
DEFAULT_IMAGE = os.path.join(BASE_DIR, "assets", "施錠する.png")
MAX_BYTES = 1024 * 1024


def find_image() -> str:
    candidates = [
        os.getenv("RICH_MENU_IMAGE", ""),
        DEFAULT_IMAGE,
        os.path.join(BASE_DIR, "施錠する.png"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise SystemExit(
        "施錠する.png が見つかりません。assets/施錠する.png に置いてから再実行してください。"
    )


def pick_target_size(width: int, height: int) -> tuple[int, int]:
    ratio = width / max(height, 1)
    # 横長ならコンパクト（843）、正方形〜縦長ならフルサイズ（1686）
    return (2500, 843) if ratio >= 1.6 else (2500, 1686)


def prepare_image(src_path: str) -> tuple[bytes, str, tuple[int, int]]:
    image = Image.open(src_path).convert("RGBA")
    target_w, target_h = pick_target_size(*image.size)
    src_ratio = image.width / image.height
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_h = image.height
        new_w = int(new_h * dst_ratio)
        left = (image.width - new_w) // 2
        image = image.crop((left, 0, left + new_w, new_h))
    else:
        new_w = image.width
        new_h = int(new_w / dst_ratio)
        top = (image.height - new_h) // 2
        image = image.crop((0, top, new_w, top + new_h))
    image = image.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def encode(fmt: str, **kwargs) -> bytes:
        buf = io.BytesIO()
        if fmt == "JPEG":
            image.convert("RGB").save(buf, format="JPEG", quality=kwargs.get("quality", 85), optimize=True)
        else:
            image.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    png = encode("PNG")
    if len(png) <= MAX_BYTES:
        return png, "image/png", (target_w, target_h)
    for quality in (85, 75, 65, 55):
        jpeg = encode("JPEG", quality=quality)
        if len(jpeg) <= MAX_BYTES:
            return jpeg, "image/jpeg", (target_w, target_h)
    raise SystemExit("画像が 1MB を超えています。もっと小さいPNGにしてください。")


def main() -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or token.startswith("your_"):
        raise SystemExit("LINE_CHANNEL_ACCESS_TOKEN を .env に設定してください。")

    src = find_image()
    payload, content_type, (width, height) = prepare_image(src)
    api = LineBotApi(token)

    for menu in api.get_rich_menu_list():
        if menu.name == RICH_MENU_NAME:
            api.delete_rich_menu(menu.rich_menu_id)
            print(f"Removed old rich menu: {menu.rich_menu_id}")

    rich_menu = RichMenu(
        size=RichMenuSize(width=width, height=height),
        selected=True,
        name=RICH_MENU_NAME,
        chat_bar_text="施錠する",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=width, height=height),
                action=MessageAction(label="施錠する", text="閉めて"),
            )
        ],
    )
    rich_menu_id = api.create_rich_menu(rich_menu)
    api.set_rich_menu_image(rich_menu_id, content_type, io.BytesIO(payload))
    api.set_default_rich_menu(rich_menu_id)
    print(f"Rich menu is now default: {rich_menu_id}")
    print(f"Image: {src} -> {width}x{height} ({content_type}, {len(payload)} bytes)")
    print("トーク画面下部の「施錠する」を開くと画像が表示され、タップで「閉めて」が送信されます。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
