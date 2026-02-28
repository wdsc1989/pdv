"""
Gera HTML do recibo não fiscal para impressão, conforme config de layout.
"""
from utils.formatters import format_currency
from utils.receipt_config import load_receipt_config


def build_receipt_html(sale, itens_with_products: list, config: dict = None) -> str:
    """
    sale: objeto Sale com id, data_venda, total_vendido, total_pecas, tipo_pagamento.
    itens_with_products: lista de (SaleItem, Product) para cada item.
    config: dict de layout (ou None para usar load_receipt_config()).
    Retorna HTML completo (documento) para exibir em iframe e imprimir.
    """
    if config is None:
        config = load_receipt_config()
    w_mm = config.get("paper_width_mm", 80)
    margin_mm = config.get("margin_mm", 5)
    font_pt = config.get("font_size_pt", 10)
    header = (config.get("header_text") or "").strip()
    subheader = (config.get("subheader_text") or "Extrato nao fiscal").strip()
    footer = (config.get("footer_text") or "").strip()

    # Conteúdo do recibo
    linhas = []
    linhas.append(f"<div class='header'>{header}</div>")
    linhas.append(f"<div class='subheader'>{subheader}</div>")
    linhas.append(f"<div class='line'>Venda #{sale.id} &nbsp; {sale.data_venda.strftime('%d/%m/%Y')} &nbsp; {sale.tipo_pagamento or '-'}</div>")
    linhas.append("<div class='line'>--------------------------------</div>")
    for it, prod in itens_with_products:
        nome = (prod.nome or "-")[:28]
        qtd = int(it.quantidade or 0)
        preco = it.preco_unitario or 0
        subtotal = it.subtotal or 0
        linhas.append(f"<div class='line'>{nome}</div>")
        linhas.append(f"<div class='line'>{qtd} x {format_currency(preco)} = {format_currency(subtotal)}</div>")
    linhas.append("<div class='line'>--------------------------------</div>")
    linhas.append(f"<div class='line total'>Total: {format_currency(sale.total_vendido or 0)}</div>")
    linhas.append(f"<div class='line'>Peças: {sale.total_pecas or 0}</div>")
    if footer:
        linhas.append(f"<div class='footer'>{footer}</div>")

    body_content = "\n".join(linhas)
    width_px = max(200, min(400, w_mm * 3.78))  # aprox 80mm ~ 302px

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Recibo #{sale.id}</title>
<style>
  body {{
    width: {w_mm}mm;
    max-width: {width_px}px;
    margin: {margin_mm}mm auto;
    font-family: monospace, sans-serif;
    font-size: {font_pt}pt;
    padding: 8px;
    background: #fff;
    color: #000;
  }}
  .header {{ text-align: center; font-weight: bold; margin-bottom: 4px; }}
  .subheader {{ text-align: center; font-size: 0.9em; margin-bottom: 8px; }}
  .line {{ margin: 2px 0; word-break: break-word; }}
  .total {{ font-weight: bold; margin-top: 6px; }}
  .footer {{ text-align: center; margin-top: 12px; font-size: 0.9em; }}
  .no-print {{ margin-top: 12px; text-align: center; }}
  .no-print button {{
    padding: 8px 16px;
    font-size: 14px;
    cursor: pointer;
    background: #1a73e8;
    color: #fff;
    border: none;
    border-radius: 4px;
  }}
  @media print {{
    body * {{ visibility: hidden; }}
    body, .receipt-content, .receipt-content * {{ visibility: visible; }}
    .receipt-content {{ position: absolute; left: 0; top: 0; width: 100%; }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>
<div class="receipt-content">
{body_content}
</div>
<div class="no-print">
  <button type="button" onclick="window.print();">Imprimir</button>
</div>
</body>
</html>"""
    return html
