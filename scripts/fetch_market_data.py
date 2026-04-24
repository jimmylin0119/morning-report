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


def calc_rsi(closes, period=14):
    """計算 RSI。"""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def calc_ma(closes, period):
    """計算均線。"""
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def fetch_quote(symbol):
    """抓取單一標的完整數據（含 RSI、MA、量能、最高最低）。"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="60d")  # 抓 60 天以便算均線和 RSI
        if hist.empty or len(hist) < 2:
            return None

        closes = hist["Close"].tolist()
        highs = hist["High"].tolist()
        lows = hist["Low"].tolist()
        volumes = hist["Volume"].tolist() if "Volume" in hist else []

        last = float(closes[-1])
        prev = float(closes[-2])
        pct = (last - prev) / prev * 100 if prev else 0.0

        # 今日最高最低
        today_high = round(float(highs[-1]), 2)
        today_low = round(float(lows[-1]), 2)

        # 均線
        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)

        # RSI
        rsi = calc_rsi(closes, 14)

        # 量能倍數（今日量 / 5 日均量）
        vol_ratio = None
        if len(volumes) >= 6:
            avg_vol = sum(volumes[-6:-1]) / 5
            if avg_vol > 0:
                vol_ratio = round(volumes[-1] / avg_vol, 2)

        return {
            "symbol": symbol,
            "price": round(last, 2),
            "change": round(last - prev, 2),
            "pct": round(pct, 2),
            "high": today_high,
            "low": today_low,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
        }
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

    # 完整的行情文字（含技術指標，給 AI 用）
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
        if tech:
            return f"{base} [{' '.join(tech)}]"
        return base

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tw": tw, "us": us, "macro": macro,
        "tw_text": "\n".join(full_line(x) for x in tw),
        "us_text": "\n".join(full_line(x) for x in us),
        "macro_text": "\n".join(format_quote_line(x) for x in macro),
    }
