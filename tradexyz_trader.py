import os, logging, requests
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils.constants import MAINNET_API_URL

log = logging.getLogger(__name__)

HL_KEY    = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
HL_WALLET = os.getenv("HYPERLIQUID_WALLET", "")

# ALL non-crypto assets — bot picks best one automatically
STOCKS      = {"TSLA","NVDA","AAPL","META","GOOGL","AMZN","MSFT","COIN",
               "HOOD","INTC","PLTR","ORCL","AMD","MU","MSTR","NFLX",
               "COST","LLY","TSM","RIVN","BABA","SMSN","CRWV","HIMS",
               "DKNG","SNDK","CRCL","SKHX","USAR","HYUNDAI","EWY","EWJ",
               "URNM","GME","HIMS","DKNG"}
INDICES     = {"SP500","XYZ100","KR200","JP225"}
COMMODITIES = {"GOLD","SILVER","CL","COPPER","NATGAS","PLATINUM","PALLADIUM","BRENTOIL"}
FOREX       = {"EUR","JPY","DXY"}
ALL_XYZ     = STOCKS | INDICES | COMMODITIES | FOREX

# Priority order for auto-selection (tested working first)
AUTO_PICKS = {
    "stock":     ["TSLA","AAPL","NVDA","META","PLTR","AMD","COIN","GOOGL","AMZN","MSFT"],
    "index":     ["SP500","XYZ100"],
    "commodity": ["SILVER","COPPER","NATGAS","CL","BRENTOIL","PLATINUM","PALLADIUM","GOLD"],
    "forex":     ["EUR","JPY"],
}

_info = None
_exch = None

def _get_clients():
    global _info, _exch
    if _info is None:
        account = Account.from_key(HL_KEY)
        _info   = Info(MAINNET_API_URL, skip_ws=True, perp_dexs=["xyz"])
        _exch   = Exchange(account, MAINNET_API_URL, perp_dexs=["xyz"])
    return _info, _exch

def _get_xyz_meta():
    r = requests.post(MAINNET_API_URL + "/info",
                      json={"type": "metaAndAssetCtxs", "dex": "xyz"},
                      timeout=10)
    r.raise_for_status()
    data = r.json()
    return {"universe": data[0].get("universe", []), "ctxs": data[1]}

def xyz_get_price(ticker: str) -> float:
    try:
        info, _ = _get_clients()
        return float(info.all_mids("xyz").get(f"xyz:{ticker}", 0))
    except Exception as e:
        log.error(f"[XYZ] Price failed {ticker}: {e}")
        return 0.0

def xyz_get_all_prices() -> dict:
    try:
        meta   = _get_xyz_meta()
        prices = {}
        for i, u in enumerate(meta["universe"]):
            name = u["name"].replace("xyz:", "")
            try:
                prices[name] = float(meta["ctxs"][i]["midPx"])
            except:
                pass
        return prices
    except Exception as e:
        log.error(f"[XYZ] All prices failed: {e}")
        return {}

def xyz_get_balance() -> float:
    try:
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState", "user": HL_WALLET},
            timeout=10)
        for b in r.json().get("balances", []):
            if b.get("coin") == "USDC":
                return float(b.get("total", 0))
        return 0.0
    except Exception as e:
        log.error(f"[XYZ] Balance failed: {e}")
        return 0.0

def xyz_get_positions() -> list:
    try:
        info, _ = _get_clients()
        state   = info.user_state(HL_WALLET)
        return [p for p in state.get("assetPositions", [])
                if "xyz:" in p.get("position", {}).get("coin", "")]
    except Exception as e:
        log.error(f"[XYZ] Positions failed: {e}")
        return []

def xyz_place_order(ticker: str, is_buy: bool, usdc_amount: float,
                    leverage: int = 3) -> dict:
    try:
        if ticker not in ALL_XYZ:
            return {"status": "skip", "msg": f"{ticker} not in allowed assets"}

        global _info, _exch
        _info = _exch = None  # fresh client for latest prices
        info, exch = _get_clients()

        price = xyz_get_price(ticker)
        if price <= 0:
            return {"status": "error", "msg": f"No price for {ticker}"}

        meta    = _get_xyz_meta()
        sz_dec  = 2
        max_lev = leverage
        for u in meta["universe"]:
            if u["name"] == f"xyz:{ticker}":
                sz_dec  = u.get("szDecimals", 2)
                max_lev = min(leverage, u.get("maxLeverage", 10))
                break

        notional = max(10.0, usdc_amount * max_lev)
        size     = round(notional / price, sz_dec)

        if price >= 1000:
            limit_px = round(price * (1.05 if is_buy else 0.95), 1)
        elif price >= 1:
            limit_px = round(price * (1.05 if is_buy else 0.95), 2)
        else:
            limit_px = round(price * (1.05 if is_buy else 0.95), 5)

        coin = f"xyz:{ticker}"
        try:
            exch.update_leverage(max_lev, coin, is_cross=False)
        except:
            pass

        # Transfer margin to isolated account (required for HIP-3)
        try:
            margin_needed = round(notional / max_lev * 1.1, 2)
            exch.update_isolated_margin(margin_needed, coin)
        except Exception as me:
            log.warning(f"[XYZ] Margin transfer warning: {me}")

        result   = exch.order(coin, is_buy, size, limit_px,
                              {"limit": {"tif": "Ioc"}})
        statuses = result.get("response", {}).get("data", {}).get("statuses", [{}])
        filled   = statuses[0].get("filled")
        error    = statuses[0].get("error")

        if error:
            log.error(f"[XYZ] Order error: {error}")
            return {"status": "error", "msg": error, "ticker": ticker}

        direction = "BUY" if is_buy else "SELL"
        log.info(f"[XYZ] {direction} {size} {ticker} @ ${price:.2f} filled={filled}")
        return {"status": "ok", "ticker": ticker, "size": size,
                "price": price, "filled": filled}

    except Exception as e:
        log.error(f"[XYZ] Order failed: {e}")
        return {"status": "error", "msg": str(e)}

