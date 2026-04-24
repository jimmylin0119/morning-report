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
    """把 NaN、None 轉成 None，其他保留數字。"""
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
    """單一 symbol 用 yf.Ticker 抓，避開 batch download 的問題。"""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="60d", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 2:
            print(f"[warn] {name}({symbol}) 無資料")
            return None

        # 清掉 NaN 的列
        hist = hist.dropna(subset=["Close"])
        if len(hist) < 2:
            return None

        closes = [float(x) for x in hist["Close"].tolist()]
        highs  = [float(x) for x in hist["High"].tolist()]
        lows   = [float(x) for x in hist["Low"].tolist()]
        volumes = [float(x) for x in hist["Volume"].tolist()] if "Volume" in hist.columns else []

        last = closes[-1]
        prev = closes[-2]
        pct = (last - prev) / prev * 100 if prev else 0.0

        vol_ratio = None
        if len(volumes) >= 6:
            avg_vol = sum(volumes[-6:-1]) / 5
            if avg_vol > 0:
                vol_ratio = round(volumes[-1] / avg_vol, 2)

        return {
            "name":      name,
            "symbol":    symbol,
            "price":     round(last, 2),
            "change":    round(last - prev, 2),
            "pct":       round(pct, 2),
            "high":      round(highs[-1], 2),
            "low":       round(lows[-1], 2),
            "ma5":       calc_ma(closes, 5),
            "ma10":      calc_ma(closes, 10),
            "ma20":      calc_ma(closes, 20),
            "rsi":       calc_rsi(closes, 14),
            "vol_ratio": vol_ratio,
        }
    except Exception as e:
        print(f"[warn] fetch_yf_one({symbol}) failed: {e}")
        return None


def fetch_twse_quote(stock_id, name):
    """從證交所抓個股資料。欄位順序：日期,股數,金額,開,高,低,收,漲跌,筆數"""
    try:
        today = date.today().strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={today}&stockNo={stock_id}&response=json"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return None
        rows = data["data"]
        last_row = rows[-1]

        def parse_num(s):
            return float(str(s).replace(",", "").replace("+", "").replace("X", "").strip())

        close  = parse_num(last_row[6])
        high   = parse_num(last_row[4])
        low    = parse_num(last_row[5])
        change_str = str(last_row[7]).replace(",", "").strip()
        # 漲跌可能含 "+" 或 "-"，先處理正負號
        change = parse_num(change_str)
        if change_str.startswith("-") or "-" in change_str:
            change = -abs(change)
        prev_close = close - change
        pct = (change / prev_close * 100) if prev_close else 0.0

        closes = []
        for row in rows:
            try:
                closes.append(parse_num(row[6]))
            except Exception:
                pass

        return {
            "name":      name,
            "symbol":    stock_id,
            "price":     round(close, 2),
            "change":    round(change, 2),
            "pct":       round(pct, 2),
            "high":      round(high, 2),
            "low":       round(low, 2),
            "ma5":       calc_ma(closes, 5),
            "ma10":      calc_ma(closes, 10),
            "ma20":      calc_ma(closes, 20),
            "rsi":       calc_rsi(closes, 14),
            "vol_ratio": None,
        }
    except Exception as e:
        print(f"[warn] fetch_twse_quote({stock_id}) failed: {e}")
        return None


def fetch_group(symbols_dict):
    result = []
    # 台股：指數走 yfinance，個股走 TWSE
    if symbols_dict is TW_SYMBOLS:
        for name, sym in symbols_dict.items():
            if sym.startswith("^"):
                # 加權/櫃買 → 用 yfinance
                q = fetch_yf_one(sym, name)
            else:
                # 個股 → 用 TWSE，失敗 fallback 到 yfinance
                q = fetch_twse_quote(sym, name)
                if not q:
                    q = fetch_yf_one(sym + ".TW", name)
            if q:
                result.append(q)
            else:
                print(f"[warn] 無法取得 {name}")
        return result

    # 美股、總經：都走 yfinance 單一查詢
    for name, sym in symbols_dict.items():
        q = fetch_yf_one(sym, name)
        if q:
            result.append(q)
        else:
            print(f"[warn] 無法取得 {name}({sym})")
    return result


def format_quote_line(item):
    arrow = "▲" if item["pct"] >= 0 else "▼"
    sign  = "+" if item["pct"] >= 0 else ""
    return f"{item['name']} {item['price']:,.2f} {arrow} {sign}{item['pct']:.2f}%"


def snapshot():
    tw    = fetch_group(TW_SYMBOLS)
    us    = fetch_group(US_SYMBOLS)
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
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tw":         tw,
        "us":         us,
        "macro":      macro,
        "tw_text":    "\n".join(full_line(x) for x in tw),
        "us_text":    "\n".join(full_line(x) for x in us),
        "macro_text": "\n".join(format_quote_line(x) for x in macro),
    }
