"""
Página de impressão do recibo não fiscal.
Abre com o sale_id em session_state (redirecionado da página de Vendas).
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import streamlit.components.v1 as components

from config.database import SessionLocal
from models.product import Product
from models.sale import Sale, SaleItem
from services.auth_service import AuthService
from utils.navigation import show_sidebar
from utils.receipt_builder import build_receipt_html
from utils.receipt_config import load_receipt_config


st.set_page_config(
    page_title="Imprimir recibo",
    page_icon="🖨️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

AuthService.require_roles(["admin", "gerente", "vendedor"])
show_sidebar()

sale_id = st.session_state.pop("print_receipt_sale_id", None)

if sale_id is None:
    st.info("Nenhum recibo para imprimir. Finalize uma venda em **Vendas** marcando **Imprimir extrato não fiscal**.")
    if st.button("Voltar às Vendas"):
        st.switch_page("pages/4_Vendas.py")
    st.stop()

db = SessionLocal()
try:
    venda = db.get(Sale, sale_id)
    if not venda:
        st.warning("Venda não encontrada.")
        st.stop()

    itens = (
        db.query(SaleItem, Product)
        .join(Product, Product.id == SaleItem.product_id)
        .filter(SaleItem.sale_id == venda.id)
        .all()
    )
    config = load_receipt_config()
    html = build_receipt_html(venda, itens, config)
    # Altura suficiente para o recibo + botão
    components.html(html, height=500, scrolling=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Voltar às Vendas", type="primary", use_container_width=True):
            st.switch_page("pages/4_Vendas.py")
finally:
    db.close()
