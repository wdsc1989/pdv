import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from dateutil.relativedelta import relativedelta
from sqlalchemy import func

from config.database import SessionLocal
from models.account_payable import AccountPayable
from models.cash_session import CashSession
from models.product import Product
from models.sale import Sale, SaleItem
from models.stock_entry import StockEntry
from services.auth_service import AuthService
from utils.formatters import format_currency, format_date
from utils.navigation import show_sidebar


st.set_page_config(page_title="Relatórios", page_icon="📈", layout="wide")

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📈 Relatórios</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Período: totais, lucro, produtos mais vendidos e caixa.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")


def get_period(tipo: str) -> tuple[date, date]:
    hoje = date.today()
    if tipo == "Diário":
        return hoje, hoje
    if tipo == "Semanal":
        inicio = hoje - timedelta(days=6)
        return inicio, hoje
    if tipo == "Mensal":
        inicio = hoje.replace(day=1)
        return inicio, hoje
    # Geral - usa um intervalo grande
    return date(2000, 1, 1), hoje


st.subheader("Filtros")
col_tipo, col1, col2 = st.columns([1, 1, 1])
with col_tipo:
    tipo = st.selectbox("Período", options=["Diário", "Semanal", "Mensal", "Geral"], help="Diário = hoje; Semanal = últimos 7 dias; Mensal = mês atual; Geral = tudo.")
inicio_padrao, fim_padrao = get_period(tipo)
with col1:
    data_inicio = st.date_input("Data inicial", value=inicio_padrao)
with col2:
    data_fim = st.date_input("Data final", value=fim_padrao)

st.markdown("---")
st.subheader("Resumo do período")

db = SessionLocal()

