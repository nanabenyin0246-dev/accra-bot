"""
neural_signal.py — Accra Bot Neural Network Signal Scorer
Pure Python, zero extra dependencies. Runs on Railway as-is.

Architecture:
  Input  (12 features) → Hidden1 (24) → Hidden2 (12) → Output (1)
  Activation: ReLU (hidden), Sigmoid (output)

Training:
  Phase 1: Synthetic crypto-calibrated data (runs immediately)
  Phase 2: Real trade outcomes appended to neural_training.json each cycle
  Phase 3: Fine-tune on real data every 50 trades

Usage in bot.py:
  from neural_signal import neural_score, record_trade_outcome, nn_status

  # Before executing a trade:
  ns = neural_score(rsi, macd_hist, bb_pct, ema_cross, momentum,
                    vol_ratio, atr_pct, fear_greed, score, confidence,
                    hour_utc, btc_trend_pct)
  if ns["quality"] < 0.35:
      log(f"  [NN] BLOCKED {symbol}: quality={ns['quality']:.2f}")
      return False

  # After trade closes (win/loss):
  record_trade_outcome(trade_id, won=True)
"""

import os, json, math, random, time
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────
_BASE        = os.path.expanduser("~/accra-bot")
_WEIGHTS_FILE = os.path.join(_BASE, "neural_weights.json")
_TRAINING_FILE= os.path.join(_BASE, "neural_training.json")
_PENDING_FILE = os.path.join(_BASE, "neural_pending.json")

# ── Architecture ─────────────────────────────────────────────
N_INPUT  = 12
N_H1     = 24
N_H2     = 12
N_OUTPUT = 1
LEARNING_RATE    = 0.01
RETRAIN_EVERY    = 50   # real trades before fine-tuning
SYNTHETIC_EPOCHS = 200
FINETUNE_EPOCHS  = 100


# ─────────────────────────────────────────────────────────────
# MATH PRIMITIVES
# ─────────────────────────────────────────────────────────────

def _relu(x):
    return max(0.0, x)

def _relu_d(x):
    return 1.0 if x > 0 else 0.0

def _sigmoid(x):
    x = max(-500, min(500, x))
    return 1.0 / (1.0 + math.exp(-x))

def _sigmoid_d(s):
    return s * (1.0 - s)

def _dot(v1, v2):
    return sum(a * b for a, b in zip(v1, v2))

def _mat_vec(mat, vec):
    return [_dot(row, vec) for row in mat]

def _add_vec(v1, v2):
    return [a + b for a, b in zip(v1, v2)]

def _scale_vec(v, s):
    return [x * s for x in v]


# ─────────────────────────────────────────────────────────────
# NETWORK — weights stored as plain lists
# ─────────────────────────────────────────────────────────────

def _init_weights(seed=42):
    """Xavier initialisation."""
    random.seed(seed)

    def _xavier(fan_in, fan_out, n):
        limit = math.sqrt(6.0 / (fan_in + fan_out))
        return [random.uniform(-limit, limit) for _ in range(n)]

    return {
        "W1": [_xavier(N_INPUT, N_H1, N_INPUT) for _ in range(N_H1)],
        "b1": [0.0] * N_H1,
        "W2": [_xavier(N_H1, N_H2, N_H1) for _ in range(N_H2)],
        "b2": [0.0] * N_H2,
        "W3": [_xavier(N_H2, N_OUTPUT, N_H2)],
        "b3": [0.0],
        "trained_on": 0,
        "version": 1,
    }


def _forward(w, x):
    """Forward pass. Returns (output, cache) for backprop."""
    # Layer 1
    z1 = _add_vec(_mat_vec(w["W1"], x), w["b1"])
    a1 = [_relu(v) for v in z1]

    # Layer 2
    z2 = _add_vec(_mat_vec(w["W2"], a1), w["b2"])
    a2 = [_relu(v) for v in z2]

    # Output
    z3 = _add_vec(_mat_vec(w["W3"], a2), w["b3"])
    a3 = [_sigmoid(z3[0])]

    return a3[0], {"x": x, "z1": z1, "a1": a1, "z2": z2, "a2": a2, "z3": z3, "a3": a3}


