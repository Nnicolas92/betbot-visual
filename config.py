"""
config.py — lee credenciales del archivo .env
Si no existe .env, pide las claves por consola una sola vez.
"""
import os
from pathlib import Path

def _load_env():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

def get_cred(casa_key: str) -> dict:
    """Devuelve {user, password} para la casa indicada."""
    mapping = {
        "1": ("BET365_USER",    "BET365_PASS"),
        "2": ("BOOKMAKER_USER", "BOOKMAKER_PASS"),
        "3": ("BETSSON_USER",   "BETSSON_PASS"),
    }
    u_key, p_key = mapping.get(casa_key, ("", ""))
    user = os.environ.get(u_key, "")
    pwd  = os.environ.get(p_key, "")
    return {"user": user, "password": pwd}
