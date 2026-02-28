"""
Página de vendas e ajuste de estoque de acessórios.
Controle por preço + quantidade (tabelas accessory_stock e accessory_sales).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import init_db, SessionLocal
from models.accessory import AccessorySale, AccessoryStock, AccessoryStockEntry
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar


st.set_page_config(page_title="Acessórios", page_icon="💎", layout="wide")

AuthService.require_auth()
show_sidebar()

# Garante que as tabelas de acessórios existam (ex.: app iniciado antes da migração)
init_db()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>💎 Acessórios</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Vendas e ajuste de estoque por preço. Controle: quantidade de peças por valor.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    tab_venda, tab_ajuste = st.tabs(["Venda", "Ajuste de estoque"])

    with tab_venda:
        st.subheader("Registrar venda")
        st.caption("Selecione o preço e a quantidade vendida. O estoque será baixado e a venda registrada no histórico.")

        estoque_venda = (
            db.execute(
                select(AccessoryStock).where(AccessoryStock.quantidade > 0).order_by(AccessoryStock.preco)
            )
            .scalars().all()
        )
        if not estoque_venda:
            st.info("Nenhum acessório em estoque. Use a aba **Ajuste de estoque** para cadastrar preços e quantidades.")
        else:
            opcoes_venda = [
                f"{format_currency(row.preco)} — {int(row.quantidade)} peças"
                for row in estoque_venda
            ]
            escolha_venda = st.selectbox(
                "Preço / estoque",
                options=opcoes_venda,
                index=0,
                key="select_venda",
            )
            idx_venda = opcoes_venda.index(escolha_venda)
            row_venda = estoque_venda[idx_venda]
            qtd_max = int(row_venda.quantidade)
            qtd_vender = st.number_input(
                "Quantidade a vender",
                min_value=1,
                max_value=max(1, qtd_max),
                value=1,
                key="qtd_vender",
            )
            if st.button("Registrar venda", type="primary", key="btn_venda"):
                if qtd_vender > row_venda.quantidade:
                    st.error("Quantidade maior que o estoque disponível.")
                else:
                    row_venda.quantidade -= qtd_vender
                    venda = AccessorySale(
                        data_venda=date.today(),
                        preco=row_venda.preco,
                        quantidade=qtd_vender,
                    )
                    db.add(venda)
                    db.commit()
                    st.success(
                        f"Venda registrada: {qtd_vender} peça(s) a {format_currency(row_venda.preco)}. "
                        f"Estoque restante: {row_venda.quantidade:.0f}."
                    )
                    st.rerun()

        st.markdown("---")
        st.subheader("Vendas registradas")
        st.caption("Consulte as vendas por período e filtre por status de repasse.")

        hoje = date.today()
        col_per, col_rep = st.columns(2)
        with col_per:
            periodo = st.selectbox(
                "Período",
                options=["Hoje", "Últimos 7 dias", "Últimos 15 dias", "Últimos 30 dias", "Este mês", "Personalizado"],
                index=1,
                key="periodo_acess",
            )
        with col_rep:
            filtro_repasse = st.selectbox(
                "Repasse",
                options=["Todas", "Pendentes de repasse", "Já repassadas"],
                index=0,
                key="filtro_repasse",
                help="Pendentes: ainda não repassou 50% ao fornecedor. Já repassadas: repasse marcado.",
            )
        if periodo == "Hoje":
            data_inicio_ac = hoje
            data_fim_ac = hoje
        elif periodo == "Últimos 7 dias":
            data_inicio_ac = hoje - timedelta(days=6)
            data_fim_ac = hoje
        elif periodo == "Últimos 15 dias":
            data_inicio_ac = hoje - timedelta(days=14)
            data_fim_ac = hoje
        elif periodo == "Últimos 30 dias":
            data_inicio_ac = hoje - timedelta(days=29)
            data_fim_ac = hoje
        elif periodo == "Este mês":
            data_inicio_ac = hoje.replace(day=1)
            data_fim_ac = hoje
        else:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                data_inicio_ac = st.date_input("Data inicial", value=hoje - timedelta(days=29), key="di_acess")
            with col_d2:
                data_fim_ac = st.date_input("Data final", value=hoje, key="df_acess")
            if data_inicio_ac > data_fim_ac:
                data_inicio_ac, data_fim_ac = data_fim_ac, data_inicio_ac

        vendas_ac = (
            db.execute(
                select(AccessorySale)
                .where(AccessorySale.data_venda >= data_inicio_ac)
                .where(AccessorySale.data_venda <= data_fim_ac)
                .order_by(AccessorySale.data_venda.desc(), AccessorySale.id.desc())
            )
            .scalars().all()
        )
        if filtro_repasse == "Pendentes de repasse":
            vendas_ac = [v for v in vendas_ac if not getattr(v, "repasse_feito", False)]
        elif filtro_repasse == "Já repassadas":
            vendas_ac = [v for v in vendas_ac if getattr(v, "repasse_feito", False)]

        if not vendas_ac:
            st.info(
                "Nenhuma venda no período selecionado."
                if filtro_repasse == "Todas"
                else f"Nenhuma venda {filtro_repasse.lower()} no período."
            )
        else:
            total_pecas_ac = sum(v.quantidade for v in vendas_ac)
            total_reais_ac = sum(v.preco * v.quantidade for v in vendas_ac)
            total_lucro_ac = total_reais_ac * 0.5
            total_repasse_ac = sum(
                (v.preco * v.quantidade) * 0.5 for v in vendas_ac if getattr(v, "repasse_feito", False)
            )
            total_pendente_ac = total_lucro_ac - total_repasse_ac
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("Peças vendidas (período)", f"{total_pecas_ac:.0f}")
            with col_m2:
                st.metric("Total vendido (período)", format_currency(total_reais_ac))
            with col_m3:
                st.metric("Lucro 50% (total)", format_currency(total_lucro_ac))
            with col_m4:
                st.metric("Repasse pendente (50%)", format_currency(total_pendente_ac))
            linhas_v = []
            for v in vendas_ac:
                subtotal = v.preco * v.quantidade
                lucro = subtotal * 0.5
                repasse = getattr(v, "repasse_feito", False)
                linhas_v.append({
                    "Data": v.data_venda.strftime("%d/%m/%Y"),
                    "Preço": format_currency(v.preco),
                    "Quantidade": v.quantidade,
                    "Subtotal": format_currency(subtotal),
                    "Lucro (50%)": format_currency(lucro),
                    "Repasse": "Sim" if repasse else "Não",
                })
            st.dataframe(linhas_v, use_container_width=True, hide_index=True)
            total_venda_txt = (
                f"Total: {total_pecas_ac:.0f} peças — "
                f"Total vendido: {format_currency(total_reais_ac)} — "
                f"Lucro (50%): {format_currency(total_lucro_ac)}"
            )
            st.text(total_venda_txt)

            st.markdown("**Marcar repasse ao fornecedor (50%)**")
            st.caption("Selecione uma venda e marque ou desmarque o repasse realizado.")
            opcoes_repasse = [
                f"{v.data_venda.strftime('%d/%m/%Y')} — {format_currency(v.preco)} — {v.quantidade:.0f} un — Repasse: {'Sim' if getattr(v, 'repasse_feito', False) else 'Não'}"
                for v in vendas_ac
            ]
            ids_vendas_ac = [v.id for v in vendas_ac]
            escolha_repasse = st.selectbox(
                "Venda",
                options=opcoes_repasse,
                index=0,
                key="select_repasse",
            )
            idx_rep = opcoes_repasse.index(escolha_repasse)
            venda_rep = db.get(AccessorySale, ids_vendas_ac[idx_rep])
            repasse_atual = getattr(venda_rep, "repasse_feito", False) if venda_rep else False
            if st.button("Marcar como repassado" if not repasse_atual else "Desmarcar repasse", key="btn_repasse"):
                if venda_rep:
                    venda_rep.repasse_feito = not repasse_atual
                    db.commit()
                    st.success("Repasse atualizado.")
                    st.rerun()

    with tab_ajuste:
        st.subheader("Ajuste de estoque")
        st.caption("Adicione um novo preço com quantidade ou ajuste a quantidade de um preço existente.")

        estoque_ajuste = (
            db.execute(select(AccessoryStock).order_by(AccessoryStock.preco)).scalars().all()
        )
        if estoque_ajuste:
            st.markdown("**Estoque atual**")
            linhas_aj = [
                {"Preço": format_currency(r.preco), "Quantidade": r.quantidade}
                for r in estoque_ajuste
            ]
            st.dataframe(linhas_aj, use_container_width=True, hide_index=True)
            total_pecas_estoque = sum(r.quantidade for r in estoque_ajuste)
            total_valor_estoque = sum(r.preco * r.quantidade for r in estoque_ajuste)
            total_estoque_txt = (
                f"Quantidade total: {total_pecas_estoque:.0f} peças — "
                f"Valor total: {format_currency(total_valor_estoque)}"
            )
            st.text(total_estoque_txt)
            st.markdown("---")

        modo_ajuste = st.radio(
            "Tipo de ajuste",
            options=["Ajustar preço existente", "Adicionar novo preço"],
            index=0,
            key="modo_ajuste",
        )
        if modo_ajuste == "Ajustar preço existente":
            if not estoque_ajuste:
                st.info("Não há preços cadastrados. Use **Adicionar novo preço** para criar.")
            else:
                opcoes_aj = [f"{format_currency(r.preco)} — {r.quantidade:.0f} peças" for r in estoque_ajuste]
                escolha_aj = st.selectbox("Preço a ajustar", options=opcoes_aj, key="select_ajuste")
                idx_aj = opcoes_aj.index(escolha_aj)
                row_aj = estoque_ajuste[idx_aj]
                delta = st.number_input(
                    "Quantidade a adicionar (positivo) ou remover (negativo)",
                    value=0,
                    step=1,
                    key="delta_ajuste",
                )
                if st.button("Salvar ajuste", type="primary", key="btn_ajuste"):
                    novo_total = row_aj.quantidade + delta
                    if novo_total < 0:
                        st.error("A quantidade em estoque não pode ficar negativa.")
                    else:
                        row_aj.quantidade = novo_total
                        if delta > 0:
                            ent = AccessoryStockEntry(
                                data_entrada=date.today(),
                                preco=row_aj.preco,
                                quantidade=delta,
                            )
                            db.add(ent)
                        db.commit()
                        st.success(f"Estoque atualizado: {novo_total:.0f} peças a {format_currency(row_aj.preco)}.")
                        st.rerun()
        else:
            novo_preco = st.number_input(
                "Preço (R$)",
                min_value=0.01,
                value=1.0,
                step=0.5,
                format="%.2f",
                key="novo_preco",
            )
            nova_qtd = st.number_input(
                "Quantidade inicial",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key="nova_qtd",
            )
            if st.button("Adicionar preço", type="primary", key="btn_novo_preco"):
                if novo_preco <= 0:
                    st.error("Informe um preço maior que zero.")
                elif nova_qtd < 0:
                    st.error("Quantidade não pode ser negativa.")
                else:
                    existente = (
                        db.query(AccessoryStock)
                        .filter(AccessoryStock.preco == novo_preco)
                        .first()
                    )
                    if existente:
                        existente.quantidade += nova_qtd
                        if nova_qtd > 0:
                            ent = AccessoryStockEntry(
                                data_entrada=date.today(),
                                preco=novo_preco,
                                quantidade=nova_qtd,
                            )
                            db.add(ent)
                        db.commit()
                        st.success(f"Quantidade somada ao preço existente. Total: {existente.quantidade:.0f} peças.")
                    else:
                        novo = AccessoryStock(preco=novo_preco, quantidade=nova_qtd)
                        db.add(novo)
                        if nova_qtd > 0:
                            ent = AccessoryStockEntry(
                                data_entrada=date.today(),
                                preco=novo_preco,
                                quantidade=nova_qtd,
                            )
                            db.add(ent)
                        db.commit()
                        st.success(f"Novo preço cadastrado: {nova_qtd:.0f} peças a {format_currency(novo_preco)}.")
                    st.rerun()

        st.markdown("---")
        st.subheader("Entradas no período")
        st.caption("Consulte as entradas de estoque (inclusões) por período.")

        periodo_ent = st.selectbox(
            "Período",
            options=["Hoje", "Últimos 7 dias", "Últimos 15 dias", "Últimos 30 dias", "Este mês", "Personalizado"],
            index=1,
            key="periodo_entradas",
        )
        if periodo_ent == "Hoje":
            data_inicio_ent = hoje
            data_fim_ent = hoje
        elif periodo_ent == "Últimos 7 dias":
            data_inicio_ent = hoje - timedelta(days=6)
            data_fim_ent = hoje
        elif periodo_ent == "Últimos 15 dias":
            data_inicio_ent = hoje - timedelta(days=14)
            data_fim_ent = hoje
        elif periodo_ent == "Últimos 30 dias":
            data_inicio_ent = hoje - timedelta(days=29)
            data_fim_ent = hoje
        elif periodo_ent == "Este mês":
            data_inicio_ent = hoje.replace(day=1)
            data_fim_ent = hoje
        else:
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                data_inicio_ent = st.date_input("Data inicial", value=hoje - timedelta(days=29), key="di_ent")
            with col_e2:
                data_fim_ent = st.date_input("Data final", value=hoje, key="df_ent")
            if data_inicio_ent > data_fim_ent:
                data_inicio_ent, data_fim_ent = data_fim_ent, data_inicio_ent

        entradas_ac = (
            db.execute(
                select(AccessoryStockEntry)
                .where(AccessoryStockEntry.data_entrada >= data_inicio_ent)
                .where(AccessoryStockEntry.data_entrada <= data_fim_ent)
                .order_by(AccessoryStockEntry.data_entrada.desc(), AccessoryStockEntry.id.desc())
            )
            .scalars().all()
        )
        if not entradas_ac:
            st.info("Nenhuma entrada no período selecionado.")
        else:
            total_pecas_ent = sum(e.quantidade for e in entradas_ac)
            total_valor_ent = sum(e.preco * e.quantidade for e in entradas_ac)
            col_ent1, col_ent2 = st.columns(2)
            with col_ent1:
                st.metric("Peças (entradas no período)", f"{total_pecas_ent:.0f}")
            with col_ent2:
                st.metric("Valor total (entradas)", format_currency(total_valor_ent))
            linhas_ent = []
            for e in entradas_ac:
                valor_linha = e.preco * e.quantidade
                linhas_ent.append({
                    "Data": e.data_entrada.strftime("%d/%m/%Y"),
                    "Preço": format_currency(e.preco),
                    "Quantidade": e.quantidade,
                    "Valor": format_currency(valor_linha),
                })
            st.dataframe(linhas_ent, use_container_width=True, hide_index=True)
            total_ent_txt = (
                f"Quantidade total: {total_pecas_ent:.0f} peças — "
                f"Valor total: {format_currency(total_valor_ent)}"
            )
            st.text(total_ent_txt)

finally:
    db.close()