def _backward(w, cache, y_true, lr=LEARNING_RATE):
    """Backprop. Updates weights in place. Returns loss."""
    a3, a2, a1 = cache["a3"], cache["a2"], cache["a1"]
    z2, z1, x  = cache["z2"], cache["z1"], cache["x"]

    loss = 0.5 * (a3[0] - y_true) ** 2

    # Output delta
    d3 = [(a3[0] - y_true) * _sigmoid_d(a3[0])]

    # Layer 2 delta
    d2 = []
    for j in range(N_H2):
        err = sum(d3[k] * w["W3"][k][j] for k in range(N_OUTPUT))
        d2.append(err * _relu_d(z2[j]))

    # Layer 1 delta
    d1 = []
    for j in range(N_H1):
        err = sum(d2[k] * w["W2"][k][j] for k in range(N_H2))
        d1.append(err * _relu_d(z1[j]))

    # Update W3, b3
    for k in range(N_OUTPUT):
        for j in range(N_H2):
            w["W3"][k][j] -= lr * d3[k] * a2[j]
        w["b3"][k] -= lr * d3[k]

    # Update W2, b2
    for k in range(N_H2):
        for j in range(N_H1):
            w["W2"][k][j] -= lr * d2[k] * a1[j]
        w["b2"][k] -= lr * d2[k]

    # Update W1, b1
    for k in range(N_H1):
        for j in range(N_INPUT):
            w["W1"][k][j] -= lr * d1[k] * x[j]
        w["b1"][k] -= lr * d1[k]

    return loss


# ─────────────────────────────────────────────────────────────
# FEATURE NORMALISATION
# Maps raw indicator values to [0, 1] range for the network
# ─────────────────────────────────────────────────────────────

def _normalise(rsi, macd_hist, bb_pct, ema_cross, momentum,
               vol_ratio, atr_pct, fear_greed, score, confidence,
               hour_utc, btc_trend_pct):
    """
    Returns 12-element normalised feature vector.

    Inputs:
      rsi           : 0–100
      macd_hist     : raw histogram value (any float)
      bb_pct        : 0–1 (Bollinger Band %B)
      ema_cross     : +1 golden cross, -1 death cross, 0 neutral
      momentum      : % change over 5 bars (e.g. +3.2)
      vol_ratio     : volume ratio vs average (e.g. 1.5)
      atr_pct       : ATR as % of price (e.g. 0.012)
      fear_greed    : 0–100
      score         : bot combined score (-100 to +100)
      confidence    : 0–100
      hour_utc      : 0–23
      btc_trend_pct : BTC 4h % change (e.g. -2.1)
    """
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    return [
        _clamp(rsi, 0, 100) / 100.0,
        _clamp(macd_hist / 0.01, -5, 5) / 10.0 + 0.5,   # centre at 0.5
        _clamp(bb_pct, 0, 1),
        (ema_cross + 1) / 2.0,                            # -1→0, 0→0.5, +1→1
        _clamp(momentum / 10.0, -1, 1) / 2.0 + 0.5,
        _clamp(vol_ratio / 3.0, 0, 1),
        _clamp(atr_pct / 0.05, 0, 1),
        _clamp(fear_greed, 0, 100) / 100.0,
        _clamp((score + 100) / 200.0, 0, 1),
        _clamp(confidence, 0, 100) / 100.0,
        math.sin(2 * math.pi * hour_utc / 24),            # cyclical hour encoding
        _clamp(btc_trend_pct / 10.0, -1, 1) / 2.0 + 0.5,
    ]


# ─────────────────────────────────────────────────────────────
# SYNTHETIC TRAINING DATA
# Calibrated to crypto market behaviour.
# Good signals: oversold + bullish confluence
# Bad signals:  overbought + weak confluence + extreme greed
# ─────────────────────────────────────────────────────────────

def _generate_synthetic_data(n=2000, seed=7):
    random.seed(seed)
    data = []

    for _ in range(n):
        # Generate random features
        rsi          = random.uniform(10, 90)
        macd_hist    = random.uniform(-0.05, 0.05)
        bb_pct       = random.uniform(0, 1)
        ema_cross    = random.choice([-1, 0, 0, 1])
        momentum     = random.uniform(-8, 8)
        vol_ratio    = random.uniform(0.3, 3.0)
        atr_pct      = random.uniform(0.003, 0.04)
        fear_greed   = random.uniform(5, 95)
        score        = random.uniform(-80, 80)
        confidence   = random.uniform(10, 90)
        hour_utc     = random.randint(0, 23)
        btc_trend    = random.uniform(-6, 6)

        # ── Label generation (domain knowledge) ──────────────
        quality = 0.5  # base

        # RSI: oversold = good BUY setup
        if rsi < 30:   quality += 0.20
        elif rsi < 40: quality += 0.10
        elif rsi > 70: quality -= 0.20
        elif rsi > 60: quality -= 0.10

        # MACD histogram positive = bullish momentum
        if macd_hist > 0.005: quality += 0.10
        elif macd_hist < -0.005: quality -= 0.10

        # Bollinger Band: near lower band = buy opportunity
        if bb_pct < 0.1:  quality += 0.15
        elif bb_pct > 0.9: quality -= 0.15

        # EMA cross
        if ema_cross == 1:  quality += 0.12
        elif ema_cross == -1: quality -= 0.12

        # Momentum: strong positive = good, but not too strong (overbought)
        if 1 < momentum < 5:   quality += 0.08
        elif momentum > 7:     quality -= 0.08
        elif momentum < -3:    quality -= 0.12

        # Volume: high volume confirms signal
        if vol_ratio > 1.8: quality += 0.08
        elif vol_ratio < 0.6: quality -= 0.08

        # ATR: very low = choppy, avoid
        if atr_pct < 0.005: quality -= 0.10

        # Fear & Greed
        if fear_greed < 20:   quality += 0.15   # extreme fear = buy
        elif fear_greed < 35: quality += 0.08
        elif fear_greed > 80: quality -= 0.18   # extreme greed = danger
        elif fear_greed > 65: quality -= 0.08

        # Bot score
        quality += score / 800.0   # small contribution

        # Confidence
        if confidence > 60: quality += 0.08
        elif confidence < 30: quality -= 0.10

        # Trading window bonus (London/NY)
        if 7 <= hour_utc <= 9 or 13 <= hour_utc <= 17:
            quality += 0.05

        # BTC trend alignment
        if btc_trend > 1:   quality += 0.06
        elif btc_trend < -2: quality -= 0.10

        # Add noise
        quality += random.gauss(0, 0.05)
        quality = max(0.02, min(0.98, quality))

        x = _normalise(rsi, macd_hist, bb_pct, ema_cross, momentum,
                        vol_ratio, atr_pct, fear_greed, score, confidence,
                        hour_utc, btc_trend)
        data.append((x, quality))

    return data


