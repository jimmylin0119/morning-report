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

MIS_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://mis.twse.com.tw/stock/index.jsp"
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
    """單一 symbol 用 yf.Ticker 抓。"""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="60d", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 2:
            print(f"[warn] {name}({symbol}) 無資料")
            return None
        hist = hist.dropna(subset=["Close"])
        if len(hist) < 2:
            return None

        closes  = [float(x) for x in hist["Close"].tolist()]
        highs   = [float(x) for x in hist["High"].tolist()]
        lows    = [float(x) for x in hist["Low"].tolist()]
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
            "vol_ratio": volratio_safe(vol_ratio),
        }
    except Exception as e:
        print(f"[warn] fetch_yf_one({symbol}) failed: {e}")
        return None


def volratio_safe(v):
    if v is None or _safe_num(v) is None:
        return None
    return v


def fetch_mis_realtime(ex_ch):
    """從 TWSE MIS API 取得即時盤中報價。
    回傳 (price, prev_close, high, low) 或 None。"""
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1"
        r = requests.get(url, timeout=10, headers=MIS_HEADERS)
        data = r.json()
        if not data.get("msgArray"):
            return None
        s = data["msgArray"][0]

        def to_f(key):
            v = s.get(key)
            if v is None or v == "-" or v == "":
                return None
            try:
                return float(v)
            except Exception:
                return None

        price = to_f("z")
        prev  = to_f("y")
        high  = to_f("h")
        low   = to_f("l")

        # z 為 "-" 表示尚未開盤，回退用 o（開盤）或最近成交
        if price is None:
            price = to_f("o") or to_f("u") or to_f("d")
        return (price, prev, high, low)
    except Exception as e:
        print(f"[warn] MIS {ex_ch} failed: {e}")
        return None


def fetch_twse_quote(stock_id, name):
    """抓個股：即時用 MIS，歷史用 STOCK_DAY。"""
    try:
        # 即時報價
        live = fetch_mis_realtime(f"tse_{stock_id}.tw")
        live_price = prev_close = live_high = live_low = None
        if live:
            live_price, prev_close, live_high, live_low = live

        # 歷史 60 日（用來算 MA / RSI）
        today = date.today().strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={today}&stockNo={stock_id}&response=json"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()

        closes = []
        last_close = last_change = last_high = last_low = None
        if data.get("stat") == "OK" and data.get("data"):
            rows = data["data"]
            for row in rows:
                try:
                    closes.append(float(str(row[6]).replace(",", "")))
                except Exception:
                    pass
            last_row = rows[-1]
            try:
                last_close = float(str(last_row[6]).replace(",", ""))
                last_high  = float(str(last_row[4]).replace(",", ""))
                last_low   = float(str(last_row[5]).replace(",", ""))
                cs = str(last_row[7]).replace(",", "").strip()
                last_change = float(cs.replace("+", "").replace("-", "").replace("X", ""))
                if cs.startswith("-"):
                    last_change = -abs(last_change)
            except Exception:
                pass

        # 優先即時，沒有再用收盤
        if live_price is not None and prev_close:
            close = live_price
            change = round(close - prev_close, 2)
            pct = round(change / prev_close * 100, 2) if prev_close else 0.0
            high = live_high if live_high else close
            low  = live_low  if live_low  else close
        elif last_close is not None:
            close = last_close
            change = last_change if last_change is not None else 0
            denom = close - change
            pct = round(change / denom * 100, 2) if denom else 0.0
            high = last_high if last_high else close
            low  = last_low  if last_low  else close
        else:
            return None

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


def fetch_twse_index(name):
    """抓加權指數：即時用 MIS（tse_t00.tw），歷史用 FMTQIK。"""
    try:
        # 即時加權指數
        live = fetch_mis_realtime("tse_t00.tw")
        live_price = prev_close = live_high = live_low = None
        if live:
            live_price, prev_close, live_high, live_low = live

        # 歷史
        today = date.today().strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={today}&response=json"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()

        closes = []
        last_close = last_change = None
        if data.get("stat") == "OK" and data.get("data"):
            rows = data["data"]
            for row in rows:
                try:
                    closes.append(float(str(row[4]).replace(",", "")))
                except Exception:
                    pass
            last_row = rows[-1]
            try:
                last_close = float(str(last_row[4]).replace(",", ""))
                cs = str(last_row[5]).strip()
                last_change = float(cs.replace("+", "").replace("-", "").replace(",", ""))
                if cs.startswith("-"):
                    last_change = -abs(last_change)
            except Exception:
                pass

        if live_price is not None and prev_close:
            close = live_price
            change = round(close - prev_close, 2)
            pct = round(change / prev_close * 100, 2) if prev_close else 0.0
            high = live_high if live_high else close
            low  = live_low  if live_low  else close
        elif last_close is not None:
            close = last_close
            change = last_change if last_change is not None else 0
            denom = close - change
            pct = round(change / denom * 100, 2) if denom else 0.0
            high = close
            low = close
        else:
            return fetch_yf_one("^TWII", name)

        return {
            "name":      name,
            "symbol":    "^TWII",
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
        print(f"[warn] fetch_twse_index failed: {e}")
        return fetch_yf_one("^TWII", name)


def fetch_group(symbols_dict):
    result = []
    if symbols_dict is TW_SYMBOLS:
        for name, sym in symbols_dict.items():
            if sym == "^TWII":
                q = fetch_twse_index(name)
            elif sym == "^TWOII":
                q = fetch_yf_one(sym, name)
            else:
                q = fetch_twse_quote(sym, name)
                if not q:
                    q = fetch_yf_one(sym + ".TW", name)
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
