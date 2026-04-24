import os
import sys
import re
import json
import feedparser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_market_data import snapshot
from send_telegram import send_messages

GEMINI_MODEL = "gemini-flash-latest"
MORNING_URL = "https://jimmylin-strategy.netlify.app/"
TW_TZ = timezone(timedelta(hours=8))

# 新聞 RSS 來源
NEWS_FEEDS = {
    "yahoo_us": "https://finance.yahoo.com/news/rssindex",
    "yahoo_tw": "https://tw.news.yahoo.com/rss/finance",
    "cnyes_wd": "https://news.cnyes.com/rss/cat/wd_stock",
    "cnyes_tw": "https://news.cnyes.com/rss/cat/tw_stock",
}


def fetch_news(feed_url, limit=3):
    """抓取 RSS 新聞，回傳標題 + 連結清單。"""
    try:
        feed = feedparser.parse(feed_url)
        return [
            {"title": e.title, "link": e.link}
            for e in feed.entries[:limit]
        ]
    except Exception as e:
        print(f"[warn] 新聞抓取失敗 {feed_url}: {e}")
        return []


def fetch_all_news():
    """抓取所有新聞來源的最新新聞。"""
    news = {}
    for key, url in NEWS_FEEDS.items():
        news[key] = fetch_news(url, limit=3)
    return news


SYSTEM_PROMPT = """你是「JimmyLin Strategy 晨報機器人」，專業金融晨報撰寫員。

【核心原則】
- 專業、精簡、清楚、好閱讀
- 不模糊、不誇張、不保證獲利
- 區分事實（來自數據）/ 判斷（基於事實推論）/ 建議（策略方向）
- 絕對不可亂編即時數據，只能使用提供給你的行情數據
- 新聞連結必須使用提供給你的真實 RSS 新聞，不可編造網址

【輸出格式】
先輸出 JSON（===JSON_START=== 到 ===JSON_END===），再輸出 5 則 Telegram 訊息（以 <<<MSG_SPLIT>>> 分隔）。
使用 Telegram HTML 格式：<b>粗體</b>、<i>斜體</i>。不使用 Markdown。"""


def build_prompt(market_data, news_data, date_str, weekday):
    # 組裝新聞資訊
    news_text = ""
    for key, items in news_data.items():
        if items:
            news_text += f"\n【{key}】\n"
            for it in items:
                news_text += f"- {it['title']}\n  {it['link']}\n"

    return f"""請產出今日（{date_str} {weekday}）的晨報分析。

【今日市場即時數據】
▼ 台股（含 MA / RSI / 量比）
{market_data['tw_text']}

▼ 美股（含 MA / RSI / 量比）
{market_data['us_text']}

▼ 總經指標
{market_data['macro_text']}

資料時間：{market_data['timestamp']}

【今日新聞 RSS】{news_text}

【輸出格式】

===JSON_START===
{{
  "analysis_date": "{date_str}",
  "tw": {{
    "bias": "偏多或偏空或震盪",
    "bias_text": "一句話結論",
    "today_action": "今日操作建議",
    "chase_ok": false,
    "batch_ok": true,
    "position": "70-80%",
    "support": "關鍵支撐",
    "watch_range": "觀察區間",
    "resist": "關鍵壓力",
    "short": "短線策略",
    "mid": "中線策略",
    "long": "長線策略",
    "risk": "最大風險"
  }},
  "us": {{
    "bias": "偏多或偏空或震盪",
    "bias_text": "一句話結論",
    "today_action": "今日操作建議",
    "chase_ok": false,
    "batch_ok": true,
    "position": "50-60%",
    "support": "關鍵支撐",
    "watch_range": "觀察區間",
    "resist": "關鍵壓力",
    "short": "短線策略",
    "mid": "中線策略",
    "long": "長線策略",
    "risk": "最大風險"
  }},
  "decision": {{
    "tw_direction": "偏多",
    "us_direction": "震盪",
    "global": "中性",
    "strategy": "今日策略主軸"
  }}
}}
===JSON_END===

然後產出 5 則 Telegram 訊息，以 <<<MSG_SPLIT>>> 分隔（獨立一行）。

每則格式如下：

━━━━━━━━━━━━━━━
📊 <b>JimmyLin Strategy｜每日晨報</b>
📅 {date_str} {weekday} · 第 N/5 則
━━━━━━━━━━━━━━━

【第 1 則】🌍 <b>國際重大事件</b>
- 列出 2-3 個最重要的國際事件，每項附上真實新聞連結（從上方 RSS 挑）
- 每則最後用 📰 附連結

【第 2 則】💹 <b>國際金融情勢</b>
- 美股表現、匯市、大宗商品
- 結尾給結論：偏多 / 偏空 / 中性
- 附 1-2 條新聞連結

【第 3 則】📰 <b>影響台股 / 美股重要新聞</b>
- 標示 🟢利多 / 🔴利空 / 🟡中性
- 每則後面附上真實新聞連結

【第 4 則】🇹🇼 <b>台股綜合趨勢分析</b>
格式：
🇹🇼 <b>台股大盤分析</b>
━━━━━━━━━━━━━━━
🔵 加權指數 [價格] [▲/▼ 幅度]
最高 [數字]  最低 [數字]
MA5: [數字]  MA10: [數字]  MA20: [數字]
趨勢：[上升/下降]  RSI: [數字] [超買注意/正常]
💡 [一句話結構判讀]

⭐ 今日挑股 Top 6（短線 1–3 天）
✅ [股名]  [價格]  [漲跌幅]  RSI [數字]  [量比]x
（選 6 檔強勢股，RSI>80 標 🔥 超買）

🎯 今日操作建議
[盤前判斷 + 2-3 條操作策略]
結論：積極 / 保守 / 觀望

━━━━━━━━━━━━━━━
⚠️ <i>免責聲明</i>
以上分析不構成投資建議
市場有風險，投資需謹慎
本內容僅供參考，請自行判斷
━━━━━━━━━━━━━━━

🔗 查看完整分析
{MORNING_URL}

【第 5 則】🇺🇸 <b>美股綜合趨勢分析</b>
格式同第 4 則，但是美股版本（S&P 500 / NASDAQ / Dow + 科技巨頭 Top 6）

同樣結尾加上免責聲明 + 網站連結。

要求：
- 所有數字只能用上方提供的真實數據
- 新聞連結必須從上方 RSS 中挑，不可編造
- 第 4、5 則結尾必須加上免責聲明
- 第 1、2、3 則不加免責聲明
- 只有第 4、5 則結尾放 MarketPulse 網站連結

請直接開始輸出。"""


