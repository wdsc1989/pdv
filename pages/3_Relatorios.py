import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func

from config.database import SessionLocal
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
    return date(2000, 1, 1), hoje


# Filtros
st.subheader("Filtros")
col_tipo, col1, col2 = st.columns([1, 1, 1])
with col_tipo:
    tipo = st.selectbox(
        "Período",
        options=["Diário", "Semanal", "Mensal", "Geral"],
        help="Diário = hoje; Semanal = últimos 7 dias; Mensal = mês atual; Geral = tudo.",
    )
inicio_padrao, fim_padrao = get_period(tipo)
with col1:
    data_inicio = st.date_input("Data inicial", value=inicio_padrao)
with col2:
    data_fim = st.date_input("Data final", value=fim_padrao)

# Menu de relatórios
RELATORIOS = [
    "Resumo do período",
    "Evolução de vendas",
    "Vendas por faixa horária",
    "Valor de estoque",
    "Entradas de estoque",
    "Produtos mais vendidos",
    "Sessões de caixa",
]
relatorio = st.selectbox(
    "Relatório",
    options=RELATORIOS,
    key="relatorio_escolhido",
    help="Selecione o relatório a ser exibido.",
)
st.markdown("---")

db = SessionLocal()
layout_plotly = dict(
    margin=dict(l=60, r=40, t=40, b=50),
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(size=12),
)
config_plotly = {"displayModeBar": False, "responsive": True}

try:
    if relatorio == "Resumo do período":
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

    elif relatorio == "Evolução de vendas":
        rows = (
            db.query(
                Sale.data_venda,
                func.coalesce(func.sum(Sale.total_vendido), 0.0).label("total_vendido"),
                func.coalesce(func.sum(Sale.total_lucro), 0.0).label("total_lucro"),
            )
            .filter(Sale.data_venda >= data_inicio)
            .filter(Sale.data_venda <= data_fim)
            .filter(Sale.status != "cancelada")
            .group_by(Sale.data_venda)
            .order_by(Sale.data_venda)
            .all()
        )
        if not rows:
            st.info("Nenhuma venda no período.")
        else:
            df = pd.DataFrame(
                [
                    {
                        "Data": r.data_venda.strftime("%d/%m/%Y"),
                        "Faturamento": float(r.total_vendido),
                        "Lucro": float(r.total_lucro),
                    }
                    for r in rows
                ]
            )
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["Data"],
                    y=df["Faturamento"],
                    name="Faturamento",
                    mode="lines+markers",
                    line=dict(width=2),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["Data"],
                    y=df["Lucro"],
                    name="Lucro",
                    mode="lines+markers",
                    line=dict(width=2),
                )
            )
            fig.update_layout(
                **layout_plotly,
                yaxis_title="Valor (R$)",
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig, use_container_width=True, config=config_plotly)

    elif relatorio == "Vendas por faixa horária":
        sales = (
            db.query(Sale.created_at, Sale.total_vendido)
            .filter(Sale.data_venda >= data_inicio)
            .filter(Sale.data_venda <= data_fim)
            .filter(Sale.status != "cancelada")
            .all()
        )
        if not sales:
            st.info("Nenhuma venda no período.")
        else:
            by_hour = {}
            for s in sales:
                h = s.created_at.hour if s.created_at else 0
                by_hour[h] = by_hour.get(h, 0) + (s.total_vendido or 0)
            hours = list(range(24))
            values = [by_hour.get(h, 0) for h in hours]
            labels = [f"{h:02d}h" for h in hours]
            fig = go.Figure(
                data=[go.Bar(x=labels, y=values, name="Faturamento", marker=dict(line=dict(width=0)))],
            )
            fig.update_layout(
                **layout_plotly,
                xaxis_title="Horário",
                yaxis_title="Faturamento (R$)",
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig, use_container_width=True, config=config_plotly)

    elif relatorio == "Valor de estoque":
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

    elif relatorio == "Entradas de estoque":
        # Gráfico por dia
        agg_entradas = (
            db.query(
                StockEntry.data_entrada,
                func.coalesce(func.sum(StockEntry.quantity), 0).label("qtd"),
            )
            .filter(StockEntry.data_entrada >= data_inicio)
            .filter(StockEntry.data_entrada <= data_fim)
            .group_by(StockEntry.data_entrada)
            .order_by(StockEntry.data_entrada)
            .all()
        )
        if agg_entradas:
            df_ent = pd.DataFrame(
                [
                    {"Data": r.data_entrada.strftime("%d/%m"), "Quantidade": float(r.qtd)}
                    for r in agg_entradas
                ]
            )
            fig = px.bar(
                df_ent,
                x="Data",
                y="Quantidade",
                labels=dict(Quantidade="Unidades"),
                text_auto=".0f",
            )
            fig.update_traces(marker_line=dict(width=0))
            fig.update_layout(**layout_plotly, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        # Tabela
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
            linhas_ent = [
                {
                    "Data": entry.data_entrada.strftime("%d/%m/%Y"),
                    "Código": codigo,
                    "Produto": nome,
                    "Quantidade": entry.quantity,
                    "Observação": entry.observacao or "",
                }
                for entry, codigo, nome in entradas
            ]
            st.dataframe(linhas_ent, use_container_width=True, hide_index=True)

    elif relatorio == "Produtos mais vendidos":
        top_itens = (
            db.query(
                Product.codigo,
                Product.nome,
                func.coalesce(func.sum(SaleItem.quantidade), 0.0).label("qtd"),
                func.coalesce(
                    func.sum(SaleItem.quantidade * SaleItem.preco_unitario), 0.0
                ).label("receita"),
                func.coalesce(func.sum(SaleItem.lucro_item), 0.0).label("lucro"),
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
            # Gráfico de barras horizontais (por quantidade)
            fig = px.bar(
                df_top,
                y="Nome",
                x="Quantidade vendida",
                orientation="h",
                labels=dict(Nome="Produto", Quantidade_vendida="Quantidade vendida"),
                text_auto=".0f",
            )
            fig.update_traces(marker_line=dict(width=0))
            fig.update_layout(**layout_plotly, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True, config=config_plotly)
            # Tabela
            df_display = df_top.copy()
            df_display["Receita"] = df_display["Receita"].apply(format_currency)
            df_display["Lucro"] = df_display["Lucro"].apply(format_currency)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

    else:  # Sessões de caixa
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

finally:
    db.close()
