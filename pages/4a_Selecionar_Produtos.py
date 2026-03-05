"""
Página de seleção de produtos para a venda.
Acessada por "Buscar produto" na página de Vendas.
Permite adicionar produtos à sacola e voltar para vendas.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.cash_session import CashSession
from models.product import Product
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar


st.set_page_config(page_title="Buscar produto", page_icon="🔍", layout="wide")

AuthService.require_roles(["admin", "gerente", "vendedor"])
show_sidebar()

db = SessionLocal()

try:
    sessao_aberta = db.query(CashSession).filter(CashSession.status == "aberta").first()
    if not sessao_aberta:
        st.error("Não há caixa aberto. Abra o caixa em **Caixa** para liberar vendas.")
        if st.button("Voltar para Vendas"):
            st.switch_page("pages/4_Vendas.py")
        st.stop()

    produtos = (
        db.execute(
            select(Product)
            .where(Product.ativo.is_(True))
            .order_by(Product.nome)
        )
        .scalars()
        .all()
    )

    if not produtos:
        st.info("Nenhum produto cadastrado. Cadastre produtos em **Produtos** antes de vender.")
        if st.button("Voltar para Vendas"):
            st.switch_page("pages/4_Vendas.py")
        st.stop()

    if "cart_items" not in st.session_state:
        st.session_state.cart_items = []

    cart = st.session_state.cart_items
    n_itens = sum(int(item["quantidade"]) for item in cart)

    st.markdown(
        "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>🔍 Buscar produto</strong></p>"
        "<p style='margin:0; font-size:0.8rem; color:#666;'>Selecione os produtos e as quantidades. Clique em Voltar para vendas quando terminar.</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Termos para autocomplete: nomes, códigos, palavras dos nomes
    termos_busca = set()
    for p in produtos:
        if p.nome:
            termos_busca.add(p.nome.strip())
            for palavra in p.nome.lower().split():
                if len(palavra) >= 2:
                    termos_busca.add(palavra.strip(".,;:"))
        if p.codigo:
            termos_busca.add(str(p.codigo))
    opcoes_busca = ["(Todas)"] + sorted(termos_busca, key=lambda x: (x or "").lower())

    # Filtros: busca (selectbox com digitação para filtrar), categoria, fornecedor, estoque, ordenação
    categorias = sorted({p.categoria for p in produtos if p.categoria}, key=lambda x: (x or "").lower())
    marcas = sorted({p.marca for p in produtos if p.marca}, key=lambda x: (x or "").lower())

    # Linha 1: Voltar + Busca (selectbox: digite para filtrar opções, ex: "Ves" mostra "vestido")
    col_voltar, col_busca = st.columns([1, 4])
    with col_voltar:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Voltar para vendas", type="primary", use_container_width=True, key="btn_voltar_vendas"):
            st.switch_page("pages/4_Vendas.py")

    with col_busca:
        termo_sel = st.selectbox(
            "Buscar (digite para filtrar: ex. Ves → vestido)",
            options=opcoes_busca,
            key="busca_selecionar_prod",
        )
        termo = "" if termo_sel == "(Todas)" else (termo_sel or "").strip().lower()

    # Linha 2: Categoria, Fornecedor, Estoque, Ordenar
    col_cat, col_forn, col_estoque, col_ordem = st.columns(4)
    with col_cat:
        filtro_cat = st.selectbox(
            "Categoria",
            options=["Todas"] + categorias,
            key="filtro_cat_sel",
        )

    with col_forn:
        filtro_marca = st.selectbox(
            "Fornecedor",
            options=["Todas"] + marcas,
            key="filtro_marca_sel",
        )

    with col_estoque:
        filtro_estoque = st.selectbox(
            "Estoque",
            options=["Todos", "Com estoque", "Sem estoque"],
            key="filtro_estoque_sel",
        )

    with col_ordem:
        ordem = st.selectbox(
            "Ordenar por",
            options=["Nome", "Código", "Preço (menor)", "Preço (maior)", "Estoque"],
            key="ordem_sel",
        )

    # Aplica filtros
    produtos_filtrados = produtos

    if termo:
        produtos_filtrados = [
            p for p in produtos_filtrados
            if termo in (p.nome or "").lower()
            or termo in (p.codigo or "").lower()
        ]

    if filtro_cat != "Todas":
        produtos_filtrados = [p for p in produtos_filtrados if p.categoria == filtro_cat]

    if filtro_marca != "Todas":
        produtos_filtrados = [p for p in produtos_filtrados if p.marca == filtro_marca]

    if filtro_estoque == "Com estoque":
        produtos_filtrados = [p for p in produtos_filtrados if (p.estoque_atual or 0) > 0]
    elif filtro_estoque == "Sem estoque":
        produtos_filtrados = [p for p in produtos_filtrados if (p.estoque_atual or 0) <= 0]

    # Ordenação
    if ordem == "Nome":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: (p.nome or "").lower())
    elif ordem == "Código":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: (p.codigo or "").lower())
    elif ordem == "Preço (menor)":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.preco_venda or 0))
    elif ordem == "Preço (maior)":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.preco_venda or 0), reverse=True)
    elif ordem == "Estoque":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.estoque_atual or 0), reverse=True)

    if n_itens > 0:
        st.markdown(f"**Itens na sacola:** {n_itens} peça(s)")

    st.markdown("---")

    if not produtos_filtrados:
        st.info("Nenhum produto encontrado para este filtro.")
    else:
        uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
        # Grid 4 colunas
        COLS = 4
        for i in range(0, len(produtos_filtrados), COLS):
            cols = st.columns(COLS)
            for j, c in enumerate(cols):
                idx = i + j
                if idx >= len(produtos_filtrados):
                    break
                p = produtos_filtrados[idx]
                with c:
                    img_path = None
                    if p.imagem_path:
                        candidate = uploads_dir / p.imagem_path
                        if candidate.exists():
                            img_path = candidate

                    st.markdown(f"**{p.codigo}**")
                    if img_path:
                        st.image(str(img_path), width=90)
                    else:
                        st.markdown(
                            "<div style='width:90px;height:70px;background:#eee;"
                            "border-radius:4px;display:flex;align-items:center;"
                            "justify-content:center;font-size:10px;color:#999;'>"
                            "Sem imagem</div>",
                            unsafe_allow_html=True,
                        )
                    nome_safe = (p.nome or "").replace("<", "&lt;").replace(">", "&gt;")[:22]
                    if len(p.nome or "") > 22:
                        nome_safe += "..."
                    st.markdown(f"{nome_safe}")
                    st.markdown(f"**{format_currency(p.preco_venda)}**")
                    estoque = p.estoque_atual if p.estoque_atual is not None else 0
                    estoque_str = f"{estoque:.0f}" if estoque == int(estoque) else f"{estoque:.2f}"
                    st.caption(f"Estoque: {estoque_str}")

                    qtd_atual = sum(int(item["quantidade"]) for item in cart if item["product_id"] == p.id)
                    nova_qtd = st.number_input(
                        "Qtde",
                        min_value=0,
                        value=int(qtd_atual),
                        step=1,
                        key=f"qty_sel_{p.id}",
                        label_visibility="collapsed",
                    )
                    if int(nova_qtd) != qtd_atual:
                        novo_cart = list(cart)
                        if nova_qtd <= 0:
                            novo_cart = [item for item in novo_cart if item["product_id"] != p.id]
                        else:
                            for item in novo_cart:
                                if item["product_id"] == p.id:
                                    item["quantidade"] = int(nova_qtd)
                                    break
                            else:
                                novo_cart.append({
                                    "product_id": p.id,
                                    "codigo": p.codigo,
                                    "nome": p.nome,
                                    "quantidade": int(nova_qtd),
                                    "preco_venda": p.preco_venda,
                                    "preco_custo": p.preco_custo,
                                })
                        st.session_state.cart_items = novo_cart
                        st.rerun()

    st.markdown("---")
    if st.button("Voltar para vendas", type="primary", key="btn_voltar_footer"):
        st.switch_page("pages/4_Vendas.py")

finally:
    db.close()
