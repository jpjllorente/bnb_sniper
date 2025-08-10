import json
import os

def _load_abi(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"ABI no encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_erc20_abi() -> dict:
    # Nombre correcto del archivo en tu repo
    return _load_abi("abis/erc20_abi.json")

def load_pancake_router_abi() -> dict:
    return _load_abi("abis/pancake_router_abi.json")
