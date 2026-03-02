import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.account_payable import AccountPayable
from models.account_receivable import AccountReceivable
from services.accounts_agent_service import AccountsAgentService
from services.auth_service import AuthService
from services.speech_to_text_service import transcribe_audio
from utils.formatters import format_currency, format_date
from utils.navigation import show_sidebar


def _format_venc(iso: str) -> str:
    if not iso:
        return iso
    try:
        return format_date(date.fromisoformat(iso))
    except Exception:
        return iso


st.set_page_config(
    page_title="Contas a Pagar e a Receber",
    page_icon="📄",
    layout="wide",
)

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📄 Contas a Pagar e Contas a Receber</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>"
    "Cadastre contas a pagar (fornecedores) e contas a receber (vendas fiado). "
    "Ambos são alertados no resumo diário do Agente de Relatórios.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    tab_pagar, tab_receber, tab_agente = st.tabs(["Contas a Pagar", "Contas a Receber", "📋 Agente"])

    with tab_pagar:
        contas = db.execute(
            select(AccountPayable).order_by(AccountPayable.data_vencimento)
        ).scalars().all()
        col_form, col_list = st.columns([1, 2])
        with col_form:
            edit_id_ap = st.session_state.get("edit_id_ap")
            opcoes_ap = [0] + [c.id for c in contas]
            sel_edit_ap = st.selectbox(
                "Editar conta ou nova",
                options=opcoes_ap,
                format_func=lambda x: "— Nova conta —" if x == 0 else next((f"{c.fornecedor} - {format_currency(c.valor)} (venc. {format_date(c.data_vencimento)})" for c in contas if c.id == x), f"ID {x}"),
                key="sel_edit_ap",
            )
            if sel_edit_ap != 0:
                st.session_state["edit_id_ap"] = sel_edit_ap
            else:
                st.session_state.pop("edit_id_ap", None)

            conta_edit_ap = None
            if st.session_state.get("edit_id_ap"):
                conta_edit_ap = next((c for c in contas if c.id == st.session_state["edit_id_ap"]), None)

            st.subheader("Editar conta a pagar" if conta_edit_ap else "Nova conta a pagar")
            st.caption("Fornecedor e valor > 0 obrigatórios.")
            default_fornecedor = conta_edit_ap.fornecedor if conta_edit_ap else ""
            default_desc = (conta_edit_ap.descricao or "") if conta_edit_ap else ""
            default_venc = conta_edit_ap.data_vencimento if conta_edit_ap else date.today()
            default_valor = float(conta_edit_ap.valor) if conta_edit_ap else 0.0
            default_obs = (conta_edit_ap.observacao or "") if conta_edit_ap else ""
            k = st.session_state.get("edit_id_ap") or 0
            fornecedor = st.text_input("Fornecedor", value=default_fornecedor, key=f"ap_fornecedor_{k}", placeholder="Nome do fornecedor")
            descricao = st.text_input("Descrição (opcional)", value=default_desc, key=f"ap_descricao_{k}")
            data_vencimento = st.date_input("Data de vencimento", value=default_venc, key=f"ap_venc_{k}")
            valor = st.number_input("Valor", min_value=0.0, value=default_valor, step=1.0, key=f"ap_valor_{k}")
            observacao = st.text_input("Observação (opcional)", value=default_obs, key=f"ap_obs_{k}")
            if conta_edit_ap:
                if st.button("Atualizar conta a pagar", type="primary", use_container_width=True, key="btn_update_ap"):
                    if not fornecedor or valor <= 0:
                        st.error("Fornecedor e valor > 0 são obrigatórios.")
                    else:
                        conta_edit_ap.fornecedor = fornecedor
                        conta_edit_ap.descricao = descricao or None
                        conta_edit_ap.data_vencimento = data_vencimento
                        conta_edit_ap.valor = valor
                        conta_edit_ap.observacao = observacao or None
                        conta_edit_ap.update_status()
                        db.commit()
                        st.session_state.pop("edit_id_ap", None)
                        st.success("Conta a pagar atualizada.")
                        st.rerun()
                if st.button("Cancelar edição", use_container_width=True, key="btn_cancel_edit_ap"):
                    st.session_state.pop("edit_id_ap", None)
                    st.rerun()
            else:
                if st.button("Salvar conta a pagar", type="primary", use_container_width=True, key="btn_ap"):
                    if not fornecedor or valor <= 0:
                        st.error("Fornecedor e valor > 0 são obrigatórios.")
                    else:
                        conta = AccountPayable(
                            fornecedor=fornecedor,
                            descricao=descricao or None,
                            data_vencimento=data_vencimento,
                            valor=valor,
                            observacao=observacao or None,
                        )
                        conta.update_status()
                        db.add(conta)
                        db.commit()
                        st.success("Conta a pagar cadastrada.")
                        st.rerun()
        with col_list:
            st.subheader("Contas a pagar")
            if not contas:
                st.info("Nenhuma conta a pagar cadastrada.")
            else:
                linhas = []
                ids = []
                for c in contas:
                    c.update_status()
                    ids.append(c.id)
                    linhas.append({
                        "Fornecedor": c.fornecedor,
                        "Descrição": c.descricao or "",
                        "Vencimento": format_date(c.data_vencimento),
                        "Pagamento": format_date(c.data_pagamento) if c.data_pagamento else "-",
                        "Valor": format_currency(c.valor),
                        "Status": c.status,
                    })
                st.dataframe(linhas, use_container_width=True, hide_index=True)
                st.markdown("---")
                st.markdown("**Marcar como paga**")
                idx = st.selectbox(
                    "Selecione a conta",
                    options=list(range(len(ids))),
                    format_func=lambda i: f"{contas[i].fornecedor} - {format_currency(contas[i].valor)} (venc. {format_date(contas[i].data_vencimento)})",
                    key="sel_ap",
                )
                if st.button("Marcar selecionada como paga", use_container_width=True, key="btn_marcar_ap"):
                    conta = contas[idx]
                    conta.data_pagamento = date.today()
                    conta.update_status()
                    db.commit()
                    st.success("Conta marcada como paga.")
                    st.rerun()

    with tab_receber:
        contas_r = db.execute(
            select(AccountReceivable).order_by(AccountReceivable.data_vencimento)
        ).scalars().all()
        col_form2, col_list2 = st.columns([1, 2])
        with col_form2:
            edit_id_ar = st.session_state.get("edit_id_ar")
            opcoes_ar = [0] + [c.id for c in contas_r]
            sel_edit_ar = st.selectbox(
                "Editar conta ou nova",
                options=opcoes_ar,
                format_func=lambda x: "— Nova conta —" if x == 0 else next((f"{c.cliente} - {format_currency(c.valor)} (venc. {format_date(c.data_vencimento)})" for c in contas_r if c.id == x), f"ID {x}"),
                key="sel_edit_ar",
            )
            if sel_edit_ar != 0:
                st.session_state["edit_id_ar"] = sel_edit_ar
            else:
                st.session_state.pop("edit_id_ar", None)

            conta_edit_ar = None
            if st.session_state.get("edit_id_ar"):
                conta_edit_ar = next((c for c in contas_r if c.id == st.session_state["edit_id_ar"]), None)

            st.subheader("Editar conta a receber" if conta_edit_ar else "Nova conta a receber")
            st.caption("Cliente (fiado) e valor > 0 obrigatórios.")
            default_cliente = conta_edit_ar.cliente if conta_edit_ar else ""
            default_desc_r = (conta_edit_ar.descricao or "") if conta_edit_ar else ""
            default_venc_r = conta_edit_ar.data_vencimento if conta_edit_ar else date.today()
            default_valor_r = float(conta_edit_ar.valor) if conta_edit_ar else 0.0
            default_obs_r = (conta_edit_ar.observacao or "") if conta_edit_ar else ""
            kr = st.session_state.get("edit_id_ar") or 0
            cliente = st.text_input("Cliente", value=default_cliente, key=f"ar_cliente_{kr}", placeholder="Nome do cliente")
            descricao_r = st.text_input("Descrição (opcional)", value=default_desc_r, key=f"ar_descricao_{kr}")
            data_venc_r = st.date_input("Data de vencimento", value=default_venc_r, key=f"ar_venc_{kr}")
            valor_r = st.number_input("Valor", min_value=0.0, value=default_valor_r, step=1.0, key=f"ar_valor_{kr}")
            observacao_r = st.text_input("Observação (opcional)", value=default_obs_r, key=f"ar_obs_{kr}")
            if conta_edit_ar:
                if st.button("Atualizar conta a receber", type="primary", use_container_width=True, key="btn_update_ar"):
                    if not cliente or valor_r <= 0:
                        st.error("Cliente e valor > 0 são obrigatórios.")
                    else:
                        conta_edit_ar.cliente = cliente
                        conta_edit_ar.descricao = descricao_r or None
                        conta_edit_ar.data_vencimento = data_venc_r
                        conta_edit_ar.valor = valor_r
                        conta_edit_ar.observacao = observacao_r or None
                        conta_edit_ar.update_status()
                        db.commit()
                        st.session_state.pop("edit_id_ar", None)
                        st.success("Conta a receber atualizada.")
                        st.rerun()
                if st.button("Cancelar edição", use_container_width=True, key="btn_cancel_edit_ar"):
                    st.session_state.pop("edit_id_ar", None)
                    st.rerun()
            else:
                if st.button("Salvar conta a receber", type="primary", use_container_width=True, key="btn_ar"):
                    if not cliente or valor_r <= 0:
                        st.error("Cliente e valor > 0 são obrigatórios.")
                    else:
                        conta = AccountReceivable(
                            cliente=cliente,
                            descricao=descricao_r or None,
                            data_vencimento=data_venc_r,
                            valor=valor_r,
                            observacao=observacao_r or None,
                        )
                        conta.update_status()
                        db.add(conta)
                        db.commit()
                        st.success("Conta a receber cadastrada.")
                        st.rerun()
        with col_list2:
            st.subheader("Contas a receber")
            if not contas_r:
                st.info("Nenhuma conta a receber cadastrada.")
            else:
                linhas_r = []
                ids_r = []
                for c in contas_r:
                    c.update_status()
                    ids_r.append(c.id)
                    linhas_r.append({
                        "Cliente": c.cliente,
                        "Descrição": c.descricao or "",
                        "Vencimento": format_date(c.data_vencimento),
                        "Recebimento": format_date(c.data_recebimento) if c.data_recebimento else "-",
                        "Valor": format_currency(c.valor),
                        "Status": c.status,
                    })
                st.dataframe(linhas_r, use_container_width=True, hide_index=True)
                st.markdown("---")
                st.markdown("**Marcar como recebida**")
                idx_r = st.selectbox(
                    "Selecione a conta",
                    options=list(range(len(ids_r))),
                    format_func=lambda i: f"{contas_r[i].cliente} - {format_currency(contas_r[i].valor)} (venc. {format_date(contas_r[i].data_vencimento)})",
                    key="sel_ar",
                )
                if st.button("Marcar selecionada como recebida", use_container_width=True, key="btn_marcar_ar"):
                    conta = contas_r[idx_r]
                    conta.data_recebimento = date.today()
                    conta.update_status()
                    db.commit()
                    st.success("Conta marcada como recebida.")
                    st.rerun()

    with tab_agente:
        st.caption("Cadastre ou dê baixa em linguagem natural. O agente pergunta o que faltar e confirma antes de executar.")
        st.markdown(
            "**Cadastrar:** \"Conta de energia 120 reais para 10/02/2026\", \"Cliente Maria, 50 reais a receber em 05/02/2026\". "
            "**Dar baixa:** \"Marcar como paga a conta de energia\", \"Recebi do João\", \"Dar baixa na conta da Maria\"."
        )
        st.markdown("---")
        if "accounts_chat_history" not in st.session_state:
            st.session_state.accounts_chat_history = []
        if "accounts_pending_records" not in st.session_state:
            st.session_state.accounts_pending_records = []
        if "accounts_pending_baixa" not in st.session_state:
            st.session_state.accounts_pending_baixa = None

        for msg in st.session_state.accounts_chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            with st.chat_message(role):
                st.markdown(content)
                if role == "assistant" and msg.get("records"):
                    recs = msg["records"]
                    if len(recs) <= 10:
                        for i, r in enumerate(recs, 1):
                            v = r.get("valor", 0)
                            d = r.get("data_vencimento", "")
                            if r.get("tipo") == "pagar":
                                st.caption(f"{i}. {r.get('fornecedor', '')} — {format_currency(v)} — venc. {_format_venc(d)}")
                            else:
                                st.caption(f"{i}. {r.get('cliente', '')} — {format_currency(v)} — venc. {_format_venc(d)}")
                    else:
                        st.caption(f"*{len(recs)} registros: de {_format_venc(recs[0].get('data_vencimento'))} a {_format_venc(recs[-1].get('data_vencimento'))}*")

        pending_ag = st.session_state.accounts_pending_records
        pending_baixa = st.session_state.accounts_pending_baixa

        if pending_baixa:
            st.markdown("---")
            st.markdown("**Confirmar baixa?**")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Sim, dar baixa", type="primary", key="btn_confirm_baixa"):
                    db_ag = SessionLocal()
                    try:
                        agent = AccountsAgentService(db_ag)
                        result = agent.execute_baixa(db_ag, pending_baixa)
                        if result.get("success"):
                            st.session_state.accounts_chat_history.append({
                                "role": "assistant",
                                "content": f"✅ {result.get('message', 'Baixa realizada.')}",
                                "records": None,
                            })
                        else:
                            st.session_state.accounts_chat_history.append({
                                "role": "assistant",
                                "content": f"❌ {result.get('message', 'Erro ao dar baixa.')}",
                                "records": None,
                            })
                        st.session_state.accounts_pending_baixa = None
                    finally:
                        db_ag.close()
                    st.rerun()
            with col_no:
                if st.button("Não, cancelar", key="btn_cancel_baixa"):
                    st.session_state.accounts_pending_baixa = None
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": "Baixa cancelada. Pode enviar um novo pedido.",
                        "records": None,
                    })
                    st.rerun()
            st.markdown("---")

        if pending_ag:
            st.markdown("---")
            st.markdown("**Confirmar cadastro?**")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Sim, cadastrar", type="primary", key="btn_confirm_contas"):
                    db_ag = SessionLocal()
                    try:
                        agent = AccountsAgentService(db_ag)
                        result = agent.execute_insert(db_ag, pending_ag)
                        if result.get("success"):
                            st.session_state.accounts_chat_history.append({
                                "role": "assistant",
                                "content": f"✅ {result.get('message', 'Cadastro realizado.')}",
                                "records": None,
                            })
                        else:
                            st.session_state.accounts_chat_history.append({
                                "role": "assistant",
                                "content": f"❌ {result.get('message', 'Erro ao cadastrar.')}",
                                "records": None,
                            })
                        st.session_state.accounts_pending_records = []
                    finally:
                        db_ag.close()
                    st.rerun()
            with col_no:
                if st.button("Não, cancelar", key="btn_cancel_contas"):
                    st.session_state.accounts_pending_records = []
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": "Cadastro cancelado. Pode enviar um novo pedido.",
                        "records": None,
                    })
                    st.rerun()
            st.markdown("---")

        query_ag = st.chat_input("Cadastrar conta ou dar baixa (ex.: \"marcar como paga a energia\", \"recebi do João\")...", key="chat_agente")
        query_ag = query_ag or st.session_state.pop("pending_audio_query_contas", None)

        with st.expander("🎤 Gravar pelo microfone"):
            st.caption("Use o microfone do dispositivo. O áudio é transcrito e enviado como pedido (não é guardado no servidor).")
            audio_key_ag = f"audio_contas_{st.session_state.get('audio_contas_counter', 0)}"
            audio_data_ag = st.audio_input("Gravar áudio", key=audio_key_ag, sample_rate=16000)
            if audio_data_ag:
                db_audio_ag = SessionLocal()
                try:
                    with st.spinner("Transcrevendo áudio..."):
                        audio_bytes_ag = audio_data_ag.read()
                        text_ag, err_ag = transcribe_audio(db_audio_ag, audio_bytes_ag, "audio.wav")
                    del audio_bytes_ag
                    if err_ag:
                        st.error(err_ag)
                    elif text_ag:
                        st.session_state["pending_audio_query_contas"] = text_ag
                        st.session_state["audio_contas_counter"] = st.session_state.get("audio_contas_counter", 0) + 1
                        st.success(f"Transcrito: \"{text_ag[:80]}{'...' if len(text_ag) > 80 else ''}\"")
                        st.rerun()
                finally:
                    db_audio_ag.close()

        if query_ag:
            st.session_state.accounts_chat_history.append({"role": "user", "content": query_ag})
            db_ag = SessionLocal()
            try:
                agent = AccountsAgentService(db_ag)
                with st.spinner("Interpretando pedido..."):
                    history_ag = st.session_state.accounts_chat_history[:-1]
                    out = agent.parse_request(query_ag, conversation_history=history_ag)
                status = out.get("status", "error")
                message = out.get("message", "")
                records = out.get("records", [])

                if status == "need_info":
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": None,
                    })
                    st.session_state.accounts_pending_records = []
                elif status == "confirm" and records:
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": records,
                    })
                    st.session_state.accounts_pending_records = records
                else:
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": message or "Não foi possível interpretar o pedido. Tente ser mais específico (quem, valor, data).",
                        "records": None,
                    })
                    st.session_state.accounts_pending_records = []
            finally:
                db_ag.close()
            st.rerun()

        st.markdown("---")
        if st.button("Limpar histórico", use_container_width=True, key="btn_clear_accounts"):
            st.session_state.accounts_chat_history = []
            st.session_state.accounts_pending_records = []
            st.session_state.accounts_pending_baixa = None
            st.rerun()

finally:
    db.close()
