from datetime import date, datetime

import locale

# Tenta usar locale pt_BR para formatação monetária, se disponível
try:
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
except locale.Error:
    # Em alguns ambientes Windows, o locale pode ter outro nome ou não estar disponível.
    pass


def format_currency(value: float) -> str:
    """
    Formata um número como moeda em reais.
    """
    try:
        return locale.currency(value, grouping=True)
    except Exception:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_date(d: date | datetime) -> str:
    """
    Formata datas no padrão brasileiro.
    """
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y %H:%M")
    return d.strftime("%d/%m/%Y")

