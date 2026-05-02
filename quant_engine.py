import math
from datetime import datetime

def kelly_position_size(confidence_pct, free_usdt, sl_multiplier=1.0, tp_multiplier=1.5, min_trade=2.0):
    p = confidence_pct / 100.0
    q = 1.0 - p
    f = (p / sl_multiplier) - (q / tp_multiplier)
    if f <= 0:
        return 0.0
    f = (f / 2.0)
    f = min(f, 0.30)
    size = round(free_usdt * f, 2)
    return max(size, min_trade) if size >= min_trade else 0.0

def expected_value(confidence_pct, sl_pct=1.5, tp_pct=2.25, fee_pct=0.20):
    p = confidence_pct / 100.0
    return round((p * tp_pct) - ((1-p) * sl_pct) - fee_pct, 4)

def bayesian_confidence_update(raw_confidence, signal_direction, fear_greed=50, market_condition="neutral", consecutive_losses=0):
    adj = raw_confidence
    if signal_direction == "BUY":
        if fear_greed < 25: adj += 8.0
        elif fear_greed < 40: adj += 4.0
        elif fear_greed > 75: adj -= 6.0
        if market_condition == "bull": adj += 5.0
        elif market_condition == "bear": adj -= 8.0
    if consecutive_losses >= 3:
        adj -= (consecutive_losses * 2.0)
    return round(max(0.0, min(100.0, adj)), 2)

def position_skew_factor(current_balance, starting_balance=70.0):
    ratio = current_balance / starting_balance
    if ratio >= 1.0: return 0.85
    elif ratio >= 0.80: return 0.75
    elif ratio >= 0.60: return 0.55
    else: return 0.35

def trade_decision(signal_confidence, signal_direction, free_usdt, fear_greed=50, market_condition="neutral", current_balance=22.0, starting_balance=70.0, consecutive_losses=0, sl_multiplier=1.0, tp_multiplier=1.5, min_confidence=55.0):
    adj_conf = bayesian_confidence_update(signal_confidence, signal_direction, fear_greed, market_condition, consecutive_losses)
    if adj_conf < min_confidence:
        return {"trade": False, "position_size": 0.0, "adjusted_confidence": adj_conf, "reason": f"Conf {adj_conf:.1f}% < {min_confidence}%"}
    ev = expected_value(adj_conf)
    if ev <= 0:
        return {"trade": False, "position_size": 0.0, "adjusted_confidence": adj_conf, "ev": ev, "reason": f"EV={ev:.3f}% negative"}
    kelly_size = kelly_position_size(adj_conf, free_usdt, sl_multiplier, tp_multiplier)
    if kelly_size <= 0:
        return {"trade": False, "position_size": 0.0, "adjusted_confidence": adj_conf, "ev": ev, "reason": "Kelly=0"}
    skew = position_skew_factor(current_balance, starting_balance)
    final_size = round(max(min(kelly_size * skew, free_usdt * 0.40), 2.0), 2)
    return {"trade": True, "position_size": final_size, "adjusted_confidence": adj_conf, "ev": ev, "kelly_size": kelly_size, "skew": skew, "reason": f"adj_conf={adj_conf:.1f}% EV={ev:.3f}% size=${final_size}"}

if __name__ == "__main__":
    d = trade_decision(65, "BUY", 22.0, fear_greed=33, market_condition="bear", current_balance=22.0)
    print(d)