def xyz_close_position(ticker: str) -> dict:
    try:
        coin = f"xyz:{ticker}"
        for p in xyz_get_positions():
            pos = p.get("position", {})
            if pos.get("coin") == coin:
                size         = abs(float(pos.get("szi", 0)))
                is_buy_close = float(pos["szi"]) < 0
                price        = xyz_get_price(ticker)
                slippage     = 1.05 if is_buy_close else 0.95
                if price >= 1000:
                    limit_px = round(price * slippage, 1)
                else:
                    limit_px = round(price * slippage, 2)
                _, exch = _get_clients()
                result  = exch.order(coin, is_buy_close, size, limit_px,
                                     {"limit": {"tif": "Ioc"}},
                                     reduce_only=True)
                return {"status": "ok", "ticker": ticker, "raw": result}
        return {"status": "no_position", "ticker": ticker}
    except Exception as e:
        log.error(f"[XYZ] Close failed: {e}")
        return {"status": "error", "msg": str(e)}

def xyz_best_pick(category: str = "all") -> str:
    """Auto-pick best liquid asset by category."""
    prices = xyz_get_all_prices()
    cats   = [category] if category != "all" else ["commodity","stock","index","forex"]
    for cat in cats:
        for ticker in AUTO_PICKS.get(cat, []):
            if prices.get(ticker, 0) > 0:
                return ticker
    return "TSLA"  # ultimate fallback

def xyz_trade(signal: str, category: str = "all", pct: float = 0.3) -> dict:
    """
    Called from bot.py after every AI signal.
    Automatically picks best asset and trades it.
    signal   : 'BUY' or 'SELL'
    category : 'stock','commodity','forex','index','all'
    pct      : fraction of balance to use (default 30%)
    """
    try:
        bal = xyz_get_balance()
        if bal < 5:
            log.info(f"[XYZ] Balance too low: ${bal:.2f}")
            return {"status": "skip", "msg": f"Balance ${bal:.2f} too low"}

        amount  = round(bal * pct, 2)
        amount  = min(amount, 20)
        is_buy  = signal.upper() == "BUY"

        # Try assets in order until one fills
        tried = []
        all_picks = (AUTO_PICKS["stock"][:3] +
                     AUTO_PICKS["commodity"][:3] +
                     AUTO_PICKS["forex"][:2] +
                     AUTO_PICKS["index"][:1])
        for t in all_picks:
            if t in tried:
                continue
            tried.append(t)
            result = xyz_place_order(t, is_buy, amount, leverage=3)
            if result.get("status") == "ok":
                log.info(f"[XYZ] Auto-trade {signal} {t} ${amount} ✅")
                return result
            else:
                log.warning(f"[XYZ] {t} failed: {result.get('msg','?')} - trying next")

        log.error("[XYZ] All assets failed")
        return {"status": "error", "msg": "All assets failed"}
    except Exception as e:
        log.error(f"[XYZ] xyz_trade failed: {e}")
        return {"status": "error", "msg": str(e)}

def xyz_test_connection() -> bool:
    try:
        bal    = xyz_get_balance()
        prices = xyz_get_all_prices()
        liquid = {k: v for k, v in prices.items() if v > 0 and k in ALL_XYZ}
        print(f"[XYZ] Connected ✅  Balance: ${bal:.2f} USDC")
        print(f"[XYZ] {len(liquid)}/{len(ALL_XYZ)} assets liquid")
        print(f"  Stocks     : {[k for k in liquid if k in STOCKS][:6]}")
        print(f"  Indices    : {[k for k in liquid if k in INDICES]}")
        print(f"  Commodities: {[k for k in liquid if k in COMMODITIES]}")
        print(f"  Forex      : {[k for k in liquid if k in FOREX]}")
        print(f"  Auto-pick BUY  → {xyz_best_pick()}")
        return True
    except Exception as e:
        print(f"[XYZ] Failed: {e}")
        return False
