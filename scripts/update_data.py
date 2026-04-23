import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_market_data import fetch_group, TW_SYMBOLS, US_SYMBOLS, MACRO_SYMBOLS

TW_TZ = timezone(timedelta(hours=8))

def build_data():
    now = datetime.now(TW_TZ)
    tw = fetch_group(TW_SYMBOLS)
    us = fetch_group(US_SYMBOLS)
    macro = fetch_group(MACRO_SYMBOLS)

    total_min = now.hour * 60 + now.minute
    weekday = now.weekday()

    if weekday >= 5:
        market_status = "週末休市"
    elif 9*60 <= total_min < 13*60+30:
        market_status = "台股開盤中"
    elif total_min >= 22*60+30 or total_min < 5*60:
        market_status = "美股開盤中"
    else:
        market_status = "盤後時段"

    def to_ticker(items):
        return [{
            "sym": x["name"],
            "price": f"{x['price']:,.2f}",
            "chg": f"{'+' if x['pct']>=0 else ''}{x['pct']:.2f}%",
            "dir": "up" if x["pct"] >= 0 else "down"
        } for x in items]

    def find(items, name):
        return next((x for x in items if x["name"] == name), None)

    return {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_ts": int(now.timestamp()),
        "market_status": market_status,
        "tw": tw,
        "us": us,
        "macro": macro,
        "tw_ticker": to_ticker(tw),
        "us_ticker": to_ticker(us),
        "market_cards": {
            "twse":    find(tw, "加權指數"),
            "tpex":    find(tw, "櫃買指數"),
            "sp500":   find(us, "S&P 500"),
            "nasdaq":  find(us, "NASDAQ"),
            "vix":     find(macro, "VIX"),
            "dxy":     find(macro, "美元指數 DXY"),
            "gold":    find(macro, "黃金"),
            "oil":     find(macro, "布蘭特原油"),
            "usd_twd": find(macro, "USD/TWD"),
            "us10y":   find(macro, "10Y 美債殖利率"),
        }
    }

def main():
    output_path = Path(__file__).parent.parent / "public" / "data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 讀取現有 data.json（保留分析內容，只更新數字）
    existing = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    print("[update_data] 抓取行情...")
    try:
        data = build_data()
        print(f"  ✓ 台股 {len(data['tw'])} / 美股 {len(data['us'])} / 總經 {len(data['macro'])}")
    except Exception as e:
        print(f"  ✗ 失敗：{e}")
        sys.exit(1)

    # 合併：保留分析內容，覆蓋數字
    existing.update(data)

    output_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  ✓ 更新完成：{data['updated_at']} | {data['market_status']}")

if __name__ == "__main__":
    main()
