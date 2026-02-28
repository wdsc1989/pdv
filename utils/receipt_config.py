"""
Carrega e salva configuração de layout do recibo para impressão.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "receipt_config.json"

DEFAULTS = {
    "paper_width_mm": 80,
    "margin_mm": 5,
    "font_size_pt": 10,
    "header_text": "LOJA DE ROUPAS",
    "subheader_text": "Extrato nao fiscal",
    "footer_text": "Obrigado pela preferencia!",
    "copies": 1,
}


def load_receipt_config() -> dict:
    """Retorna a configuração do recibo (merge com defaults)."""
    out = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            out.update(data)
        except Exception:
            pass
    return out


def save_receipt_config(config: dict) -> None:
    """Salva a configuração do recibo em config/receipt_config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
