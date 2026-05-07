import requests, time, re

_kronos_cache = {"direction": None, "ts": 0}
CACHE_SECONDS = 3600

def _fetch_kronos_demo():
    try:
        r = requests.get("https://shiyu-coder.github.io/Kronos-demo/", timeout=10, headers={"User-Agent": "AccraBot/1.0"})
        html = r.text
        for pattern in [r'bullishProbability["\s:=]+([0-9.]+)', r'bullish_prob["\s:=]+([0-9.]+)', r'"prob"["\s:]+([0-9.]+)']:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if 0 < val <= 100:
                    return val, "kronos_demo"
        r2 = requests.get("https://raw.githubusercontent.com/shiyu-coder/Kronos-demo/master/model/predictions.json", timeout=8)
        data = r2.json()
        for key in ["bullish_prob", "bullishProbability", "confidence", "prob_up"]:
            if key in data:
                return float(data[key]), "kronos_json"
    except:
        pass
    return None, None

def _binance_momentum():
    try:
        r = requests.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "1h", "limit": 48}, timeout=8)
        closes = [float(c[4]) for c in r.json()]
        change_24h = (closes[-1] - closes[-24]) / closes[-24] * 100
        bull_ratio = sum(1 for i in range(-24, 0) if closes[i] > closes[i-1]) / 24 * 100
        if change_24h > 2: momentum = min(75 + change_24h, 85)
        elif change_24h > 0.5: momentum = 60 + (change_24h * 5)
        elif change_24h < -2: momentum = max(25 + change_24h, 15)
        elif change_24h < -0.5: momentum = 40 + (change_24h * 5)
        else: momentum = 50
        return round(momentum * 0.6 + bull_ratio * 0.4, 1), "binance_momentum"
    except:
        return None, None

def get_kronos_btc_signal():
    global _kronos_cache
    if time.time() - _kronos_cache["ts"] < CACHE_SECONDS and _kronos_cache.get("direction"):
        return _kronos_cache
    prob, source = _fetch_kronos_demo()
    if prob is None:
        prob, source = _binance_momentum()
    if prob is None:
        prob, source = 50.0, "default_neutral"
    if prob >= 65: direction, adj = "UP", +12
    elif prob >= 55: direction, adj = "UP", +6
    elif prob <= 35: direction, adj = "DOWN", -12
    elif prob <= 45: direction, adj = "DOWN", -6
    else: direction, adj = "NEUTRAL", 0
    result = {"direction": direction, "bullish_prob": prob, "adjustment": adj, "source": source, "ts": time.time()}
    _kronos_cache = result
    return result

def apply_kronos_to_signal(raw_confidence, signal_direction):
    signal = get_kronos_btc_signal()
    adj = signal["adjustment"]
    if signal_direction == "BUY": adjusted = raw_confidence + adj
    elif signal_direction == "SELL": adjusted = raw_confidence - adj
    else: adjusted = raw_confidence
    return {"original": raw_confidence, "adjusted": round(max(0.0, min(100.0, adjusted)), 2),
            "kronos_direction": signal["direction"], "kronos_prob": signal["bullish_prob"],
            "kronos_adj": adj, "source": signal["source"]}
