import yfinance as yf
import requests
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

ALL_SYMBOLS = {**US_SYMBOLS, **MACRO_SYMBOLS}

_cache = {}


def calc_rsi(closes, period=14):
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
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def _build_quote(name, symbol, hist):
    try:
        if hist is None or hist.empty or len(hist) < 2:
            return None
        closes  = hist["Close"].tolist()
        highs   = hist["High"].tolist()
        lows    = hist["Low"].tolist()
        volumes = hist["Volume"].tolist() if "Volume" in hist.columns else []
        last = float(closes[-1])
        prev = float(closes[-2])
        pct  = (last - prev) / prev * 100 if prev else 0.0
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
            "high":      round(float(highs[-1]), 2),
            "low":       round(float(lows[-1]), 2),
            "ma5":       calc_ma(closes, 5),
            "ma10":      calc_ma(closes, 10),
            "ma20":      calc_ma(closes, 20),
            "rsi":       calc_rsi(closes, 14),
            "vol_ratio": vol_ratio,
        }
    except Exception as e:
        print(f"[warn] _build_quote({symbol}) failed: {e}")
        return None


def _ensure_cache(symbols_dict):
    global _cache
    if _cache:
        return
    all_syms = list(symbols_dict.values())
    print(f"[fetch] batch download {len(all_syms)} symbols...")
    try:
        raw = yf.download(
            tickers=all_syms,
            period="60d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
            timeout=30,
        )
        for sym in all_syms:
            try:
                if len(all_syms) == 1:
                    _cache[sym] = raw
                else:
                    _cache[sym] = raw[sym] if sym in raw.columns.get_level_values(0) else None
            except Exception:
                _cache[sym] = None
        print(f"[fetch] batch download 完成")
    except Exception as e:
        print(f"[warn] batch download 失敗，改用逐一模式: {e}")
        for sym in all_syms:
            try:
                _cache[sym] = yf.Ticker(sym).history(period="60d")
            except Exception as e2:
                print(f"[warn] fallback {sym} failed: {e2}")
                _cache[sym] = None


# ── 台股：改用 TWSE 官方 API 抓最新資料 ──
def fetch_twse_quote(stock_id, name):
    """從台灣證交所官方 API 抓個股即時資料。"""
    try:
        today = date.today().strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={today}&stockNo={stock_id}&response=json"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return None
        rows = data["data"]
        # 最後一筆是最新交易日
        last_row = rows[-1]
        prev_row = rows[-2] if len(rows) >= 2 else None
        # 欄位：日期,成交股數,成交金額,開盤價,最高價,最低價,收盤價,漲跌價差,成交筆數
        close = float(last_row[6].replace(",", ""))
        high  = float(last_row[4].replace(",", ""))
        low   = float(last_row[5].replace(",", ""))
        open_ = float(last_row[3].replace(",", ""))
        change = float(last_row[7].replace(",", "").replace("+", ""))
        prev_close = close - change
        pct = (change / prev_close * 100) if prev_close else 0.0
        closes = [float(row[6].replace(",", "")) for row in rows]
        return {
            "name":      name,
            "symbol":    stock_id,
            "price":     close,
            "change":    round(change, 2),
            "pct":       round(pct, 2),
            "high":      high,
            "low":       low,
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
    """從 TWSE 抓加權/櫃買指數。"""
    try:
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        # 找 "大盤統計資訊" 表
        for table in data.get("tables", []):
            for row in table.get("data", []):
                if "發行量加權股價指數" in str(row):
                    try:
                        price = float(str(row[1]).replace(",", ""))
                        change = float(str(row[2]).replace(",", ""))
                        prev = price - change
                        pct = (change / prev * 100) if prev else 0.0
                        return {
                            "name":   name,
                            "symbol": "^TWII",
                            "price":  round(price, 2),
                            "change": round(change, 2),
                            "pct":    round(pct, 2),
                            "high": None, "low": None,
                            "ma5": None, "ma10": None, "ma20": None,
                            "rsi": None, "vol_ratio": None,
                        }
                    except Exception:
                        pass
        return None
    except Exception as e:
        print(f"[warn] fetch_twse_index failed: {e}")
        return None


def fetch_group(symbols_dict):
    # 台股走 TWSE API，美股+總經走 yfinance
    if symbols_dict is TW_SYMBOLS:
        return fetch_tw_group()
    _ensure_cache(ALL_SYMBOLS)
    result = []
    for name, sym in symbols_dict.items():
        q = _build_quote(name, sym, _cache.get(sym))
        if q:
            result.append(q)
        else:
            print(f"[warn] 無法取得 {name} ({sym})")
    return result


def fetch_tw_group():
    """台股全部走 TWSE 官方 API。"""
    result = []
    for name, sym in TW_SYMBOLS.items():
        if sym in ("^TWII", "^TWOII"):
            # 指數用 yfinance fallback
            try:
                hist = yf.Ticker(sym).history(period="60d")
                q = _build_quote(name, sym, hist)
                if q:
                    result.append(q)
            except Exception as e:
                print(f"[warn] index {sym} failed: {e}")
        else:
            q = fetch_twse_quote(sym, name)
            if q:
                result.append(q)
            else:
                # fallback to yfinance
                try:
                    hist = yf.Ticker(sym + ".TW").history(period="60d")
                    q = _build_quote(name, sym + ".TW", hist)
                    if q:
                        result.append(q)
                except Exception:
                    pass
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
