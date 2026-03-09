"""
Agente de cadastro de contas a pagar e a receber em linguagem natural.
Interpreta pedidos, faz perguntas quando falta informação e confirma antes de inserir.
Suporta cadastro em massa (ex.: todo dia 8 de cada mês de 2026).
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import date as date_type

import streamlit as st

from config.database import SessionLocal
from services.accounts_agent_service import AccountsAgentService
from services.auth_service import AuthService
from services.chat_memory import SCOPE_ACCOUNTS_AGENT, add_message, clear, get_messages
from services.speech_to_text_service import transcribe_audio
from utils.formatters import format_currency, format_date
from utils.navigation import show_sidebar


def _format_venc(iso: str) -> str:
    if not iso:
        return iso
    try:
        return format_date(date_type.fromisoformat(iso))
    except Exception:
        return iso

st.set_page_config(
    page_title="Agente de Contas",
    page_icon="📋",
    layout="wide",
)

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📋 Agente de Cadastro de Contas</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>"
    "Cadastre contas a pagar e a receber em linguagem natural. O agente pergunta o que faltar e confirma antes de inserir."
    "</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "**Exemplos:** "
    "\"Cadastre conta de energia no valor de 120 para o dia 10/02/2026\", "
    "\"Para o cliente Maria, 50 reais a receber em 05/02/2026\", "
    "\"Cadastre a conta a pagar aluguel no valor de 800 para todo dia 8 dos meses do ano de 2026\"."
)
st.markdown("---")

if "accounts_chat_history" not in st.session_state:
    st.session_state.accounts_chat_history = []
if "accounts_pending_records" not in st.session_state:
    st.session_state.accounts_pending_records = []

user = AuthService.get_current_user()
current_user_id = user.get("id") if user else None

# Carregar histórico do banco quando está vazio (ex.: após refresh)
if current_user_id is not None and len(st.session_state.accounts_chat_history) == 0:
    db_load = SessionLocal()
    try:
        loaded = get_messages(db_load, current_user_id, SCOPE_ACCOUNTS_AGENT)
        if loaded:
            st.session_state.accounts_chat_history = loaded
            st.rerun()
    finally:
        db_load.close()

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

pending = st.session_state.accounts_pending_records

if pending:
    st.markdown("---")
    st.markdown("**Confirmar cadastro?**")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Sim, cadastrar", type="primary", key="btn_confirm_contas"):
            db = SessionLocal()
            try:
                agent = AccountsAgentService(db)
                result = agent.execute_insert(db, pending)
                if result.get("success"):
                    content = f"✅ {result.get('message', 'Cadastro realizado.')}"
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": content,
                        "records": None,
                    })
                    if current_user_id is not None:
                        add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", content, None)
                else:
                    content = f"❌ {result.get('message', 'Erro ao cadastrar.')}"
                    st.session_state.accounts_chat_history.append({
                        "role": "assistant",
                        "content": content,
                        "records": None,
                    })
                    if current_user_id is not None:
                        add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", content, None)
                st.session_state.accounts_pending_records = []
            finally:
                db.close()
            st.rerun()
    with col_no:
        if st.button("Não, cancelar", key="btn_cancel_contas"):
            st.session_state.accounts_pending_records = []
            content = "Cadastro cancelado. Pode enviar um novo pedido."
            st.session_state.accounts_chat_history.append({
                "role": "assistant",
                "content": content,
                "records": None,
            })
            if current_user_id is not None:
                db_cancel = SessionLocal()
                try:
                    add_message(db_cancel, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", content, None)
                finally:
                    db_cancel.close()
            st.rerun()
    st.markdown("---")

query = st.chat_input("Descreva a conta a cadastrar (a pagar ou a receber)...")
query = query or st.session_state.pop("pending_audio_query_contas", None)

with st.expander("🎤 Gravar pelo microfone"):
    st.caption("Grave um áudio e envie; será transcrito e enviado como pedido (não é guardado no servidor).")
    audio_key = f"audio_contas_standalone_{st.session_state.get('audio_contas_standalone_counter', 0)}"
    audio_value = st.audio_input("Microfone", key=audio_key, label_visibility="collapsed")
    if audio_value is not None and hasattr(audio_value, "read"):
        try:
            audio_bytes = audio_value.read()
        except Exception:
            st.error("Erro ao ler o áudio.")
        else:
            if audio_bytes:
                db_audio = SessionLocal()
                try:
                    with st.spinner("Transcrevendo áudio..."):
                        text, err = transcribe_audio(db_audio, audio_bytes, "audio.wav")
                    if err:
                        st.error(err)
                    elif text:
                        st.session_state["pending_audio_query_contas"] = text
                        st.session_state["audio_contas_standalone_counter"] = st.session_state.get("audio_contas_standalone_counter", 0) + 1
                        st.success(f"Transcrito: \"{text[:80]}{'...' if len(text) > 80 else ''}\"")
                        st.rerun()
                finally:
                    db_audio.close()

if query:
    st.session_state.accounts_chat_history.append({"role": "user", "content": query})
    db = SessionLocal()
    try:
        if current_user_id is not None:
            add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "user", query, None)
        agent = AccountsAgentService(db)
        with st.spinner("Interpretando pedido..."):
            # Histórico para contexto: mensagens anteriores (role + content)
            history = [
                {"role": (m.get("role") or "user"), "content": (m.get("content") or "")}
                for m in st.session_state.accounts_chat_history[:-1]
            ]
            out = agent.parse_request(query, conversation_history=history)
        status = out.get("status", "error")
        message = out.get("message", "")
        records = out.get("records", [])

        if status == "need_info":
            st.session_state.accounts_chat_history.append({
                "role": "assistant",
                "content": message,
                "records": None,
            })
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", message, None)
            st.session_state.accounts_pending_records = []
        elif status == "confirm" and records:
            st.session_state.accounts_chat_history.append({
                "role": "assistant",
                "content": message,
                "records": records,
            })
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", message, records)
            st.session_state.accounts_pending_records = records
        else:
            fallback = message or "Não foi possível interpretar o pedido. Tente ser mais específico (quem, valor, data)."
            st.session_state.accounts_chat_history.append({
                "role": "assistant",
                "content": fallback,
                "records": None,
            })
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_ACCOUNTS_AGENT, "assistant", fallback, None)
            st.session_state.accounts_pending_records = []
    finally:
        db.close()
    st.rerun()

st.markdown("---")
if st.button("Limpar histórico", use_container_width=True, key="btn_clear_accounts"):
    if current_user_id is not None:
        db_clear = SessionLocal()
        try:
            clear(db_clear, current_user_id, SCOPE_ACCOUNTS_AGENT)
        finally:
            db_clear.close()
    st.session_state.accounts_chat_history = []
    st.session_state.accounts_pending_records = []
    st.rerun()
