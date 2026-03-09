import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import init_db, SessionLocal
from models.personal_agenda import PersonalAgenda
from services.agenda_agent_service import AgendaAgentService
from services.auth_service import AuthService
from services.chat_memory import SCOPE_AGENDA_AGENT, add_message, clear, get_messages
from services.speech_to_text_service import transcribe_audio
from utils.navigation import show_sidebar


st.set_page_config(page_title="Agenda Pessoal", page_icon="📅", layout="wide")

AuthService.require_roles(["admin"])
show_sidebar()

user = AuthService.get_current_user()
current_user_id = user.get("id") if user else None

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📅 Agenda Pessoal (Admin)</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>"
    "Cadastre compromissos pessoais (somente administradores). "
    "Os compromissos de hoje e dos próximos 7 dias aparecerão como alertas no resumo diário do Agente de Relatórios."
    "</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

init_db()
db = SessionLocal()

# Direcionamento a partir da Análise do dia (link com aba=compromissos ou botão)
qp = st.query_params
aba_compromissos_primeiro = (qp.get("aba") == "compromissos") or st.session_state.pop("agenda_aba_compromissos", False)
tabs_labels = ["Compromissos", "Agente"] if aba_compromissos_primeiro else ["Agente", "Compromissos"]
tab_handles = st.tabs(tabs_labels)
tab_agente = next((h for i, h in enumerate(tab_handles) if tabs_labels[i] == "Agente"), tab_handles[0])
tab_compromissos = next((h for i, h in enumerate(tab_handles) if tabs_labels[i] == "Compromissos"), tab_handles[1])

