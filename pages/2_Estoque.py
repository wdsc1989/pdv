import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.product import Product
from models.product_category import ProductCategory
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar


st.set_page_config(page_title="Estoque", page_icon="📊", layout="wide")

AuthService.require_auth()
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📊 Estoque</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Quantidades em estoque. Abaixo do mínimo em destaque.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    # Filtros
    categorias = (
        db.execute(
            select(ProductCategory)
            .where(ProductCategory.ativo.is_(True))
            .order_by(ProductCategory.nome)
        )
        .scalars()
        .all()
    )
    cat_opcoes = ["Todas as categorias"] + [c.nome for c in categorias]

    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        busca_produto = st.text_input(
            "Buscar produto (nome ou código)",
            placeholder="Ex: vestido, VEST001, jeans...",
        ).strip().lower()
    with col_f2:
        cat_escolhida = st.selectbox("Categoria", options=cat_opcoes)
    with col_f3:
        status_filtro = st.selectbox(
            "Status",
            options=["Apenas ativos", "Todos", "Apenas inativos"],
            index=0,
        )

    query = select(Product).order_by(Product.nome)
    if status_filtro == "Apenas ativos":
        query = query.filter(Product.ativo.is_(True))
    elif status_filtro == "Apenas inativos":
        query = query.filter(Product.ativo.is_(False))

    produtos = db.execute(query).scalars().all()

    # Filtro por categoria
    if cat_escolhida != "Todas as categorias":
        cat_obj = next((c for c in categorias if c.nome == cat_escolhida), None)
        if cat_obj:
            produtos = [p for p in produtos if p.categoria_id == cat_obj.id]

    # Filtro por produto (nome ou código)
    if busca_produto:
        produtos = [
            p
            for p in produtos
            if busca_produto in (p.nome or "").lower()
            or busca_produto in (p.codigo or "").lower()
        ]

    if not produtos:
        st.info("Nenhum produto encontrado com os filtros atuais.")
    else:
        linhas = []
        baixo = []
        valor_estoque_custo = 0.0
        valor_estoque_venda = 0.0

        valor_lucro_total = 0.0
        for p in produtos:
            estoque = float(p.estoque_atual or 0)
            estoque_min = float(p.estoque_minimo or 0)
            custo = p.preco_custo or 0
            venda = p.preco_venda or 0
            lucro_un = venda - custo
            lucro_estoque = lucro_un * estoque
            valor_estoque_custo += custo * estoque
            valor_estoque_venda += venda * estoque
            valor_lucro_total += lucro_estoque

            linha = {
                "Código": p.codigo,
                "Nome": p.nome,
                "Categoria": p.categoria or "",
                "Marca": p.marca or "",
                "Estoque": estoque,
                "Estoque mín.": estoque_min,
                "Preço venda": format_currency(venda),
                "Lucro un.": format_currency(lucro_un),
                "Lucro (estoque)": format_currency(lucro_estoque),
            }
            linhas.append(linha)
            if p.estoque_minimo is not None and p.estoque_atual <= p.estoque_minimo:
                baixo.append(linha)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total de produtos", len(produtos))
        with col2:
            st.metric("Em alerta (estoque baixo)", len(baixo))
        with col3:
            st.metric("Valor estoque (custo)", format_currency(valor_estoque_custo))
        with col4:
            st.metric("Valor estoque (venda)", format_currency(valor_estoque_venda))
        with col5:
            st.metric("Lucro (estoque)", format_currency(valor_lucro_total))

        if baixo:
            st.markdown("---")
            st.subheader("⚠️ Produtos com estoque baixo")
            st.caption("Estes produtos estão com quantidade igual ou abaixo do mínimo definido.")
            st.dataframe(baixo, use_container_width=True, hide_index=True)
            st.markdown("---")

        st.subheader("Todos os produtos")
        st.dataframe(linhas, use_container_width=True, hide_index=True)
finally:
    db.close()

