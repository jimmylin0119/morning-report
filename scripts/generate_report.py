import os
import sys
import re
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_market_data import snapshot
from send_telegram import send_messages

GEMINI_MODEL = "gemini-2.0-flash"
MORNING_URL = "https://jimmylin-strategy.netlify.app/"
TW_TZ = timezone(timedelta(hours=8))

SYSTEM_PROMPT = """你是「JimmyLin Strategy 晨報機器人」，專業金融晨報撰寫員。

【核心原則】
- 專業、精簡、清楚、好閱讀
- 不模糊、不誇張、不保證獲利
- 區分事實（來自數據）/ 判斷（基於事實推論）/ 建議（策略方向）
- 若資料不足，必須明確寫明「盤前判斷」
- 絕對不可亂編即時數據，只能使用提供給你的行情數據

【輸出格式】
你必須輸出 5 則訊息，以 <<<MSG_SPLIT>>> 分隔（獨立一行）。
每則都要：
- 有明確標題（用 emoji 開頭）
- 段落短、適合手機閱讀
- 使用 Telegram HTML 格式：<b>粗體</b>、<i>斜體</i>
- 不使用 Markdown（不要用 # 或 **）
- 不使用程式碼區塊"""

def build_prompt(market_data, date_str, weekday):
    return f"""請產出今日（{date_str} {weekday}）的 5 則晨報。

【今日市場即時數據】
▼ 台股
{market_data['tw_text']}

▼ 美股
{market_data['us_text']}

▼ 總經指標
{market_data['macro_text']}

資料時間：{market_data['timestamp']}

【輸出要求】
5 則訊息，每則以 <<<MSG_SPLIT>>> 分隔。

每則開頭：
━━━━━━━━━━━━━━━
📊 <b>JimmyLin Strategy｜每日晨報</b>
📅 {date_str} {weekday} · 第 N/5 則
━━━━━━━━━━━━━━━

每則結尾：
━━━━━━━━━━━━━━━
🔗 查看完整分析：
{MORNING_URL}

五則標題：
1. 🌍 <b>國際重大事件</b>
2. 💹 <b>國際金融情勢</b>
3. 📰 <b>影響台股 / 美股的重要新聞</b>
4. 🇹🇼 <b>台股綜合趨勢分析</b>
5. 🇺🇸 <b>美股綜合趨勢分析</b>

要求：
- 第 2 則結尾：偏多 / 偏空 / 中性
- 第 4 則結尾：積極 / 保守 / 觀望
- 第 5 則結尾：偏多 / 偏空 / 震盪 / 觀望
- 數字只用上方提供的數據，不可編造

請直接開始產出。"""

def generate_report(market_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)
    now_tw = datetime.now(TW_TZ)
    date_str = now_tw.strftime("%Y/%m/%d")
    weekday = ["週一","週二","週三","週四","週五","週六","週日"][now_tw.weekday()]

    print(f"[info] 呼叫 Gemini（{GEMINI_MODEL}）...")

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=4000,
        ),
        contents=build_prompt(market_data, date_str, weekday),
    )

    messages = [m.strip() for m in response.text.split("<<<MSG_SPLIT>>>") if m.strip()]
    print(f"[info] 產出 {len(messages)} 則")
    return messages

ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a"}

def sanitize_html(text):
    text = text.replace("&", "&amp;")
    placeholders = {}
    def stash(m):
        tag = m.group(0)
        inner = m.group(1).lower().split()[0].lstrip("/")
        if inner in ALLOWED_TAGS:
            key = f"§§{len(placeholders)}§§"
            placeholders[key] = tag
            return key
        return tag.replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"<(/?[^<>]+)>", stash, text)
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    for key, tag in placeholders.items():
        text = text.replace(key, tag)
    return text

def main():
    print("=" * 50)
    print(f"JimmyLin Strategy 晨報機器人")
    print(f"執行時間：{datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\n[1/3] 抓取行情...")
    try:
        market_data = snapshot()
        print(f"  ✓ 台股 {len(market_data['tw'])} / 美股 {len(market_data['us'])} / 總經 {len(market_data['macro'])}")
    except Exception as e:
        print(f"  ✗ 失敗：{e}")
        market_data = {
            "timestamp": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M"),
            "tw_text": "（數據暫不可用）",
            "us_text": "（數據暫不可用）",
            "macro_text": "（數據暫不可用）",
            "tw": [], "us": [], "macro": [],
        }

    print("\n[2/3] 生成晨報...")
    try:
        messages = generate_report(market_data)
        if len(messages) < 3:
            print(f"  ✗ 則數不足（{len(messages)}）")
            sys.exit(1)
    except Exception as e:
        print(f"  ✗ 失敗：{e}")
        sys.exit(1)

    messages = [sanitize_html(m) for m in messages]

    print("\n[3/3] 發送 Telegram...")
    success = send_messages(messages, delay=1.5)

    print("\n" + "=" * 50)
    print(f"完成：{success}/{len(messages)} 則成功")
    print("=" * 50)

    if success < len(messages):
        sys.exit(1)

if __name__ == "__main__":
    main()
