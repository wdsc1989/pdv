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

            st.markdown("**Editar ou excluir venda**")
            st.caption("Selecione uma venda para alterar dados ou excluir do histórico.")
            escolha_edit_v = st.selectbox(
                "Venda a editar ou excluir",
                options=opcoes_repasse,
                index=0,
                key="select_edit_venda",
            )
            idx_edit_v = opcoes_repasse.index(escolha_edit_v)
            venda_edit_id = ids_vendas_ac[idx_edit_v]
            venda_edit_obj = db.get(AccessorySale, venda_edit_id)
            col_ed_v, col_ex_v = st.columns(2)
            with col_ed_v:
                if st.button("Editar esta venda", key="btn_editar_venda"):
                    st.session_state["acess_editar_venda_id"] = venda_edit_id
                    st.rerun()
            with col_ex_v:
                if st.button("Excluir esta venda", type="secondary", key="btn_excluir_venda"):
                    st.session_state["acess_confirmar_excluir_venda_id"] = venda_edit_id
                    st.rerun()

        # Formulário de edição de venda (fora do else para não depender de vendas_ac no rerun)
        if st.session_state.get("acess_editar_venda_id"):
            st.markdown("---")
            vid = st.session_state["acess_editar_venda_id"]
            v_edit = db.get(AccessorySale, vid)
            if v_edit:
                st.markdown("**Editar venda**")
                with st.form("form_editar_venda_acess"):
                    data_edit = st.date_input("Data da venda", value=v_edit.data_venda, key="edit_v_data")
                    preco_edit = st.number_input("Preço (R$)", min_value=0.01, value=float(v_edit.preco), step=0.5, format="%.2f", key="edit_v_preco")
                    qtd_edit = st.number_input("Quantidade", min_value=0.0, value=float(v_edit.quantidade), step=1.0, key="edit_v_qtd")
                    repasse_edit = st.checkbox("Repasse ao fornecedor feito", value=bool(getattr(v_edit, "repasse_feito", False)), key="edit_v_repasse")
                    col_sv, col_cv = st.columns(2)
                    with col_sv:
                        subm = st.form_submit_button("Salvar")
                    with col_cv:
                        canc = st.form_submit_button("Cancelar")
                    if subm:
                        v_edit.data_venda = data_edit
                        v_edit.preco = preco_edit
                        v_edit.quantidade = qtd_edit
                        v_edit.repasse_feito = repasse_edit
                        db.commit()
                        st.session_state.pop("acess_editar_venda_id", None)
                        st.success("Venda atualizada.")
                        st.rerun()
                    if canc:
                        st.session_state.pop("acess_editar_venda_id", None)
                        st.rerun()

        # Confirmação de exclusão de venda
        if st.session_state.get("acess_confirmar_excluir_venda_id"):
            st.markdown("---")
            eid = st.session_state["acess_confirmar_excluir_venda_id"]
            v_del = db.get(AccessorySale, eid)
            if v_del:
                st.warning(f"Excluir venda de {v_del.data_venda.strftime('%d/%m/%Y')} — {format_currency(v_del.preco)} — {v_del.quantidade:.0f} un? Esta ação não pode ser desfeita.")
                col_ok, col_can = st.columns(2)
                with col_ok:
                    if st.button("Sim, excluir venda", type="primary", key="confirm_excluir_venda"):
                        db.delete(v_del)
                        db.commit()
                        st.session_state.pop("acess_confirmar_excluir_venda_id", None)
                        st.success("Venda excluída.")
                        st.rerun()
                with col_can:
                    if st.button("Cancelar", key="cancel_excluir_venda"):
                        st.session_state.pop("acess_confirmar_excluir_venda_id", None)
                        st.rerun()
            else:
                st.session_state.pop("acess_confirmar_excluir_venda_id", None)
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

            st.markdown("**Editar ou excluir linha de estoque**")
            st.caption("Altere preço/quantidade ou remova um preço do estoque.")
            opcoes_edit_est = [f"{format_currency(r.preco)} — {r.quantidade:.0f} peças" for r in estoque_ajuste]
            escolha_edit_est = st.selectbox("Linha a editar ou excluir", options=opcoes_edit_est, key="select_edit_estoque")
            idx_edit_est = opcoes_edit_est.index(escolha_edit_est)
            row_edit_est = estoque_ajuste[idx_edit_est]
            col_ed_est, col_ex_est = st.columns(2)
            with col_ed_est:
                if st.button("Editar esta linha", key="btn_editar_estoque"):
                    st.session_state["acess_editar_estoque_id"] = row_edit_est.id
                    st.rerun()
            with col_ex_est:
                if st.button("Excluir esta linha", type="secondary", key="btn_excluir_estoque"):
                    st.session_state["acess_confirmar_excluir_estoque_id"] = row_edit_est.id
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

        # Formulário de edição de linha de estoque (tab Ajuste)
        if st.session_state.get("acess_editar_estoque_id"):
            st.markdown("---")
            eid = st.session_state["acess_editar_estoque_id"]
            row_est = db.get(AccessoryStock, eid)
            if row_est:
                st.markdown("**Editar linha de estoque**")
                with st.form("form_editar_estoque_acess"):
                    preco_est = st.number_input("Preço (R$)", min_value=0.01, value=float(row_est.preco), step=0.5, format="%.2f", key="edit_est_preco")
                    qtd_est = st.number_input("Quantidade", min_value=0.0, value=float(row_est.quantidade), step=1.0, key="edit_est_qtd")
                    col_sv2, col_cv2 = st.columns(2)
                    with col_sv2:
                        subm2 = st.form_submit_button("Salvar")
                    with col_cv2:
                        canc2 = st.form_submit_button("Cancelar")
                    if subm2:
                        outro = db.query(AccessoryStock).filter(AccessoryStock.preco == preco_est, AccessoryStock.id != row_est.id).first()
                        if outro:
                            outro.quantidade += qtd_est
                            db.delete(row_est)
                            db.commit()
                            st.session_state.pop("acess_editar_estoque_id", None)
                            st.success(f"Preço unificado com linha existente. Total: {outro.quantidade:.0f} peças.")
                        else:
                            row_est.preco = preco_est
                            row_est.quantidade = qtd_est
                            db.commit()
                            st.session_state.pop("acess_editar_estoque_id", None)
                            st.success("Linha de estoque atualizada.")
                        st.rerun()
                    if canc2:
                        st.session_state.pop("acess_editar_estoque_id", None)
                        st.rerun()

        # Confirmação de exclusão de linha de estoque
        if st.session_state.get("acess_confirmar_excluir_estoque_id"):
            st.markdown("---")
            eid = st.session_state["acess_confirmar_excluir_estoque_id"]
            row_del = db.get(AccessoryStock, eid)
            if row_del:
                st.warning(f"Excluir estoque de {format_currency(row_del.preco)} — {row_del.quantidade:.0f} peças? O registro será removido.")
                col_ok2, col_can2 = st.columns(2)
                with col_ok2:
                    if st.button("Sim, excluir linha", type="primary", key="confirm_excluir_estoque"):
                        db.delete(row_del)
                        db.commit()
                        st.session_state.pop("acess_confirmar_excluir_estoque_id", None)
                        st.success("Linha de estoque excluída.")
                        st.rerun()
                with col_can2:
                    if st.button("Cancelar", key="cancel_excluir_estoque"):
                        st.session_state.pop("acess_confirmar_excluir_estoque_id", None)
                        st.rerun()
            else:
                st.session_state.pop("acess_confirmar_excluir_estoque_id", None)
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

            st.markdown("**Editar ou excluir entrada**")
            st.caption("Selecione uma entrada do período para alterar ou excluir.")
            opcoes_ent = [
                f"{e.data_entrada.strftime('%d/%m/%Y')} — {format_currency(e.preco)} — {e.quantidade:.0f} peças"
                for e in entradas_ac
            ]
            escolha_ent = st.selectbox("Entrada a editar ou excluir", options=opcoes_ent, key="select_edit_entrada")
            idx_ent = opcoes_ent.index(escolha_ent)
            entrada_sel = entradas_ac[idx_ent]
            col_ed_ent, col_ex_ent = st.columns(2)
            with col_ed_ent:
                if st.button("Editar esta entrada", key="btn_editar_entrada"):
                    st.session_state["acess_editar_entrada_id"] = entrada_sel.id
                    st.rerun()
            with col_ex_ent:
                if st.button("Excluir esta entrada", type="secondary", key="btn_excluir_entrada"):
                    st.session_state["acess_confirmar_excluir_entrada_id"] = entrada_sel.id
                    st.rerun()

        # Formulário de edição de entrada (tab Ajuste)
        if st.session_state.get("acess_editar_entrada_id"):
            st.markdown("---")
            ent_id = st.session_state["acess_editar_entrada_id"]
            ent_edit = db.get(AccessoryStockEntry, ent_id)
            if ent_edit:
                st.markdown("**Editar entrada**")
                with st.form("form_editar_entrada_acess"):
                    data_ent = st.date_input("Data da entrada", value=ent_edit.data_entrada, key="edit_ent_data")
                    preco_ent = st.number_input("Preço (R$)", min_value=0.01, value=float(ent_edit.preco), step=0.5, format="%.2f", key="edit_ent_preco")
                    qtd_ent = st.number_input("Quantidade", min_value=0.0, value=float(ent_edit.quantidade), step=1.0, key="edit_ent_qtd")
                    col_sv3, col_cv3 = st.columns(2)
                    with col_sv3:
                        subm3 = st.form_submit_button("Salvar")
                    with col_cv3:
                        canc3 = st.form_submit_button("Cancelar")
                    if subm3:
                        ent_edit.data_entrada = data_ent
                        ent_edit.preco = preco_ent
                        ent_edit.quantidade = qtd_ent
                        db.commit()
                        st.session_state.pop("acess_editar_entrada_id", None)
                        st.success("Entrada atualizada.")
                        st.rerun()
                    if canc3:
                        st.session_state.pop("acess_editar_entrada_id", None)
                        st.rerun()

        # Confirmação de exclusão de entrada
        if st.session_state.get("acess_confirmar_excluir_entrada_id"):
            st.markdown("---")
            ent_id = st.session_state["acess_confirmar_excluir_entrada_id"]
            ent_del = db.get(AccessoryStockEntry, ent_id)
            if ent_del:
                st.warning(
                    f"Excluir entrada de {ent_del.data_entrada.strftime('%d/%m/%Y')} — "
                    f"{format_currency(ent_del.preco)} — {ent_del.quantidade:.0f} peças? O registro será removido (o estoque atual não é alterado)."
                )
                col_ok3, col_can3 = st.columns(2)
                with col_ok3:
                    if st.button("Sim, excluir entrada", type="primary", key="confirm_excluir_entrada"):
                        db.delete(ent_del)
                        db.commit()
                        st.session_state.pop("acess_confirmar_excluir_entrada_id", None)
                        st.success("Entrada excluída.")
                        st.rerun()
                with col_can3:
                    if st.button("Cancelar", key="cancel_excluir_entrada"):
                        st.session_state.pop("acess_confirmar_excluir_entrada_id", None)
                        st.rerun()
            else:
                st.session_state.pop("acess_confirmar_excluir_entrada_id", None)
                st.rerun()

finally:
    db.close()
