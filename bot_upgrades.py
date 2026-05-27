import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
bot_upgrades.py — Accra Bot Enhancement Module
Inspired by zostaff/ai-quant-researcher

5 upgrades that plug into bot.py with minimal changes:
  1. KillSwitch        — halts trading on loss limits / stale data
  2. CriticAgent       — adversarial AI review before every trade
  3. RiskSizer         — volatility-adjusted Kelly position sizing
  4. FeaturePipeline   — leakage-proof indicator wrapper
  5. DeflatedSharpe    — multiple-testing gate before signals execute

Usage in bot.py:
  from bot_upgrades import KillSwitch, critic_agent, risk_sizer, FeaturePipeline, deflated_sharpe_gate
"""

import os, time, json, math, requests, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("accra_bot")

# ─────────────────────────────────────────────────────────────
# 1. KILL-SWITCH
# Halts all trading when loss limits or anomalies are detected.
# Inspired by zostaff kill-switch + Kobeissi capital protection.
# ─────────────────────────────────────────────────────────────

@dataclass
class KillSwitchConfig:
    intraday_loss_pct:   float = 0.08   # halt if down 8% today
    rolling_5d_loss_pct: float = 0.15   # halt if down 15% in 5 days
    max_open_trades:     int   = 5      # hard cap on concurrent trades
    data_staleness_sec:  int   = 120    # halt if price data > 2 min old
    min_usdt_reserve:    float = 2.0    # never trade below this USDT floor
    max_consecutive_losses: int = 4     # halt after 4 losses in a row


class KillSwitch:
    """
    Guards every trade cycle. Call ks.check(state) before executing.
    Reset requires explicit manual call with token — no auto-resume.
    """
    def __init__(self, cfg: KillSwitchConfig = None):
        self.cfg     = cfg or KillSwitchConfig()
        self.halted  = False
        self.reason  = ""
        self._start_balance: Optional[float] = None
        self._5d_balances: list = []
        self._last_snapshot = time.time()

    def record_balance(self, usdt: float):
        """Call once per cycle with current USDT balance."""
        now = time.time()
        if self._start_balance is None:
            self._start_balance = usdt
        # Snapshot every ~1 hour for 5-day rolling window
        if now - self._last_snapshot > 3600:
            self._5d_balances.append(usdt)
            if len(self._5d_balances) > 120:  # 5 days × 24 snapshots
                self._5d_balances.pop(0)
            self._last_snapshot = now

    def check(self, state: dict) -> tuple:
        """
        Returns (ok: bool, reason: str).
        state keys: usdt, open_trades, last_data_ts, consecutive_losses,
                    start_of_day_usdt
        """
        if self.halted:
            return False, f"HALTED: {self.reason}"

        usdt              = state.get("usdt", 0)
        open_trades       = state.get("open_trades", 0)
        last_data_ts      = state.get("last_data_ts", time.time())
        consecutive_losses= state.get("consecutive_losses", 0)
        start_of_day_usdt = state.get("start_of_day_usdt", usdt)

        # 1. USDT floor — never wipe the account
        if usdt < self.cfg.min_usdt_reserve:
            return self._halt(f"USDT below floor: ${usdt:.2f} < ${self.cfg.min_usdt_reserve:.2f}")

        # 2. Intraday loss limit
        if start_of_day_usdt > 0:
            intraday_loss = (start_of_day_usdt - usdt) / start_of_day_usdt
            if intraday_loss >= self.cfg.intraday_loss_pct:
                return self._halt(
                    f"Intraday loss limit hit: -{intraday_loss*100:.1f}% "
                    f"(limit {self.cfg.intraday_loss_pct*100:.0f}%)"
                )

        # 3. 5-day rolling loss
        if len(self._5d_balances) >= 24:
            peak_5d = max(self._5d_balances[-120:])
            if peak_5d > 0:
                drawdown_5d = (peak_5d - usdt) / peak_5d
                if drawdown_5d >= self.cfg.rolling_5d_loss_pct:
                    return self._halt(
                        f"5-day drawdown limit hit: -{drawdown_5d*100:.1f}% "
                        f"(limit {self.cfg.rolling_5d_loss_pct*100:.0f}%)"
                    )

        # 4. Max open trades
        if open_trades >= self.cfg.max_open_trades:
            return False, f"Max open trades reached: {open_trades}/{self.cfg.max_open_trades}"

        # 5. Data staleness
        data_age = time.time() - last_data_ts
        if data_age > self.cfg.data_staleness_sec:
            return self._halt(
                f"Price data stale: {data_age:.0f}s old "
                f"(limit {self.cfg.data_staleness_sec}s)"
            )

        # 6. Consecutive losses
        if consecutive_losses >= self.cfg.max_consecutive_losses:
            return self._halt(
                f"Consecutive loss limit: {consecutive_losses} losses in a row"
            )

        return True, "OK"

    def _halt(self, reason: str) -> tuple:
        self.halted = True
        self.reason = reason
        msg = f"[KILL-SWITCH] HALTED — {reason}"
        print(msg)
        log.error(msg)
        try:
            _telegram_notify(f"<b>🛑 KILL-SWITCH ACTIVATED</b>\n{reason}\n\nManual reset required.")
        except Exception:
            pass
        return False, reason

    def reset(self, token: str):
        """Manual reset only. Token = 'root-cause-analyzed'"""
        if token != "root-cause-analyzed":
            raise PermissionError("Wrong token. Analyze the root cause first.")
        self.halted = False
        self.reason = ""
        print("[KILL-SWITCH] Reset. Trading resumed.")

    def status(self) -> dict:
        return {
            "halted":  self.halted,
            "reason":  self.reason,
            "config":  {
                "intraday_loss_pct":   self.cfg.intraday_loss_pct,
                "rolling_5d_loss_pct": self.cfg.rolling_5d_loss_pct,
                "max_consecutive_losses": self.cfg.max_consecutive_losses,
            }
        }


# Singleton — bot.py imports and uses this one instance
kill_switch = KillSwitch()


# ─────────────────────────────────────────────────────────────
# 2. CRITIC AGENT
# Adversarial AI review before every trade.
# Assumes the trade is broken until proven otherwise.
# Inspired by zostaff critic_agent pattern.
# ─────────────────────────────────────────────────────────────

CRITIC_SYSTEM = """You are a skeptical senior quant reviewer.
ASSUME THIS TRADE IS WRONG until proven otherwise.
Your job: find reasons NOT to take this trade.
Be brief, harsh, and specific. Return ONLY valid JSON."""

CRITIC_PROMPT = """Review this trade signal:

