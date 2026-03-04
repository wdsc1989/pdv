"""
UI do Agente de Relatórios: conversa em linguagem natural, análise do dia, histórico.
Usado na página Início (app.py) para administradores.
"""
import pandas as pd
import streamlit as st

from config.database import init_db, SessionLocal
from services.auth_service import AuthService
from services.chat_memory import SCOPE_REPORT_AGENT, add_message, clear, get_messages
from services.report_agent_service import ReportAgentService
from services.speech_to_text_service import transcribe_audio
from utils.formatters import format_currency


def render_agente_relatorios_ui() -> None:
    """
    Renderiza a interface completa do Agente de Relatórios: análise do dia,
    histórico de chat, botões de navegação, input de texto, microfone e limpar histórico.
    Deve ser chamado apenas para usuários admin (caller garante).
    """
    init_db()
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "agente_initial_analysis_user_id" not in st.session_state:
        st.session_state.agente_initial_analysis_user_id = None

    user = AuthService.get_current_user()
    current_user_id = user.get("id") if user else None

    # Hidratar histórico do banco quando chat está vazio (ex.: após refresh ou novo login)
    if current_user_id is not None and len(st.session_state.chat_history) == 0:
        db_load = SessionLocal()
        try:
            loaded = get_messages(db_load, current_user_id, SCOPE_REPORT_AGENT)
            if loaded:
                st.session_state.chat_history = loaded
                st.rerun()
        finally:
            db_load.close()

    # Primeira análise ao abrir: uma vez por usuário, só quando não há histórico no DB
    deve_mostrar_inicial = (
        len(st.session_state.chat_history) == 0
        and current_user_id is not None
        and st.session_state.agente_initial_analysis_user_id != current_user_id
    )
    if deve_mostrar_inicial:
        db_init = SessionLocal()
        try:
            agent_init = ReportAgentService(db_init)
            with st.spinner("Preparando análise do dia..."):
                initial_text = agent_init.get_initial_analysis(db_init, user_id=current_user_id)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": initial_text,
                "table_data": None,
            })
            add_message(db_init, current_user_id, SCOPE_REPORT_AGENT, "assistant", initial_text, None)
            st.session_state.agente_initial_analysis_user_id = current_user_id
        except Exception:
            st.session_state.agente_initial_analysis_user_id = current_user_id
        finally:
            db_init.close()
        st.rerun()

    st.markdown(
        "<p style='margin:0 0 0.25rem 0; font-size:1.1rem;'><strong>Agente de Relatórios</strong></p>"
        "<p style='margin:0; font-size:0.8rem; color:#666;'>"
        "Pergunte sobre vendas, estoque, caixa, contas a pagar em linguagem natural."
        "</p>",
        unsafe_allow_html=True,
    )
    col_title, col_btn = st.columns([1, 0.2])
    with col_btn:
        if st.button("Atualizar análise do dia", key="btn_refresh_analise_dia", help="Gera novamente a análise do dia (limpa o histórico da conversa)."):
            if current_user_id is not None:
                db_clear = SessionLocal()
                try:
                    clear(db_clear, current_user_id, SCOPE_REPORT_AGENT)
                    st.session_state.chat_history = []
                    st.session_state.agente_initial_analysis_user_id = None
                    st.rerun()
                finally:
                    db_clear.close()
    st.markdown(
        "**Exemplos:** \"Quanto vendi este mês?\", \"Produtos mais vendidos da semana\", "
        "\"Contas a pagar deste mês\". **Análises:** \"Previsão de vendas\", \"Tendência e sazonalidade\"."
    )
    st.markdown("---")

    first_assistant_done = False
    for msg in st.session_state.chat_history:
        role = msg["role"]
        content = msg.get("content", "")
        with st.chat_message(role):
            st.markdown(content)
            if role == "assistant" and msg.get("table_data") is not None:
                df = msg["table_data"]
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
            if role == "assistant" and not first_assistant_done:
                first_assistant_done = True

    query = st.chat_input("Pergunte sobre vendas, estoque, caixa, contas a pagar...")
    query = query or st.session_state.pop("pending_audio_query", None)

    with st.expander("Gravar pelo microfone"):
        st.caption("Áudio é transcrito e enviado como pergunta (não é guardado no servidor).")
        audio_key = f"audio_relatorios_{st.session_state.get('audio_relatorios_counter', 0)}"
        audio_data = st.audio_input("Gravar áudio", key=audio_key, sample_rate=16000)
        if audio_data:
            db_audio = SessionLocal()
            try:
                with st.spinner("Transcrevendo áudio..."):
                    audio_bytes = audio_data.read()
                    text, err = transcribe_audio(db_audio, audio_bytes, "audio.wav")
                del audio_bytes
                if err:
                    st.error(err)
                elif text:
                    st.session_state["pending_audio_query"] = text
                    st.session_state["audio_relatorios_counter"] = st.session_state.get("audio_relatorios_counter", 0) + 1
                    st.success(f"Transcrito: \"{text[:80]}{'...' if len(text) > 80 else ''}\"")
                    st.rerun()
            finally:
                db_audio.close()

    if query:
        st.session_state.chat_history.append({"role": "user", "content": query})
        db = SessionLocal()
        try:
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_REPORT_AGENT, "user", query, None)
            agent = ReportAgentService(db)
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history[:-1]]
            with st.spinner("Analisando pergunta..."):
                query_analysis = agent.analyze_query(query, conversation_history=history)
            if query_analysis.get("intent") == "error":
                err_content = f"**Erro:** {query_analysis.get('error', 'Erro desconhecido')}."
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": err_content,
                    "table_data": None,
                })
                if current_user_id is not None:
                    add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", err_content, None)
                st.rerun()
            if query_analysis.get("intent") == "esclarecer_periodo":
                raw = query_analysis.get("clarification_message")
                msg = (raw if isinstance(raw, str) and raw.strip() else None) or "De qual período deseja o relatório? (ex.: hoje, esta semana, dia 02/03/2026, este mês)"
                msg_content = f"**{msg}**"
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": msg_content,
                    "table_data": None,
                })
                add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", msg_content, None)
                st.rerun()
            if query_analysis.get("intent") == "resposta_direta":
                raw = query_analysis.get("resposta_direta")
                msg = (raw if isinstance(raw, str) and raw.strip() else None) or "Não entendi. Você pode perguntar sobre faturamento, vendas, estoque, contas a pagar, etc."
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": msg,
                    "table_data": None,
                })
                if current_user_id is not None:
                    add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", msg, None)
                st.rerun()
            with st.spinner("Consultando dados..."):
                query_result = agent.execute_query(db, query_analysis)
            if query_result.get("type") == "error":
                err_content = f"**Erro:** {query_result.get('error', 'Erro desconhecido')}."
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": err_content,
                    "table_data": None,
                })
                if current_user_id is not None:
                    add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", err_content, None)
                st.rerun()
            with st.spinner("Gerando resposta..."):
                response_text = agent.format_response(query_result, query_analysis, query)
            table_data = None
            data = query_result.get("data", {})
            qt = query_result.get("type", "")
            if qt == "produtos_mais_vendidos" and data.get("items"):
                rows = [
                    {
                        "Código": i["codigo"],
                        "Nome": i["nome"],
                        "Quantidade": i["quantidade"],
                        "Receita": format_currency(i["receita"]),
                        "Lucro": format_currency(i["lucro"]),
                    }
                    for i in data["items"]
                ]
                table_data = pd.DataFrame(rows)
            elif qt == "entradas_estoque" and data.get("entradas"):
                rows = [
                    {
                        "Data": e["data_entrada"],
                        "Código": e["codigo"],
                        "Produto": e["nome"],
                        "Quantidade": e["quantidade"],
                        "Observação": e.get("observacao", ""),
                    }
                    for e in data["entradas"]
                ]
                table_data = pd.DataFrame(rows)
            elif qt == "sessoes_caixa" and data.get("sessoes"):
                rows = [
                    {
                        "ID": s["id"],
                        "Abertura": s["data_abertura"],
                        "Fechamento": s["data_fechamento"],
                        "Valor abertura": format_currency(s["valor_abertura"]),
                        "Total vendas": format_currency(s["total_vendas_sessao"]),
                        "Status": s["status"],
                    }
                    for s in data["sessoes"]
                ]
                table_data = pd.DataFrame(rows)
            elif qt == "contas_pagar" and data.get("contas"):
                rows = [
                    {
                        "Fornecedor": c["fornecedor"],
                        "Vencimento": c["data_vencimento"],
                        "Valor": format_currency(c["valor"]),
                        "Status": c["status"],
                    }
                    for c in data["contas"]
                ]
                table_data = pd.DataFrame(rows)
            elif qt == "contas_receber" and data.get("contas"):
                rows = [
                    {
                        "Cliente": c["cliente"],
                        "Vencimento": c["data_vencimento"],
                        "Valor": format_currency(c["valor"]),
                        "Status": c["status"],
                    }
                    for c in data["contas"]
                ]
                table_data = pd.DataFrame(rows)
            elif qt == "sql_result" and data.get("columns") and data.get("rows") is not None:
                table_data = pd.DataFrame(data["rows"], columns=data["columns"])
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response_text,
                "table_data": table_data,
            })
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", response_text, table_data)
            st.rerun()
        except Exception as e:
            err_content = f"**Erro:** {str(e)}"
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": err_content,
                "table_data": None,
            })
            if current_user_id is not None:
                add_message(db, current_user_id, SCOPE_REPORT_AGENT, "assistant", err_content, None)
            st.rerun()
        finally:
            db.close()

    st.markdown("---")
    if st.button("Limpar histórico", use_container_width=True, key="btn_clear_agente"):
        if current_user_id is not None:
            db_clear = SessionLocal()
            try:
                clear(db_clear, current_user_id, SCOPE_REPORT_AGENT)
            finally:
                db_clear.close()
        st.session_state.chat_history = []
        st.rerun()
