# services/market_service.py
from __future__ import annotations
import requests
from utils.log_config import log_function

class MarketService:
    """
    Servicio mínimo para obtener el precio actual por pair_address en BSC.
    """
    BASE = "https://api.dexscreener.com/latest/dex/pairs/bsc"

    @log_function
    def get_price_native_bnb(self, pair_address: str) -> float | None:
        url = f"{self.BASE}/{pair_address}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json().get("pair")
        if not data:
            return None
        # DexScreener publica 'priceNative' y 'priceUsd'
        price_native = data.get("priceNative")
        try:
            return float(price_native) if price_native is not None else None
        except:
            return None