# ─────────────────────────────────────────────────────────────
# TRAINING
# ─────────────────────────────────────────────────────────────

def _train(weights, data, epochs=100, lr=LEARNING_RATE, shuffle=True):
    """Train weights on (x, y) pairs. Returns final avg loss."""
    for epoch in range(epochs):
        if shuffle:
            random.shuffle(data)
        total_loss = 0.0
        for x, y in data:
            _, cache = _forward(weights, x)
            loss = _backward(weights, cache, y, lr)
            total_loss += loss
        avg_loss = total_loss / len(data)
    return avg_loss


def _save_weights(w):
    try:
        with open(_WEIGHTS_FILE, "w") as f:
            json.dump(w, f)
    except Exception as e:
        print(f"[NN] Save error: {e}")


def _load_weights():
    try:
        if os.path.exists(_WEIGHTS_FILE):
            with open(_WEIGHTS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _bootstrap():
    """Train on synthetic data if no weights exist."""
    print("[NN] Bootstrapping neural network on synthetic data...")
    w = _init_weights()
    data = _generate_synthetic_data(2000)
    loss = _train(w, data, epochs=SYNTHETIC_EPOCHS, lr=0.01)
    w["trained_on"] = len(data)
    w["bootstrap_loss"] = round(loss, 6)
    w["bootstrapped_at"] = datetime.now(timezone.utc).isoformat()
    _save_weights(w)
    print(f"[NN] Bootstrap complete. Loss={loss:.4f} | Weights saved.")
    return w


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

# Load or bootstrap weights at import time
_weights = _load_weights()
if _weights is None:
    _weights = _bootstrap()
else:
    print(f"[NN] Weights loaded. Trained on {_weights.get('trained_on', 0)} samples.")


def neural_score(rsi: float, macd_hist: float, bb_pct: float,
                 ema_cross: int, momentum: float, vol_ratio: float,
                 atr_pct: float, fear_greed: int, score: int,
                 confidence: int, hour_utc: int,
                 btc_trend_pct: float) -> dict:
    """
    Score a trade signal through the neural network.

    Returns dict:
      quality     : 0.0–1.0 (higher = better trade)
      gate        : True if quality >= threshold (trade allowed)
      threshold   : current quality threshold
      label       : STRONG / GOOD / WEAK / REJECT
      reason      : human-readable explanation
    """
    global _weights
    x = _normalise(rsi, macd_hist, bb_pct, ema_cross, momentum,
                   vol_ratio, atr_pct, fear_greed, score, confidence,
                   hour_utc, btc_trend_pct)
    quality, _ = _forward(_weights, x)
    quality = round(quality, 4)

    # Dynamic threshold — tightens as more real trades accumulate
    real_trades = _weights.get("real_trades", 0)
    if real_trades < 20:
        threshold = 0.38   # lenient while learning
    elif real_trades < 100:
        threshold = 0.42   # moderate
    else:
        threshold = 0.46   # strict once data-rich

    gate = quality >= threshold

    if quality >= 0.70:   label = "STRONG"
    elif quality >= 0.55: label = "GOOD"
    elif quality >= threshold: label = "WEAK"
    else:                 label = "REJECT"

    reason = (
        f"NN quality={quality:.2f} threshold={threshold:.2f} "
        f"label={label} real_trades={real_trades}"
    )

    return {
        "quality":   quality,
        "gate":      gate,
        "threshold": threshold,
        "label":     label,
        "reason":    reason,
        "features":  x,
    }


def record_trade_outcome(features: list, won: bool):
    """
    Record a real trade outcome for future fine-tuning.
    features: the _normalise() output saved at trade time
    won: True = profitable, False = loss
    """
    try:
        label = 0.80 if won else 0.20   # not 1.0/0.0 — label smoothing
        entry = {
            "features": features,
            "label":    label,
            "won":      won,
            "ts":       datetime.now(timezone.utc).isoformat(),
        }

        # Load existing
        existing = []
        if os.path.exists(_TRAINING_FILE):
            with open(_TRAINING_FILE) as f:
                existing = json.load(f)

        existing.append(entry)

        with open(_TRAINING_FILE, "w") as f:
            json.dump(existing[-500:], f)   # keep last 500

        print(f"[NN] Outcome recorded: {'WIN' if won else 'LOSS'} "
              f"(total real: {len(existing)})")

        # Fine-tune every RETRAIN_EVERY trades
        if len(existing) % RETRAIN_EVERY == 0:
            _finetune(existing)

    except Exception as e:
        print(f"[NN] Record error: {e}")


def _finetune(real_data: list):
    """Fine-tune weights on accumulated real trade data."""
    global _weights
    print(f"[NN] Fine-tuning on {len(real_data)} real trades...")

    # Mix: 30% synthetic + 70% real (prevent catastrophic forgetting)
    synthetic = _generate_synthetic_data(int(len(real_data) * 0.43), seed=int(time.time()))
    real_pairs = [(d["features"], d["label"]) for d in real_data]
    mixed = synthetic + real_pairs

    loss = _train(_weights, mixed, epochs=FINETUNE_EPOCHS, lr=0.005)
    _weights["trained_on"] = _weights.get("trained_on", 0) + len(real_pairs)
    _weights["real_trades"] = len(real_data)
    _weights["last_finetune"] = datetime.now(timezone.utc).isoformat()
    _weights["finetune_loss"] = round(loss, 6)
    _save_weights(_weights)
    print(f"[NN] Fine-tune complete. Loss={loss:.4f} | "
          f"Total samples={_weights['trained_on']}")


def save_pending_features(trade_id: str, features: list):
    """Save features at trade entry so outcome can be linked later."""
    try:
        pending = {}
        if os.path.exists(_PENDING_FILE):
            with open(_PENDING_FILE) as f:
                pending = json.load(f)
        pending[trade_id] = {
            "features": features,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        # Keep only last 50 pending
        if len(pending) > 50:
            oldest = sorted(pending.keys())[0]
            del pending[oldest]
        with open(_PENDING_FILE, "w") as f:
            json.dump(pending, f)
    except Exception as e:
        print(f"[NN] Pending save error: {e}")


def resolve_trade_outcome(trade_id: str, won: bool):
    """
    Call when a trade closes. Links outcome to saved features.
    trade_id: the symbol + entry time string used at open
    """
    try:
        if not os.path.exists(_PENDING_FILE):
            return
        with open(_PENDING_FILE) as f:
            pending = json.load(f)
        if trade_id not in pending:
            return
        features = pending[trade_id]["features"]
        record_trade_outcome(features, won)
        del pending[trade_id]
        with open(_PENDING_FILE, "w") as f:
            json.dump(pending, f)
    except Exception as e:
        print(f"[NN] Resolve error: {e}")


def nn_status() -> dict:
    """Returns current neural network status for bot status push."""
    global _weights
    return {
        "trained_on":    _weights.get("trained_on", 0),
        "real_trades":   _weights.get("real_trades", 0),
        "bootstrap_loss":_weights.get("bootstrap_loss", 0),
        "finetune_loss": _weights.get("finetune_loss", None),
        "last_finetune": _weights.get("last_finetune", None),
        "version":       _weights.get("version", 1),
    }


def print_nn_status():
    s = nn_status()
    print("\n" + "="*55)
    print("  ACCRA BOT — NEURAL NETWORK STATUS")
    print("="*55)
    print(f"  Architecture : {N_INPUT}→{N_H1}→{N_H2}→{N_OUTPUT}")
    print(f"  Total samples: {s['trained_on']}")
    print(f"  Real trades  : {s['real_trades']}")
    print(f"  Bootstrap loss:{s['bootstrap_loss']:.4f}")
    if s["finetune_loss"]:
        print(f"  Finetune loss: {s['finetune_loss']:.4f}")
    if s["last_finetune"]:
        print(f"  Last finetune: {s['last_finetune'][:19]}")
    print("="*55 + "\n")
