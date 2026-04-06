import os, logging
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

log = logging.getLogger(__name__)

HL_KEY     = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
HL_WALLET  = os.getenv("HYPERLIQUID_WALLET", "")
HL_LEVERAGE = int(os.getenv("HL_LEVERAGE", "2"))  # default 2x

_ASSET_CACHE = {}

def _get_clients():
    if not HL_KEY or not HL_WALLET:
        raise ValueError("HYPERLIQUID keys missing in .env")
    account = Account.from_key(HL_KEY)
    info    = Info(constants.MAINNET_API_URL, skip_ws=True)
    exch    = Exchange(account, constants.MAINNET_API_URL)
    return info, exch

def _get_asset_info(info, coin):
    global _ASSET_CACHE
    if coin in _ASSET_CACHE:
        return _ASSET_CACHE[coin]
    metas    = info.meta_and_asset_ctxs()
    universe = metas[0]["universe"]
    ctxs     = metas[1]
    for i, u in enumerate(universe):
        if u["name"] == coin:
            try:
                price = float(ctxs[i]["midPx"])
            except:
                price = 0.0
            result = {"index": i, "sz_decimals": u.get("szDecimals", 4), "price": price}
            _ASSET_CACHE[coin] = result
            return result
    return None

def _round_price(price, is_buy):
    slippage = 1.05 if is_buy else 0.95
    px = price * slippage
    if price >= 1000: return round(px, 0)
    elif price >= 10: return round(px, 1)
    elif price >= 0.1: return round(px, 2)
    else: return round(px, 5)

def hl_get_balance():
    try:
        import requests
        # Unified account - check spot balance
        r = requests.post("https://api.hyperliquid.xyz/info",
            json={"type": "spotClearinghouseState", "user": HL_WALLET})
        balances = r.json().get("balances", [])
        for b in balances:
            if b.get("coin") == "USDC":
                usdc = float(b.get("total", 0))
                log.info(f"[HL] Balance: ${usdc:.2f} USDC")
                return usdc
        # Fallback to perp
        info, _ = _get_clients()
        state   = info.user_state(HL_WALLET)
        usdc    = float(state.get("marginSummary", {}).get("accountValue", 0))
        return usdc
    except Exception as e:
        log.error(f"[HL] Balance check failed: {e}")
        return 0.0

def hl_get_price(coin):
    try:
        info, _ = _get_clients()
        asset   = _get_asset_info(info, coin)
        return asset["price"] if asset else 0.0
    except Exception as e:
        log.error(f"[HL] Price fetch failed for {coin}: {e}")
        return 0.0

def hl_place_order(coin, is_buy, usdc_amount, reduce_only=False, leverage=None):
    try:
        if leverage is None:
            leverage = HL_LEVERAGE

        info, exch = _get_clients()

        # Set leverage
        if leverage > 1:
            exch.update_leverage(leverage, coin, is_cross=True)

        asset = _get_asset_info(info, coin)
        if not asset:
            return {"status": "error", "msg": f"Unknown coin: {coin}"}

        price  = asset["price"]
        sz_dec = asset["sz_decimals"]

        if price <= 0:
            return {"status": "error", "msg": f"No price for {coin}"}

        notional = usdc_amount * leverage
        if notional < 10:
            notional = 10  # enforce $10 minimum

        size     = round(notional / price, sz_dec)
        min_size = 10 ** (-sz_dec)

        if size < min_size:
            return {"status": "skip", "msg": f"Size {size} below min {min_size} for {coin}"}

        limit_px = _round_price(price, is_buy)

        result   = exch.order(
            coin, is_buy, size, limit_px,
            {"limit": {"tif": "Ioc"}},
            reduce_only=reduce_only,
        )

        statuses = result.get("response", {}).get("data", {}).get("statuses", [{}])
        filled   = statuses[0].get("filled")
        error    = statuses[0].get("error")

        if error:
            log.error(f"[HL] Order error: {error}")
            return {"status": "error", "msg": error, "coin": coin}

        direction = "BUY" if is_buy else "SELL"
        log.info(f"[HL] {direction} {size} {coin} @ ${price:.4f} filled={filled}")
        return {"status": "ok", "coin": coin, "size": size,
                "price": price, "filled": filled}

    except Exception as e:
        log.error(f"[HL] Order failed: {e}")
        return {"status": "error", "msg": str(e)}

def hl_close_position(coin):
    try:
        info, _   = _get_clients()
        state     = info.user_state(HL_WALLET)
        for p in state.get("assetPositions", []):
            pos = p.get("position", {})
            if pos.get("coin") == coin:
                size         = abs(float(pos.get("szi", 0)))
                is_buy_close = float(pos["szi"]) < 0
                price        = hl_get_price(coin)
                return hl_place_order(coin, is_buy_close,
                                      size * price, reduce_only=True, leverage=1)
        return {"status": "no_position", "coin": coin}
    except Exception as e:
        log.error(f"[HL] Close failed: {e}")
        return {"status": "error", "msg": str(e)}

def hl_get_positions():
    try:
        info, _ = _get_clients()
        state   = info.user_state(HL_WALLET)
        return state.get("assetPositions", [])
    except Exception as e:
        log.error(f"[HL] Positions fetch failed: {e}")
        return []

def hl_get_all_assets():
    try:
        info, _  = _get_clients()
        metas    = info.meta_and_asset_ctxs()
        universe = metas[0]["universe"]
        ctxs     = metas[1]
        assets   = []
        for i, u in enumerate(universe):
            try:
                price   = float(ctxs[i]["midPx"])
                sz_dec  = u.get("szDecimals", 4)
                min_usd = round(price * (10 ** (-sz_dec)), 4)
                assets.append({"coin": u["name"], "price": price,
                                "min_usd": min_usd, "sz_dec": sz_dec})
            except:
                pass
        return assets
    except Exception as e:
        log.error(f"[HL] Asset list failed: {e}")
        return []

def hl_test_connection():
    try:
        bal    = hl_get_balance()
        assets = hl_get_all_assets()
        print(f"[HL] Connected ✅  Balance: ${bal:.2f} USDC")
        print(f"[HL] {len(assets)} tradeable assets available")
        return True
    except Exception as e:
        print(f"[HL] Connection failed ❌  {e}")
        return False
