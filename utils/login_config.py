"""
Carrega e salva configuração da tela de login (título, subtítulo, exibir logo).
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "login_config.json"

DEFAULTS = {
    "login_title": "🔐 PDV - Loja de Roupas",
    "login_subtitle": "Sistema de Ponto de Venda para loja de roupas",
    "login_show_logo": True,
    "login_logo_width": 280,
}


def load_login_config() -> dict:
    """Retorna a configuração da tela de login (merge com defaults)."""
    out = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            out.update(data)
        except Exception:
            pass
    return out


def save_login_config(config: dict) -> None:
    """Salva a configuração da tela de login em config/login_config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