try:

    with tab_agente:
        st.caption(
            "Registre compromissos em linguagem natural. "
            "O agente pergunta o que faltar (título, data) e confirma antes de cadastrar."
        )
        st.markdown(
            "**Exemplos:** \"Reunião amanhã às 14h\", \"Dentista dia 15/03\", \"Agendar entrega para segunda\", \"Compromisso: consulta médica na quinta\"."
        )
        st.markdown("---")

        if "agenda_chat_history" not in st.session_state:
            st.session_state.agenda_chat_history = []
        if "agenda_pending_record" not in st.session_state:
            st.session_state.agenda_pending_record = None

        if current_user_id is not None and len(st.session_state.agenda_chat_history) == 0:
            db_load = SessionLocal()
            try:
                loaded = get_messages(db_load, current_user_id, SCOPE_AGENDA_AGENT)
                if loaded:
                    st.session_state.agenda_chat_history = loaded
                    st.rerun()
            finally:
                db_load.close()

        for msg in st.session_state.agenda_chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            with st.chat_message(role):
                st.markdown(content)
                if role == "assistant" and msg.get("records") and len(msg["records"]) == 1:
                    r = msg["records"][0]
                    st.caption(
                        f"*{r.get('titulo', '')} — {r.get('data', '')} {r.get('hora') or ''}*"
                    )

        pending_record = st.session_state.agenda_pending_record

        if pending_record:
            st.markdown("---")
            st.markdown("**Confirmar cadastro?**")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Sim, cadastrar", type="primary", key="btn_confirm_agenda"):
                    db_ag = SessionLocal()
                    try:
                        agent = AgendaAgentService(db_ag)
                        result = agent.execute_insert(db_ag, pending_record, current_user_id)
                        if result.get("success"):
                            content = f"✅ {result.get('message', 'Compromisso registrado.')}"
                            st.session_state.agenda_chat_history.append({
                                "role": "assistant",
                                "content": content,
                                "records": None,
                            })
                            if current_user_id is not None:
                                add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "assistant", content, None)
                        else:
                            content = f"❌ {result.get('message', 'Erro ao cadastrar.')}"
                            st.session_state.agenda_chat_history.append({
                                "role": "assistant",
                                "content": content,
                                "records": None,
                            })
                            if current_user_id is not None:
                                add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "assistant", content, None)
                        st.session_state.agenda_pending_record = None
                    finally:
                        db_ag.close()
                    st.rerun()
            with col_no:
                if st.button("Não, cancelar", key="btn_cancel_agenda"):
                    st.session_state.agenda_pending_record = None
                    content = "Cadastro cancelado. Pode enviar um novo pedido."
                    st.session_state.agenda_chat_history.append({
                        "role": "assistant",
                        "content": content,
                        "records": None,
                    })
                    if current_user_id is not None:
                        db_cancel = SessionLocal()
                        try:
                            add_message(db_cancel, current_user_id, SCOPE_AGENDA_AGENT, "assistant", content, None)
                        finally:
                            db_cancel.close()
                    st.rerun()
            st.markdown("---")

        query_ag = st.chat_input(
            "Descreva o compromisso (ex.: Reunião amanhã às 14h, Dentista dia 15/03)...",
            key="chat_agenda",
        )
        query_ag = query_ag or st.session_state.pop("pending_audio_query_agenda", None)

        with st.expander("🎤 Gravar pelo microfone"):
            st.caption("Grave um áudio e envie; será transcrito e enviado como pedido de compromisso (não é guardado no servidor).")
            audio_key_agenda = f"audio_agenda_{st.session_state.get('audio_agenda_counter', 0)}"
            audio_value_agenda = st.audio_input("Microfone", key=audio_key_agenda, label_visibility="collapsed")
            if audio_value_agenda is not None and hasattr(audio_value_agenda, "read"):
                try:
                    audio_bytes_agenda = audio_value_agenda.read()
                except Exception:
                    st.error("Erro ao ler o áudio.")
                else:
                    if audio_bytes_agenda:
                        db_audio_agenda = SessionLocal()
                        try:
                            with st.spinner("Transcrevendo áudio..."):
                                text_agenda, err_agenda = transcribe_audio(db_audio_agenda, audio_bytes_agenda, "audio.wav")
                            if err_agenda:
                                st.error(err_agenda)
                            elif text_agenda:
                                st.session_state["pending_audio_query_agenda"] = text_agenda
                                st.session_state["audio_agenda_counter"] = st.session_state.get("audio_agenda_counter", 0) + 1
                                st.success(f"Transcrito: \"{text_agenda[:80]}{'...' if len(text_agenda) > 80 else ''}\"")
                                st.rerun()
                        finally:
                            db_audio_agenda.close()

        if query_ag:
            st.session_state.agenda_chat_history.append({"role": "user", "content": query_ag})
            db_ag = SessionLocal()
            try:
                if current_user_id is not None:
                    add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "user", query_ag, None)
                agent = AgendaAgentService(db_ag)
                with st.spinner("Interpretando pedido..."):
                    # Histórico para contexto: mensagens anteriores (role + content)
                    history_ag = [
                        {"role": (m.get("role") or "user"), "content": (m.get("content") or "")}
                        for m in st.session_state.agenda_chat_history[:-1]
                    ]
                    out = agent.parse_request(query_ag, conversation_history=history_ag)
                status = out.get("status", "error")
                message = out.get("message", "")
                record = out.get("record")

                if status == "need_info":
                    st.session_state.agenda_chat_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": None,
                    })
                    if current_user_id is not None:
                        add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "assistant", message, None)
                    st.session_state.agenda_pending_record = None
                elif status == "confirm" and record:
                    st.session_state.agenda_chat_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": [record],
                    })
                    if current_user_id is not None:
                        add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "assistant", message, [record])
                    st.session_state.agenda_pending_record = record
                else:
                    fallback = message or "Não foi possível interpretar. Informe título e data (ex.: Reunião amanhã)."
                    st.session_state.agenda_chat_history.append({
                        "role": "assistant",
                        "content": fallback,
                        "records": None,
                    })
                    if current_user_id is not None:
                        add_message(db_ag, current_user_id, SCOPE_AGENDA_AGENT, "assistant", fallback, None)
                    st.session_state.agenda_pending_record = None
            finally:
                db_ag.close()
            st.rerun()

        st.markdown("---")
        if st.button("Limpar histórico", use_container_width=True, key="btn_clear_agenda"):
            if current_user_id is not None:
                db_clear = SessionLocal()
                try:
                    clear(db_clear, current_user_id, SCOPE_AGENDA_AGENT)
                finally:
                    db_clear.close()
            st.session_state.agenda_chat_history = []
            st.session_state.agenda_pending_record = None
            st.rerun()

    with tab_compromissos:
        if aba_compromissos_primeiro:
            st.caption("Você veio do link da Análise do dia (Agente de Relatórios).")
        col_form, col_list = st.columns([1, 2])

        with col_form:
            st.subheader("Novo compromisso")
            edit_id = st.session_state.get("agenda_edit_id")

            if edit_id:
                agenda_row = db.execute(
                    select(PersonalAgenda).where(PersonalAgenda.id == edit_id)
                ).scalar_one_or_none()
            else:
                agenda_row = None

            titulo_default = agenda_row.titulo if agenda_row else ""
            descricao_default = agenda_row.descricao if agenda_row else ""
            data_default = agenda_row.data if agenda_row else date.today()
            hora_default = agenda_row.hora if agenda_row else ""

            titulo = st.text_input("Título", value=titulo_default, max_chars=200)
            descricao = st.text_area(
                "Descrição (opcional)", value=descricao_default, max_chars=500, height=80
            )
            data_compromisso = st.date_input("Data", value=data_default)
            hora = st.text_input(
                "Horário (opcional, HH:MM)", value=hora_default, max_chars=5, placeholder="14:30"
            )

            if st.button(
                "Salvar compromisso" if not edit_id else "Atualizar compromisso",
                use_container_width=True,
            ):
                if not titulo.strip():
                    st.error("Informe um título para o compromisso.")
                else:
                    if agenda_row is None:
                        agenda_row = PersonalAgenda()
                        db.add(agenda_row)
                    agenda_row.user_id = current_user_id
                    agenda_row.titulo = titulo.strip()
                    agenda_row.descricao = descricao.strip() or None
                    agenda_row.data = data_compromisso
                    agenda_row.hora = hora.strip() or None
                    db.commit()
                    st.success("Compromisso salvo com sucesso.")
                    st.session_state.pop("agenda_edit_id", None)
                    st.rerun()

            if edit_id:
                if st.button("Cancelar edição", use_container_width=True):
                    st.session_state.pop("agenda_edit_id", None)
                    st.rerun()

        with col_list:
            st.subheader("Meus compromissos")
            filtro_dias = st.slider(
                "Mostrar próximos dias",
                min_value=0,
                max_value=60,
                value=30,
                help="Filtra compromissos a partir de hoje pelos próximos N dias.",
            )
            hoje = date.today()
            limite = hoje.fromordinal(hoje.toordinal() + filtro_dias)

            query = (
                db.query(PersonalAgenda)
                .filter(PersonalAgenda.data >= hoje)
                .filter(PersonalAgenda.data <= limite)
            )
            if current_user_id is not None:
                query = query.filter(PersonalAgenda.user_id == current_user_id)
            compromissos = query.order_by(PersonalAgenda.data, PersonalAgenda.hora).all()

            if not compromissos:
                st.info("Nenhum compromisso cadastrado para o período selecionado.")
            else:
                for c in compromissos:
                    cols = st.columns([3, 2, 1])
                    with cols[0]:
                        st.markdown(
                            f"**{c.titulo}**  \n"
                            f"{c.descricao or ''}"
                        )
                    with cols[1]:
                        data_txt = c.data.strftime("%d/%m/%Y")
                        hora_txt = f"{c.hora}" if c.hora else "-"
                        st.markdown(f"**Data:** {data_txt}  \n**Hora:** {hora_txt}")
                    with cols[2]:
                        if st.button(
                            "Editar",
                            key=f"edit_agenda_{c.id}",
                            use_container_width=True,
                        ):
                            st.session_state["agenda_edit_id"] = c.id
                            st.rerun()
                        if st.button(
                            "Excluir",
                            key=f"delete_agenda_{c.id}",
                            use_container_width=True,
                        ):
                            db.delete(c)
                            db.commit()
                            st.rerun()

finally:
    db.close()