Symbol:     {symbol}
Signal:     {signal}
Score:      {score}
Confidence: {confidence}%
RSI:        {rsi}
Reasons:    {reasons}
USDT Bal:   ${usdt:.2f}
Open Trades:{open_trades}
Fear&Greed: {fear_greed}
Market:     {market}

CHECK FOR:
1. Is RSI already at extreme — chasing a move?
2. Is confidence < 35%? Too weak to risk capital.
3. Is score built from conflicting signals?
4. Is USDT too low to survive a stop loss?
5. Is Fear&Greed extreme in wrong direction?
6. Any reason this is a BAD trade right now?

Reply ONLY in JSON:
{{"approved": true/false, "confidence_adj": -20 to +10, "fatal_issues": ["list"], "warnings": ["list"], "verdict": "one sentence"}}"""


def critic_agent(symbol: str, signal: str, score: int, confidence: int,
                 rsi: float, reasons: list, usdt: float,
                 open_trades: int, fear_greed: int, market: str,
                 call_ai_fn) -> dict:
    """
    Adversarial review of a trade signal before execution.
    
    Args:
        call_ai_fn: the bot's call_multi_ai function
    
    Returns dict with keys: approved, confidence_adj, fatal_issues, warnings, verdict
    """
    # Fast-path rejections (no AI needed)
    if confidence < 25:
        return {
            "approved": False, "confidence_adj": 0,
            "fatal_issues": [f"Confidence {confidence}% below minimum 25%"],
            "warnings": [], "verdict": "Signal too weak — skipped AI review"
        }
    if usdt < 2.5 and signal == "BUY":
        return {
            "approved": False, "confidence_adj": 0,
            "fatal_issues": [f"USDT ${usdt:.2f} too low to safely trade"],
            "warnings": [], "verdict": "Insufficient capital"
        }

    prompt = CRITIC_PROMPT.format(
        symbol=symbol, signal=signal, score=score,
        confidence=confidence, rsi=round(rsi, 1),
        reasons="; ".join(str(r) for r in reasons[:5]),
        usdt=usdt, open_trades=open_trades,
        fear_greed=fear_greed, market=market
    )

    try:
        raw = call_ai_fn(prompt, CRITIC_SYSTEM)
        if not raw:
            # AI unavailable — apply conservative default
            return {
                "approved": confidence >= 40,
                "confidence_adj": 0,
                "fatal_issues": [],
                "warnings": ["AI critic unavailable — applied conservative threshold"],
                "verdict": "AI unavailable — defaulted to confidence >= 40%"
            }

        import re as _re
        raw = _re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)

        # Ensure required keys exist
        result.setdefault("approved", False)
        result.setdefault("confidence_adj", 0)
        result.setdefault("fatal_issues", [])
        result.setdefault("warnings", [])
        result.setdefault("verdict", "")

        # Clamp confidence adjustment
        result["confidence_adj"] = max(-20, min(10, int(result["confidence_adj"])))

        status = "[OK] APPROVED" if result["approved"] else "[ERR] REJECTED"
        print(f"  [CRITIC] {symbol} {status} | {result['verdict'][:60]}")
        if result["fatal_issues"]:
            for issue in result["fatal_issues"]:
                print(f"    ⚠ {issue}")

        return result

    except Exception as e:
        print(f"  [CRITIC] Parse error: {e} — defaulting to reject")
        return {
            "approved": False, "confidence_adj": 0,
            "fatal_issues": [f"Critic parse error: {str(e)[:50]}"],
            "warnings": [], "verdict": "Critic failed — trade blocked for safety"
        }


# ─────────────────────────────────────────────────────────────
# 3. RISK SIZER
# Volatility-adjusted Kelly position sizing.
# Replaces flat % sizing in execute().
# Inspired by zostaff realistic_cost_bps + Kelly sizing.
# ─────────────────────────────────────────────────────────────

def calc_atr_pct(closes: list, period: int = 14) -> float:
    """Average True Range as % of price — measures volatility."""
    if len(closes) < period + 1:
        return 0.01  # default 1% volatility
    trs = [abs(closes[i] - closes[i-1]) for i in range(-period, 0)]
    atr = sum(trs) / len(trs)
    return atr / closes[-1] if closes[-1] > 0 else 0.01


def risk_sizer(usdt: float, confidence: int, closes: list,
               sl_pct: float = 0.05, min_trade: float = 2.0,
               max_pct: float = 0.05) -> dict:  # CRITICAL FIX: 5% max
    """
    Volatility-adjusted Kelly position sizing.

    Logic:
    - Kelly fraction = (edge * win_rate - loss_rate) / edge
    - Volatility scalar: reduce size when ATR is high (choppy market)
    - Confidence scalar: scale linearly from min_conf to 100
    - Hard caps: min $2, max 40% of balance

    Returns dict with: amount, qty_pct, kelly_f, atr_pct, reason
    """
    if usdt < min_trade:
        return {"amount": 0, "qty_pct": 0, "kelly_f": 0,
                "atr_pct": 0, "reason": f"USDT ${usdt:.2f} below min trade ${min_trade}"}

    # Estimate win rate from confidence (conservative mapping)
    win_rate = 0.35 + (confidence / 100) * 0.30   # 35% at conf=0, 65% at conf=100
    loss_rate = 1 - win_rate

    # Kelly fraction
    edge = (1 + sl_pct) / sl_pct  # reward/risk ratio
    kelly_f = (edge * win_rate - loss_rate) / edge
    kelly_f = max(0.02, min(kelly_f, 0.35))  # cap 2%–35%

    # Volatility scalar — reduce size in choppy markets
    atr_pct = calc_atr_pct(closes) if closes else 0.01
    if atr_pct > 0.03:       vol_scalar = 0.5   # very volatile — halve size
    elif atr_pct > 0.015:    vol_scalar = 0.75  # moderate volatility
    else:                     vol_scalar = 1.0   # normal volatility

    # Confidence scalar
    conf_scalar = max(0.3, confidence / 100)

    # Final position size
    raw_amount = usdt * kelly_f * vol_scalar * conf_scalar
    amount = round(max(min_trade, min(raw_amount, usdt * max_pct)), 2)

    reason = (f"Kelly={kelly_f:.2f} vol={atr_pct*100:.2f}% "
              f"vol_scalar={vol_scalar} conf={confidence}% → ${amount:.2f}")

    return {
        "amount":   amount,
        "qty_pct":  round(amount / usdt, 3) if usdt > 0 else 0,
        "kelly_f":  round(kelly_f, 3),
        "atr_pct":  round(atr_pct, 4),
        "reason":   reason,
    }


# ─────────────────────────────────────────────────────────────
# 4. FEATURE PIPELINE
# Leakage-proof indicator wrapper.
# Every feature uses STRICTLY past data by construction.
# Inspired by zostaff FeaturePipeline.
# ─────────────────────────────────────────────────────────────

class FeaturePipeline:
    """
    Computes technical features from a price series with
    guaranteed no look-ahead bias.

    Each transform receives only closes[t-lookback : t] —
    never the current bar or future bars.

    Usage:
        pipe = FeaturePipeline()
        pipe.add("rsi_14",   lambda w: _rsi(w), 15)
        pipe.add("mom_20",   lambda w: w[-1]/w[0]-1, 20)
        features = pipe.fit(closes)
        # features["rsi_14"] = RSI using only past 15 closes
    """

    def __init__(self):
        self._transforms: list = []  # (name, fn, lookback)

    def add(self, name: str, fn, lookback: int):
        """
        fn(window: list) -> float
        window = closes[i-lookback : i]  (past only, never bar i itself)
        """
        self._transforms.append((name, fn, lookback))
        return self  # chainable

    def fit(self, closes: list) -> dict:
        """
        Returns dict of feature_name -> latest value.
        Only the most recent value is returned (what we need for live trading).
        """
        results = {}
        n = len(closes)
        for name, fn, lookback in self._transforms:
            if n < lookback:
                results[name] = None
                continue
            window = closes[max(0, n - lookback): n]  # past only
            try:
                results[name] = fn(window)
            except Exception as e:
                results[name] = None
                print(f"  [FeaturePipeline] {name} error: {e}")
        return results

    def fit_series(self, closes: list) -> dict:
        """
        Returns dict of feature_name -> list of values (one per bar).
        Useful for backtesting / validation.
        """
        results = {name: [] for name, _, _ in self._transforms}
        n = len(closes)
        for i in range(n):
            for name, fn, lookback in self._transforms:
                if i < lookback:
                    results[name].append(None)
                    continue
                window = closes[i - lookback: i]  # strictly past
                try:
                    results[name].append(fn(window))
                except Exception:
                    results[name].append(None)
        return results


def build_standard_pipeline() -> FeaturePipeline:
    """
    Standard pipeline for Accra Bot crypto signals.
    All indicators are leakage-proof by construction.
    """
    def _rsi(w, period=14):
        if len(w) < period + 1:
            return 50.0
        g = l = 0.0
        for i in range(1, period + 1):
            d = w[i] - w[i - 1]
            if d > 0: g += d
            else:     l -= d
        ag, al = g / period, l / period
        for i in range(period + 1, len(w)):
            d = w[i] - w[i - 1]
            ag = (ag * (period - 1) + (d if d > 0 else 0)) / period
            al = (al * (period - 1) + (-d if d < 0 else 0)) / period
        return round(100 - 100 / (1 + ag / al), 2) if al != 0 else 100.0

    def _ema(w, period):
        if len(w) < period:
            return w[-1] if w else 0
        k = 2 / (period + 1)
        v = sum(w[:period]) / period
        for c in w[period:]:
            v = c * k + v * (1 - k)
        return v

    def _mom(w):
        return (w[-1] / w[0] - 1) * 100 if w[0] != 0 else 0

    def _vol(w):
        if len(w) < 2: return 0
        rets = [(w[i] - w[i-1]) / w[i-1] for i in range(1, len(w)) if w[i-1] != 0]
        if not rets: return 0
        mean = sum(rets) / len(rets)
        var  = sum((r - mean)**2 for r in rets) / len(rets)
        return math.sqrt(var) * math.sqrt(252 * 24)  # annualised hourly

    def _bb_pct(w, period=20):
        if len(w) < period: return 0.5
        sl = w[-period:]
        mid = sum(sl) / period
        std = math.sqrt(sum((x - mid)**2 for x in sl) / period)
        if std == 0: return 0.5
        return (w[-1] - (mid - 2*std)) / (4*std)

    def _zscore(w):
        if len(w) < 2: return 0
        mean = sum(w) / len(w)
        std  = math.sqrt(sum((x - mean)**2 for x in w) / len(w))
        return (w[-1] - mean) / std if std != 0 else 0

    pipe = FeaturePipeline()
    pipe.add("rsi_14",    lambda w: _rsi(w, 14),       16)
    pipe.add("rsi_7",     lambda w: _rsi(w, 7),        9)
    pipe.add("ema9",      lambda w: _ema(w, 9),        10)
    pipe.add("ema21",     lambda w: _ema(w, 21),       22)
    pipe.add("ema50",     lambda w: _ema(w, 50),       51)
    pipe.add("mom_20",    _mom,                        20)
    pipe.add("mom_5",     _mom,                        5)
    pipe.add("vol_20",    _vol,                        21)
    pipe.add("bb_pct",    _bb_pct,                     21)
    pipe.add("zscore_20", _zscore,                     20)
    return pipe


# ─────────────────────────────────────────────────────────────
# 5. DEFLATED SHARPE GATE
# Multiple-testing correction. Prevents trading signals that
# look good only because we scanned 50+ coins.
# After scanning N assets, the best random signal has high Sharpe
# by pure luck. This corrects for that.
# Inspired by zostaff deflated_sharpe_ratio.
# ─────────────────────────────────────────────────────────────

# Rolling attempt counter — persisted across cycles
_attempt_counter_file = os.path.expanduser("~/accra-bot/signal_attempts.json")

def _load_attempt_count() -> int:
    try:
        with open(_attempt_counter_file) as f:
            return json.load(f).get("n", 1)
    except Exception:
        return 1

def _save_attempt_count(n: int):
    try:
        with open(_attempt_counter_file, "w") as f:
            json.dump({"n": n, "updated": datetime.now().isoformat()}, f)
    except Exception:
        pass


def _expected_max_sharpe(n_trials: int) -> float:
    """
    Expected maximum Sharpe ratio from n_trials random strategies.
    Uses Bailey-López de Prado approximation.
    E[max SR] ≈ √(2 log n) − γ / √(2 log n)
    where γ = Euler-Mascheroni constant ≈ 0.5772
    """
    if n_trials <= 1:
        return 0.0
    gamma = 0.5772156649
    log_n = math.log(max(n_trials, 2))
    return math.sqrt(2 * log_n) - gamma / math.sqrt(2 * log_n)


def deflated_sharpe_gate(returns: list, n_trials: int = None,
                          min_pvalue: float = 0.90) -> dict:
    """
    Gate a signal through the Deflated Sharpe Ratio test.

    Args:
        returns:    list of recent period returns for this signal
        n_trials:   total signals evaluated so far (loaded from file if None)
        min_pvalue: minimum DSR p-value to pass (default 0.90)

    Returns dict: passed, dsr_pvalue, observed_sharpe, threshold_sharpe, reason
    """
    if n_trials is None:
        n_trials = _load_attempt_count()

    # Increment and save
    _save_attempt_count(n_trials + 1)

    n = len(returns)
    if n < 20:
        return {
            "passed": True,  # not enough data — allow but warn
            "dsr_pvalue": 0.5,
            "observed_sharpe": 0,
            "threshold_sharpe": 0,
            "reason": f"Insufficient data ({n} bars) — gate bypassed"
        }

    mean_r = sum(returns) / n
    variance = sum((r - mean_r)**2 for r in returns) / n
    std_r = math.sqrt(variance) if variance > 0 else 1e-9

    # Annualised Sharpe (hourly bars → ×√8760)
    sharpe = (mean_r / std_r) * math.sqrt(8760)

    # Skewness
    skew = sum((r - mean_r)**3 for r in returns) / (n * std_r**3) if std_r > 0 else 0

    # Excess kurtosis
    kurt = sum((r - mean_r)**4 for r in returns) / (n * std_r**4) - 3 if std_r > 0 else 0

    # Expected max Sharpe under null (per-period)
    sr_per = sharpe / math.sqrt(8760)
    sr0    = _expected_max_sharpe(n_trials) / math.sqrt(8760)

    # DSR numerator / denominator
    numerator   = (sr_per - sr0) * math.sqrt(n - 1)
    denom_inner = 1 - skew * sr_per + (kurt - 1) / 4 * sr_per**2
    denominator = math.sqrt(max(denom_inner, 1e-9))

    z = numerator / denominator if denominator > 0 else 0

    # CDF approximation (error function)
    def _norm_cdf(x):
        t = 1 / (1 + 0.2316419 * abs(x))
        poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
               + t * (-1.821255978 + t * 1.330274429))))
        p = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x**2) * poly
        return p if x >= 0 else 1 - p

    dsr_pvalue = _norm_cdf(z)

    passed = dsr_pvalue >= min_pvalue
    threshold_sharpe = _expected_max_sharpe(n_trials)

    reason = (
        f"Sharpe={sharpe:.2f} vs threshold={threshold_sharpe:.2f} "
        f"(n_trials={n_trials}) DSR={dsr_pvalue:.2f} → {'PASS' if passed else 'REJECT'}"
    )

    if not passed:
        print(f"  [DSR GATE] REJECTED — {reason}")
    else:
        print(f"  [DSR GATE] PASSED  — {reason}")

    return {
        "passed":           passed,
        "dsr_pvalue":       round(dsr_pvalue, 3),
        "observed_sharpe":  round(sharpe, 2),
        "threshold_sharpe": round(threshold_sharpe, 2),
        "skew":             round(skew, 2),
        "excess_kurtosis":  round(kurt, 2),
        "n_trials":         n_trials,
        "reason":           reason,
    }


def returns_from_closes(closes: list, signal_position: int = 1) -> list:
    """
    Convert price closes to returns for the DSR gate.
    signal_position: +1 = long, -1 = short
    Returns are shifted by 1 bar (no look-ahead).
    """
    if len(closes) < 2:
        return []
    raw = [(closes[i] - closes[i-1]) / closes[i-1]
           for i in range(1, len(closes))]
    return [r * signal_position for r in raw]


# ─────────────────────────────────────────────────────────────
# HELPER — Telegram notify (used by kill-switch)
# ─────────────────────────────────────────────────────────────

def _telegram_notify(message: str):
    token = os.getenv("TELEGRAM_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT",  "")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message, "parse_mode": "HTML"},
            timeout=8,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# UPGRADE REPORT — prints status of all 5 modules on import
# ─────────────────────────────────────────────────────────────

def print_upgrade_status():
    print("\n" + "="*55)
    print("  ACCRA BOT UPGRADES (zostaff-inspired)")
    print("="*55)
    print("  [OK] 1. KillSwitch      — loss limits + data staleness")
    print("  [OK] 2. CriticAgent     — adversarial AI trade review")
    print("  [OK] 3. RiskSizer       — Kelly + volatility sizing")
    print("  [OK] 4. FeaturePipeline — leakage-proof indicators")
    print("  [OK] 5. DeflatedSharpe  — multiple-testing gate")
    n = _load_attempt_count()
    sr0 = round(_expected_max_sharpe(n), 2)
    print(f"\n  Signal attempts tracked: {n}")
    print(f"  Current SR threshold:    {sr0}")
    print("="*55 + "\n")