def parse_analysis(text):
    try:
        start = text.find("===JSON_START===")
        end = text.find("===JSON_END===")
        if start == -1 or end == -1:
            return None
        json_str = text[start+16:end].strip()
        return json.loads(json_str)
    except Exception as e:
        print(f"  [warn] JSON 解析失敗：{e}")
        return None


def extract_messages(text):
    end = text.find("===JSON_END===")
    if end != -1:
        text = text[end+14:]
    return [m.strip() for m in text.split("<<<MSG_SPLIT>>>") if m.strip()]


def save_analysis_to_json(analysis, market_data):
    if not analysis:
        return
    output_path = Path(__file__).parent.parent / "public" / "data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing["analysis"] = analysis
    existing["analysis_updated_at"] = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now(TW_TZ)
    existing["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    existing["updated_ts"] = int(now.timestamp())
    if market_data.get("tw"):
        existing["tw"] = market_data["tw"]
    if market_data.get("us"):
        existing["us"] = market_data["us"]
    if market_data.get("macro"):
        existing["macro"] = market_data["macro"]
    output_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  ✓ 分析結果已寫入 public/data.json")


def generate_report(market_data, news_data):
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
            max_output_tokens=8000,
        ),
        contents=build_prompt(market_data, news_data, date_str, weekday),
    )
    full_text = response.text
    analysis = parse_analysis(full_text)
    messages = extract_messages(full_text)
    print(f"[info] 產出 {len(messages)} 則訊息")
    if analysis:
        print(f"[info] 台股：{analysis.get('tw',{}).get('bias','?')} / 美股：{analysis.get('us',{}).get('bias','?')}")
    return messages, analysis


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

    print("\n[1/4] 抓取行情...")
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

    print("\n[2/4] 抓取新聞...")
    try:
        news_data = fetch_all_news()
        total = sum(len(v) for v in news_data.values())
        print(f"  ✓ 抓取 {total} 則新聞")
    except Exception as e:
        print(f"  ✗ 新聞抓取失敗：{e}")
        news_data = {}

    print("\n[3/4] 生成晨報與分析...")
    try:
        messages, analysis = generate_report(market_data, news_data)
        if len(messages) < 3:
            print(f"  ✗ 則數不足（{len(messages)}）")
            sys.exit(1)
        save_analysis_to_json(analysis, market_data)
    except Exception as e:
        print(f"  ✗ 失敗：{e}")
        sys.exit(1)

    messages = [sanitize_html(m) for m in messages]

    print("\n[4/4] 發送 Telegram...")
    success = send_messages(messages, delay=1.5)

    print("\n" + "=" * 50)
    print(f"完成：{success}/{len(messages)} 則成功")
    print("=" * 50)

    if success < len(messages):
        sys.exit(1)


if __name__ == "__main__":
    main()
