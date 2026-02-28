"""
Página do Agente de Relatórios: perguntas em linguagem natural, respostas em tempo real.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from config.database import SessionLocal
from services.auth_service import AuthService
from services.report_agent_service import ReportAgentService
from utils.formatters import format_currency
from utils.navigation import show_sidebar

st.set_page_config(page_title="Agente Relatórios", page_icon="🤖", layout="wide")

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>🤖 Agente de Relatórios</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>"
    "Faça perguntas em linguagem natural e receba relatórios em tempo real com base nos dados do PDV."
    "</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "**Exemplos:** \"Quanto vendi este mês?\", \"Produtos mais vendidos da semana\", "
    "\"Valor do estoque\", \"Contas a pagar deste mês\", \"Sessões de caixa\". "
    "**Análises avançadas:** \"Previsão de vendas\", \"Tendência e sazonalidade\", \"Análise avançada com notícias\"."
)
st.markdown("---")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "agente_initial_analysis_user_id" not in st.session_state:
    st.session_state.agente_initial_analysis_user_id = None

user = AuthService.get_current_user()
current_user_id = user.get("id") if user else None
# Primeira análise ao abrir: uma vez por usuário; ao trocar de usuário (logout/login), mostra de novo
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
            initial_text = agent_init.get_initial_analysis(db_init)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": initial_text,
            "table_data": None,
        })
        st.session_state.agente_initial_analysis_user_id = current_user_id
    except Exception:
        st.session_state.agente_initial_analysis_user_id = current_user_id
    finally:
        db_init.close()
    st.rerun()

for msg in st.session_state.chat_history:
    role = msg["role"]
    content = msg.get("content", "")
    with st.chat_message(role):
        st.markdown(content)
        if role == "assistant" and msg.get("table_data") is not None:
            df = msg["table_data"]
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)

query = st.chat_input("Pergunte sobre vendas, estoque, caixa ou contas a pagar...")

if query:
    st.session_state.chat_history.append({"role": "user", "content": query})
    db = SessionLocal()
    try:
        agent = ReportAgentService(db)
        with st.spinner("Analisando pergunta..."):
            query_analysis = agent.analyze_query(query)
        if query_analysis.get("intent") == "error":
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"**Erro:** {query_analysis.get('error', 'Erro desconhecido')}.",
                "table_data": None,
            })
            st.rerun()
        with st.spinner("Consultando dados..."):
            query_result = agent.execute_query(db, query_analysis)
        if query_result.get("type") == "error":
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"**Erro:** {query_result.get('error', 'Erro desconhecido')}.",
                "table_data": None,
            })
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
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response_text,
            "table_data": table_data,
        })
        st.rerun()
    except Exception as e:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"**Erro:** {str(e)}",
            "table_data": None,
        })
        st.rerun()
    finally:
        db.close()

st.markdown("---")
if st.button("Limpar histórico", use_container_width=True):
    st.session_state.chat_history = []
    st.rerun()