try:
    # Vendas no período
    vendas_query = (
        db.query(
            func.coalesce(func.sum(Sale.total_vendido), 0.0),
            func.coalesce(func.sum(Sale.total_lucro), 0.0),
            func.coalesce(func.sum(Sale.total_pecas), 0),
        )
        .filter(Sale.data_venda >= data_inicio)
        .filter(Sale.data_venda <= data_fim)
        .filter(Sale.status != "cancelada")
    )
    total_vendido, total_lucro, total_pecas = vendas_query.one()

    # KPIs adicionais
    num_vendas = (
        db.query(func.count(Sale.id))
        .filter(Sale.data_venda >= data_inicio)
        .filter(Sale.data_venda <= data_fim)
        .filter(Sale.status != "cancelada")
        .scalar()
    )
    margem = (total_lucro / total_vendido * 100) if total_vendido > 0 else 0.0
    ticket_medio = (total_vendido / num_vendas) if num_vendas and num_vendas > 0 else 0.0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total vendido", format_currency(total_vendido))
    with col2:
        st.metric("Total de lucro", format_currency(total_lucro))
    with col3:
        st.metric("Margem (%)", f"{margem:.2f}")
    with col4:
        st.metric("Peças vendidas", int(total_pecas))

    col5, col6 = st.columns(2)
    with col5:
        st.metric("Nº de vendas", num_vendas or 0)
    with col6:
        st.metric("Ticket médio", format_currency(ticket_medio))

    st.markdown("---")

    # Valor de estoque (snapshot atual)
    st.subheader("Valor de estoque (atual)")
    produtos_estoque = db.query(Product).all()
    valor_estoque_custo = sum(
        (p.preco_custo or 0) * (p.estoque_atual or 0) for p in produtos_estoque
    )
    valor_estoque_venda = sum(
        (p.preco_venda or 0) * (p.estoque_atual or 0) for p in produtos_estoque
    )
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.metric("Estoque a custo", format_currency(valor_estoque_custo))
    with col_e2:
        st.metric("Estoque a venda", format_currency(valor_estoque_venda))

    st.markdown("---")
    st.subheader("Entradas de estoque no período")

    entradas = (
        db.query(StockEntry, Product.codigo, Product.nome)
        .join(Product, Product.id == StockEntry.product_id)
        .filter(StockEntry.data_entrada >= data_inicio)
        .filter(StockEntry.data_entrada <= data_fim)
        .order_by(StockEntry.data_entrada.desc(), StockEntry.id.desc())
        .all()
    )
    if not entradas:
        st.info("Nenhuma entrada de estoque registrada no período.")
    else:
        total_entradas = sum(e[0].quantity for e in entradas)
        st.metric("Total de unidades (entradas no período)", f"{total_entradas:.0f}")
        linhas_ent = []
        for entry, codigo, nome in entradas:
            linhas_ent.append(
                {
                    "Data": entry.data_entrada.strftime("%d/%m/%Y"),
                    "Código": codigo,
                    "Produto": nome,
                    "Quantidade": entry.quantity,
                    "Observação": entry.observacao or "",
                }
            )
        st.dataframe(linhas_ent, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Produtos mais vendidos
    st.subheader("Produtos mais vendidos")
    top_itens = (
        db.query(
            Product.codigo,
            Product.nome,
            func.coalesce(func.sum(SaleItem.quantidade), 0.0).label("qtd"),
            func.coalesce(
                func.sum(SaleItem.quantidade * SaleItem.preco_unitario), 0.0
            ).label("receita"),
            func.coalesce(
                func.sum(SaleItem.lucro_item), 0.0
            ).label("lucro"),
        )
        .join(Product, Product.id == SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.data_venda >= data_inicio)
        .filter(Sale.data_venda <= data_fim)
        .filter(Sale.status != "cancelada")
        .group_by(Product.codigo, Product.nome)
        .order_by(func.sum(SaleItem.quantidade).desc())
        .limit(10)
        .all()
    )
    if not top_itens:
        st.info("Nenhuma venda registrada no período.")
    else:
        df_top = pd.DataFrame(
            [
                {
                    "Código": cod,
                    "Nome": nome,
                    "Quantidade vendida": qtd,
                    "Receita": receita,
                    "Lucro": lucro,
                }
                for cod, nome, qtd, receita, lucro in top_itens
            ]
        )
        df_top["Receita"] = df_top["Receita"].apply(format_currency)
        df_top["Lucro"] = df_top["Lucro"].apply(format_currency)
        st.dataframe(df_top, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Sessões de caixa no período")

    sessoes = (
        db.query(CashSession)
        .filter(
            func.date(CashSession.data_abertura) >= data_inicio,
            func.date(CashSession.data_abertura) <= data_fim,
        )
        .order_by(CashSession.data_abertura)
        .all()
    )
    if not sessoes:
        st.info("Nenhuma sessão de caixa no período.")
    else:
        linhas_s = []
        for s in sessoes:
            total_s = (
                db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
                .filter(Sale.cash_session_id == s.id)
                .filter(Sale.status != "cancelada")
                .scalar()
            )
            linhas_s.append(
                {
                    "ID": s.id,
                    "Abertura": format_date(s.data_abertura),
                    "Fechamento": format_date(s.data_fechamento)
                    if s.data_fechamento
                    else "-",
                    "Valor abertura": format_currency(s.valor_abertura),
                    "Valor fechamento": format_currency(s.valor_fechamento)
                    if s.valor_fechamento is not None
                    else "-",
                    "Status": s.status,
                    "Total vendas sessão": format_currency(total_s),
                }
            )
        st.dataframe(linhas_s, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Contas a pagar no período (por vencimento)")

    contas = (
        db.query(AccountPayable)
        .filter(AccountPayable.data_vencimento >= data_inicio)
        .filter(AccountPayable.data_vencimento <= data_fim)
        .order_by(AccountPayable.data_vencimento)
        .all()
    )
    if not contas:
        st.info("Nenhuma conta a pagar no período.")
    else:
        total_abertas = 0.0
        total_pagas = 0.0
        linhas_c = []
        for c in contas:
            c.update_status()
            if c.status == "paga":
                total_pagas += c.valor
            else:
                total_abertas += c.valor
            linhas_c.append(
                {
                    "Fornecedor": c.fornecedor,
                    "Vencimento": format_date(c.data_vencimento),
                    "Pagamento": format_date(c.data_pagamento)
                    if c.data_pagamento
                    else "-",
                    "Valor": format_currency(c.valor),
                    "Status": c.status,
                }
            )
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total em aberto", format_currency(total_abertas))
        with col2:
            st.metric("Total pagas", format_currency(total_pagas))
        st.dataframe(linhas_c, use_container_width=True, hide_index=True)

finally:
    db.close()

