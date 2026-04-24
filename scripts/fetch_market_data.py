import yfinance as yf
import requests
import math
from datetime import datetime, date

TW_SYMBOLS = {
    "加權指數": "^TWII",
    "櫃買指數": "^TWOII",
    "台積電": "2330",
    "鴻海": "2317",
    "聯發科": "2454",
    "廣達": "2382",
    "緯創": "3231",
    "長榮": "2603",
    "大立光": "3008",
    "聯電": "2303",
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


def _safe_num(x):
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None


def calc_rsi(closes, period=14):
    closes = [c for c in closes if _safe_num(c) is not None]
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def calc_ma(closes, period):
    closes = [c for c in closes if _safe_num(c) is not None]
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def fetch_yf_one(symbol, name):
    """用 Yahoo Finance chart API 抓即時價（含今天盤中）。"""
    try:
        chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=60d"
        r = requests.get(chart_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        j = r.json()
        result = j.get("chart", {}).get("result", [])
        if not result:
            return None

        meta = result[0].get("meta", {})
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]

        last = _safe_num(meta.get("regularMarketPrice"))
        prev = _safe_num(meta.get("chartPreviousClose"))
        if last is None or prev is None:
            return None

        pct = (last - prev) / prev * 100 if prev else 0.0
        today_high = _safe_num(meta.get("regularMarketDayHigh")) or last
        today_low = _safe_num(meta.get("regularMarketDayLow")) or last

        closes_raw = quote.get("close", [])
        closes = [float(x) for x in closes_raw if x is not None]
        if closes:
            closes[-1] = last  # 把最後一筆改成即時價

        volumes_raw = quote.get("volume", [])
        volumes = [float(x) for x in volumes_raw if x is not None]

        vol_ratio = None
        if len(volumes) >= 6:
            avg_vol = sum(volumes[-6:-1]) / 5
            if avg_vol > 0:
                vol_ratio = round(volumes[-1] / avg_vol, 2)

        return {
            "name": name, "symbol": symbol,
            "price": round(last, 2), "change": round(last - prev, 2), "pct": round(pct, 2),
            "high": round(today_high, 2), "low": round(today_low, 2),
            "ma5": calc_ma(closes, 5), "ma10": calc_ma(closes, 10), "ma20": calc_ma(closes, 20),
            "rsi": calc_rsi(closes, 14), "vol_ratio": vol_ratio,
        }
    except Exception as e:
        print(f"[warn] fetch_yf_one({symbol}) failed: {e}")
        return None


def fetch_group(symbols_dict):
    result = []
    if symbols_dict is TW_SYMBOLS:
        for name, sym in symbols_dict.items():
            yf_sym = sym if sym.startswith("^") else f"{sym}.TW"
            q = fetch_yf_one(yf_sym, name)
            if q:
                result.append(q)
            else:
                print(f"[warn] 無法取得 {name}")
        return result

    for name, sym in symbols_dict.items():
        q = fetch_yf_one(sym, name)
        if q:
            result.append(q)
        else:
            print(f"[warn] 無法取得 {name}({sym})")
    return result


def format_quote_line(item):
    arrow = "▲" if item["pct"] >= 0 else "▼"
    sign = "+" if item["pct"] >= 0 else ""
    return f"{item['name']} {item['price']:,.2f} {arrow} {sign}{item['pct']:.2f}%"


def snapshot():
    tw = fetch_group(TW_SYMBOLS)
    us = fetch_group(US_SYMBOLS)
    macro = fetch_group(MACRO_SYMBOLS)

    def full_line(item):
        base = format_quote_line(item)
        tech = []
        if item.get("high") and item.get("low"):
            tech.append(f"高{item['high']:,.2f}/低{item['low']:,.2f}")
        if item.get("ma5"):
            tech.append(f"MA5={item['ma5']:,.2f}")
        if item.get("ma20"):
            tech.append(f"MA20={item['ma20']:,.2f}")
        if item.get("rsi") is not None:
            tech.append(f"RSI={item['rsi']}")
        if item.get("vol_ratio"):
            tech.append(f"量比={item['vol_ratio']}")
        return f"{base} [{' '.join(tech)}]" if tech else base

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tw": tw, "us": us, "macro": macro,
        "tw_text": "\n".join(full_line(x) for x in tw),
        "us_text": "\n".join(full_line(x) for x in us),
        "macro_text": "\n".join(format_quote_line(x) for x in macro),
    }
