import os
import time
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

def send_message(text, parse_mode="HTML", retries=3):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    if not token or not channel_id:
        print("[error] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHANNEL_ID")
        return False
    url = TELEGRAM_API.format(token=token)
    payload = {"chat_id": channel_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": False}
    for attempt in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                return True
            print(f"[warn] Telegram {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"[warn] 發送失敗 attempt={attempt + 1}: {e}")
        time.sleep(2)
    return False

def send_messages(messages, delay=1.5):
    success = 0
    for i, msg in enumerate(messages, 1):
        ok = send_message(msg)
        print(f"[send] 第 {i}/{len(messages)} 則: {'✓' if ok else '✗'}")
        if ok:
            success += 1
        if i < len(messages):
            time.sleep(delay)
    return success
