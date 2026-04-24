def fetch_quote(symbol):
    try:
        ticker = yf.Ticker(symbol)
        
        # 用 fast_info 取得即時價（今天盤中即時）
        fi = ticker.fast_info
        last = float(fi.last_price)
        prev = float(fi.previous_close)
        pct = (last - prev) / prev * 100 if prev else 0.0

        # 今日最高最低
        today_high = float(fi.day_high) if fi.day_high else last
        today_low = float(fi.day_low) if fi.day_low else last

        # 技術指標需要歷史數據
        hist = ticker.history(period="60d")
        closes = hist["Close"].tolist() if not hist.empty else []
        volumes = hist["Volume"].tolist() if "Volume" in hist and not hist.empty else []

        # 今天盤中價更新到最後
        if closes:
            closes[-1] = last

        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)
        rsi = calc_rsi(closes, 14)

        vol_ratio = None
        if len(volumes) >= 6:
            avg_vol = sum(volumes[-6:-1]) / 5
            if avg_vol > 0:
                vol_ratio = round(float(fi.shares_outstanding or volumes[-1]) / avg_vol if False else volumes[-1] / avg_vol, 2)

        return {
            "symbol": symbol,
            "price": round(last, 2),
            "change": round(last - prev, 2),
            "pct": round(pct, 2),
            "high": round(today_high, 2),
            "low": round(today_low, 2),
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
        }
    except Exception as e:
        print(f"[warn] fetch_quote({symbol}) failed: {e}")
        return None
