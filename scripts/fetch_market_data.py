import yfinance as yf
from datetime import datetime

TW_SYMBOLS = {
    "加權指數": "^TWII",
    "櫃買指數": "^TWOII",
    "台積電": "2330.TW",
    "鴻海": "2317.TW",
    "聯發科": "2454.TW",
    "廣達": "2382.TW",
    "緯創": "3231.TW",
    "長榮": "2603.TW",
    "大立光": "3008.TW",
    "聯電": "2303.TW",
}

US_SYMBOLS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "Dow Jones": "^DJI",
    "NVDA": "NVDA",
    "MSFT": "MSFT",
    "AAPL": "AAPL",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "TSLA": "TSLA",
    "META": "META",
    "QQQ": "QQQ",
}

MACRO_SYMBOLS = {
    "VIX": "^VIX",
    "美元指數 DXY": "DX-Y.NYB",
    "10Y 美債殖利率": "^TNX",
    "布蘭特原油": "BZ=F",
    "黃金": "GC=F",
    "USD/TWD": "TWD=X",
}

def fetch_quote(symbol):
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        pct = (last - prev) / prev * 100 if prev else 0.0
        return {"symbol": symbol, "price": round(last, 2), "change": round(last - prev, 2), "pct": round(pct, 2)}
    except Exception as e:
        print(f"[warn] fetch_quote({symbol}) failed: {e}")
        return None

def fetch_group(symbols):
    result = []
    for name, sym in symbols.items():
        q = fetch_quote(sym)
        if q:
            q["name"] = name
            result.append(q)
    return result

def format_quote_line(item):
    arrow = "▲" if item["pct"] >= 0 else "▼"
    sign = "+" if item["pct"] >= 0 else ""
    return f"{item['name']} {item['price']:,.2f} {arrow} {sign}{item['pct']:.2f}%"

def snapshot():
    tw = fetch_group(TW_SYMBOLS)
    us = fetch_group(US_SYMBOLS)
    macro = fetch_group(MACRO_SYMBOLS)
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tw": tw, "us": us, "macro": macro,
        "tw_text": "\n".join(format_quote_line(x) for x in tw),
        "us_text": "\n".join(format_quote_line(x) for x in us),
        "macro_text": "\n".join(format_quote_line(x) for x in macro),
    }
