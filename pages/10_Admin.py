import sys
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
from sqlalchemy import select

from config.ai_config import AIConfigManager
from config.database import SessionLocal
from config.prompt_config import (
    ACCOUNTS_AGENT_KEYS,
    AGENDA_AGENT_KEYS,
    DEFAULTS,
    PLACEHOLDERS_HELP,
    PromptConfigManager,
    REPORT_AGENT_KEYS,
)
from models.user import User
from services.ai_service import AIService
from services.auth_service import AuthService
from services.accounts_agent_service import AccountsAgentService
from services.agenda_agent_service import AgendaAgentService
from services.report_agent_service import ReportAgentService
from utils.formatters import format_currency
from utils.navigation import show_sidebar
from utils.login_config import load_login_config, save_login_config
from utils.receipt_config import load_receipt_config, save_receipt_config
from utils.sidebar_logo import get_sidebar_logo_path, remove_sidebar_logo, save_sidebar_logo


st.set_page_config(page_title="Administração", page_icon="⚙️", layout="wide")

AuthService.require_roles(["admin"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>⚙️ Administração</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Crie e gerencie usuários. Perfis: admin, gerente ou vendedor.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    col_form, col_list = st.columns([1, 2])

    SIGNOS = [
        ("", "— Sem signo —"),
        ("aries", "Áries"),
        ("touro", "Touro"),
        ("gemeos", "Gêmeos"),
        ("cancer", "Câncer"),
        ("leao", "Leão"),
        ("virgem", "Virgem"),
        ("libra", "Libra"),
        ("escorpiao", "Escorpião"),
        ("sagitario", "Sagitário"),
        ("capricornio", "Capricórnio"),
        ("aquario", "Aquário"),
        ("peixes", "Peixes"),
    ]

    with col_form:
        st.subheader("Criar novo usuário")
        username = st.text_input("Usuário (login)")
        name = st.text_input("Nome")
        password = st.text_input("Senha", type="password")
        role = st.selectbox("Perfil", options=["admin", "gerente", "vendedor"])
        signo_create = st.selectbox(
            "Signo (horóscopo)",
            options=[v[0] for v in SIGNOS],
            format_func=lambda x: next((v[1] for v in SIGNOS if v[0] == x), x or "—"),
        )

        if st.button("Criar usuário", type="primary", use_container_width=True):
            if not username or not name or not password:
                st.error("Usuário, nome e senha são obrigatórios.")
            else:
                existe = (
                    db.query(User).filter(User.username == username).first()
                )
                if existe:
                    st.error("Já existe um usuário com este login.")
                else:
                    from services.auth_service import AuthService as AS

                    AS.create_user(
                        db=db,
                        username=username,
                        name=name,
                        password=password,
                        role=role,
                        signo=signo_create if signo_create else None,
                    )
                    st.success("Usuário criado com sucesso.")
                    st.rerun()

    with col_list:
        st.subheader("Usuários cadastrados")
        users = db.execute(select(User).order_by(User.username)).scalars().all()
        if not users:
            st.info("Nenhum usuário cadastrado além do admin padrão.")
        else:
            signo_label = {v[0]: v[1] for v in SIGNOS}
            linhas = []
            for u in users:
                linhas.append(
                    {
                        "ID": u.id,
                        "Usuário": u.username,
                        "Nome": u.name,
                        "Perfil": u.role,
                        "Signo": signo_label.get(u.signo or "", u.signo or "—"),
                        "Ativo": "Sim" if u.active else "Não",
                    }
                )
            st.dataframe(linhas, use_container_width=True, hide_index=True)

        st.caption("Alterar signo de um usuário:")
        user_options = [(u.id, f"{u.username} ({u.name})") for u in (users or [])]
        if user_options:
            user_id_edit = st.selectbox(
                "Usuário",
                options=[x[0] for x in user_options],
                format_func=lambda x: next((n for i, n in user_options if i == x), ""),
                key="edit_signo_user",
            )
            signo_edit = st.selectbox(
                "Novo signo",
                options=[v[0] for v in SIGNOS],
                format_func=lambda x: next((v[1] for v in SIGNOS if v[0] == x), x or "—"),
                key="edit_signo_value",
            )
            if st.button("Salvar signo", key="save_signo_btn"):
                usr = db.query(User).filter(User.id == user_id_edit).first()
                if usr:
                    usr.signo = signo_edit if signo_edit else None
                    db.commit()
                    st.success("Signo atualizado.")
                    st.rerun()

    # Seção de dados de teste só aparece quando habilitada explicitamente via variável de ambiente.
    # Em produção, NÃO defina PDV_ENABLE_TEST_DATA=1 para evitar que scripts de seed sejam expostos.
    if os.getenv("PDV_ENABLE_TEST_DATA") == "1":
        st.markdown("---")
        with st.expander("Dados de teste (produtos e vendas)"):
            st.caption(
                "Use para popular o sistema com produtos e vendas de exemplo. "
                "Produtos de teste podem ser criados/atualizados sem afetar vendas. "
                "Vendas de teste **substituem** todas as vendas e sessões de caixa atuais."
            )
            col_pp, col_vv = st.columns(2)
            with col_pp:
                if st.button("Criar/atualizar produtos de teste", key="seed_products_btn", use_container_width=True):
                    try:
                        from scripts.seed_products import main as seed_main
                        seed_main()
                        st.success("Produtos de teste criados ou atualizados.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao executar seed de produtos: {e}")
            with col_vv:
                if st.button("Criar vendas de teste (reseta vendas e caixa)", key="seed_sales_btn", use_container_width=True):
                    try:
                        from scripts.reset_and_seed_sales import main as seed_sales_main
                        seed_sales_main()
                        st.success("Vendas de teste criadas. Uma sessão de caixa aberta foi criada.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao executar seed de vendas: {e}")

    st.markdown("---")
    with st.expander("Logo do menu (sidebar)"):
        st.caption(
            "Adicione uma logo para aparecer no menu lateral, no lugar do texto \"PDV\". "
            "Formatos: PNG, JPG, JPEG ou WEBP. Largura recomendada: até 200px."
        )
        logo_path = get_sidebar_logo_path()
        if logo_path:
            st.image(str(logo_path), width=180)
            if st.button("Remover logo", key="remove_logo_btn"):
                remove_sidebar_logo()
                st.success("Logo removida. O menu voltará a exibir \"PDV\".")
                st.rerun()
        logo_file = st.file_uploader(
            "Enviar nova logo",
            type=["png", "jpg", "jpeg", "webp"],
            key="sidebar_logo_upload",
        )
        if logo_file:
            save_sidebar_logo(logo_file.getvalue(), logo_file.name)
            st.success("Logo salva. Atualize a página ou navegue para ver no menu.")
            st.rerun()

    st.markdown("---")
    with st.expander("Tela de login"):
        st.caption(
            "Título e subtítulo exibidos na tela de login. "
            "A logo exibida na tela de login é a mesma do menu lateral. "
            "Para alterá-la, use o bloco 'Logo do menu (sidebar)' acima."
        )
        lc = load_login_config()
        login_title = st.text_input(
            "Título da tela de login",
            value=lc.get("login_title", ""),
            placeholder="Ex: 🔐 PDV - Loja de Roupas",
            key="admin_login_title",
        )
        login_subtitle = st.text_input(
            "Subtítulo",
            value=lc.get("login_subtitle", ""),
            placeholder="Ex: Sistema de Ponto de Venda para loja de roupas",
            key="admin_login_subtitle",
        )
        login_show_logo = st.checkbox(
            "Exibir logo na tela de login",
            value=lc.get("login_show_logo", True),
            key="admin_login_show_logo",
        )
        login_logo_width = st.number_input(
            "Largura da logo na tela de login (px)",
            min_value=120,
            max_value=500,
            value=int(lc.get("login_logo_width", 280)),
            step=20,
            key="admin_login_logo_width",
        )
        if st.button("Salvar", key="login_config_save_btn", type="primary"):
            save_login_config({
                "login_title": login_title or lc.get("login_title", ""),
                "login_subtitle": login_subtitle or lc.get("login_subtitle", ""),
                "login_show_logo": login_show_logo,
                "login_logo_width": login_logo_width,
            })
            st.success("Configuração da tela de login salva.")
            st.rerun()

    st.markdown("---")
    with st.expander("Layout do recibo para impressão"):
        st.caption(
            "Ajuste o layout do recibo não fiscal conforme a impressora (largura do papel, margens, fonte)."
        )
        rc = load_receipt_config()
        c1, c2 = st.columns(2)
        with c1:
            paper_width_mm = st.number_input(
                "Largura do papel (mm)",
                min_value=58,
                max_value=120,
                value=rc.get("paper_width_mm", 80),
                step=1,
            )
            margin_mm = st.number_input(
                "Margem (mm)",
                min_value=0,
                max_value=20,
                value=rc.get("margin_mm", 5),
                step=1,
            )
            font_size_pt = st.number_input(
                "Tamanho da fonte (pt)",
                min_value=8,
                max_value=14,
                value=rc.get("font_size_pt", 10),
                step=1,
            )
        with c2:
            header_text = st.text_input(
                "Texto do cabeçalho",
                value=rc.get("header_text", ""),
                placeholder="Ex: LOJA DE ROUPAS",
            )
            subheader_text = st.text_input(
                "Subtítulo do recibo",
                value=rc.get("subheader_text", "Extrato nao fiscal"),
            )
            footer_text = st.text_input(
                "Texto do rodapé",
                value=rc.get("footer_text", ""),
                placeholder="Ex: Obrigado pela preferencia!",
            )
        if st.button("Salvar configuração do recibo", type="primary"):
            save_receipt_config(
                {
                    "paper_width_mm": paper_width_mm,
                    "margin_mm": margin_mm,
                    "font_size_pt": font_size_pt,
                    "header_text": header_text or "",
                    "subheader_text": subheader_text or "Extrato nao fiscal",
                    "footer_text": footer_text or "",
                    "copies": rc.get("copies", 1),
                }
            )
            st.success("Configuração do recibo salva.")

    st.markdown("---")
    with st.expander("Configuração de IA (Agentes de Relatórios e de Contas)"):
        st.caption(
            "Configure o provedor de IA usado por **ambos** os agentes. "
            "**Agente de Relatórios:** na página Início (perguntas em linguagem natural). "
            "**Agente de Contas:** páginas \"Agente de Contas\" e \"Contas a Pagar\" (cadastro de contas a pagar/receber). "
            "Somente administradores têm acesso a esta administração."
        )
        current_ai = AIConfigManager.get_config(db)
        if current_ai:
            st.info(
                f"**IA ativa:** {current_ai.provider.upper()} — {current_ai.model or 'modelo padrão'}"
            )
        else:
            st.warning("Nenhuma configuração de IA ativa. Configure abaixo para usar o agente de relatórios.")

        with st.form("ai_config_form"):
            provider = st.selectbox(
                "Provedor",
                options=["openai", "gemini", "ollama", "groq"],
                format_func=lambda x: {
                    "openai": "OpenAI (GPT)",
                    "gemini": "Google Gemini",
                    "ollama": "Ollama (local)",
                    "groq": "Groq",
                }[x],
            )
            api_key = st.text_input(
                "Chave de API",
                type="password",
                placeholder="Deixe em branco para Ollama",
            )
            if provider == "openai":
                model = st.text_input("Modelo", value="gpt-4o-mini")
                base_url = None
            elif provider == "gemini":
                model = st.text_input("Modelo", value="gemini-1.5-flash")
                base_url = None
            elif provider == "groq":
                model = st.text_input("Modelo", value="llama-3.3-70b-versatile")
                base_url = None
            else:
                model = st.text_input("Modelo", value="llama3.2")
                base_url = st.text_input(
                    "URL base (Ollama)",
                    value="http://localhost:11434",
                    help="Ex.: http://localhost:11434",
                )
            enabled = st.checkbox("Ativar esta configuração", value=True)
            submit = st.form_submit_button("Salvar")
            test_btn = st.form_submit_button("Testar conexão")

            if submit:
                key = api_key if api_key else ("ollama" if provider == "ollama" else "")
                if provider != "ollama" and not key:
                    st.error("Informe a chave de API.")
                else:
                    try:
                        AIConfigManager.save_config(
                            db=db,
                            provider=provider,
                            api_key=key,
                            model=model,
                            base_url=base_url if provider == "ollama" else None,
                            enabled=enabled,
                        )
                        st.success("Configuração salva.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

            if test_btn:
                key = api_key if api_key else ("ollama" if provider == "ollama" else "")
                if provider != "ollama" and not key:
                    st.error("Informe a chave de API para testar.")
                else:
                    try:
                        AIConfigManager.save_config(
                            db=db,
                            provider=provider,
                            api_key=key,
                            model=model,
                            base_url=base_url if provider == "ollama" else None,
                            enabled=True,
                        )
                        db.commit()
                        ai = AIService(db)
                        success, msg = ai.test_connection()
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                        if current_ai and current_ai.provider != provider:
                            AIConfigManager.delete_config(db, provider)
                            AIConfigManager.save_config(
                                db=db,
                                provider=current_ai.provider,
                                api_key=current_ai.api_key,
                                model=current_ai.model,
                                base_url=current_ai.base_url,
                                enabled=True,
                            )
                        elif not current_ai:
                            AIConfigManager.delete_config(db, provider)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao testar: {e}")

        st.markdown("**Configurações salvas**")
        all_ai = AIConfigManager.get_all_configs(db)
        if all_ai:
            for cfg in all_ai:
                with st.expander(
                    f"{'Ativo' if cfg.enabled else 'Inativo'}: {cfg.provider.upper()} — {cfg.model or 'padrão'}"
                ):
                    if st.button("Excluir", key=f"del_ai_{cfg.id}"):
                        AIConfigManager.delete_config(db, cfg.provider)
                        st.success("Configuração excluída.")
                        st.rerun()
        else:
            st.caption("Nenhuma configuração cadastrada.")

    st.markdown("---")
    with st.expander("Prompts do Agente de Relatórios"):
        st.caption(
            "Edite os textos (templates) usados pelo agente de relatórios. "
            "Cada prompt aceita placeholders que são preenchidos automaticamente (ex.: data_hoje, query). "
            "Use os botões abaixo para salvar ou restaurar o texto padrão."
        )
        prompt_labels = {
            "report_agent.analyze_query": "Análise da pergunta (analyze_query)",
            "report_agent.initial_analysis": "Análise do dia (initial_analysis)",
            "report_agent.format_response_analise_avancada": "Formatação: análise avançada",
            "report_agent.format_response_generic": "Formatação: resposta genérica",
        }
        for key in REPORT_AGENT_KEYS:
            with st.expander(prompt_labels.get(key, key)):
                current = PromptConfigManager.get_or_default(db, key, DEFAULTS[key])
                st.caption(PLACEHOLDERS_HELP.get(key, ""))
                new_value = st.text_area(
                    "Texto do prompt",
                    value=current,
                    height=220 if key == "report_agent.analyze_query" else 180,
                    key=f"prompt_ta_{key}",
                )
                col_save, col_restore = st.columns(2)
                with col_save:
                    if st.button("Salvar", key=f"prompt_save_{key}"):
                        PromptConfigManager.set(db, key, new_value)
                        st.success("Prompt salvo.")
                        st.rerun()
                with col_restore:
                    if st.button("Restaurar padrão", key=f"prompt_restore_{key}"):
                        PromptConfigManager.delete(db, key)
                        st.success("Padrão restaurado (valor do banco removido).")
                        st.rerun()

        st.markdown("**Testar**")
        st.caption(
            "Converse com o agente como na página Início. A resposta exibida é a do agente (não o JSON interno). "
            "Se o agente pedir esclarecimento (ex.: \"De qual período?\"), digite a resposta abaixo e envie para continuar."
        )
        if "prompt_test_history" not in st.session_state:
            st.session_state.prompt_test_history = []

        # Prova de uso do histórico: exibe o contexto que será enviado ao agente
        if st.session_state.prompt_test_history:
            with st.expander("Prova de uso do histórico: contexto enviado ao agente"):
                st.caption(
                    "O agente recebe as últimas mensagens abaixo como **conversation_history**. "
                    "Com isso ele entende respostas como \"ano atual\", \"este mês\" ou \"hoje\" em função do que foi perguntado antes (ex.: \"contas a pagar do ano\" → \"ano atual\" = ano completo)."
                )
                # Mesmo formato que enviamos para analyze_query (últimas 20)
                history_for_preview = [
                    {"role": m["role"], "content": m.get("content") or ""}
                    for m in st.session_state.prompt_test_history[-20:]
                ]
                for i, h in enumerate(history_for_preview):
                    role_label = "Usuário" if h["role"] == "user" else "Assistente"
                    content = h["content"]
                    preview = (content[:400] + "..." if len(content) > 400 else content).replace("\n", " ")
                    st.text(f"{i + 1}. [{role_label}] {preview}")
                st.caption(f"Mensagens no contexto: {len(history_for_preview)} (máx. 20 usadas pelo agente na análise).")

                # Última análise: JSON completo e caminho escolhido (quando disponível)
                if st.session_state.get("last_analysis_debug"):
                    debug = st.session_state.last_analysis_debug
                    st.markdown("---")
                    st.markdown("**Última pergunta analisada:**")
                    st.code(st.session_state.get("last_analysis_question", ""), language=None)
                    st.markdown("**Caminho escolhido:**")
                    st.code(debug.get("path", ""), language=None)
                    st.markdown("**JSON bruto (resposta da IA):**")
                    st.json(debug.get("raw_json"))
                    st.markdown("**JSON final (após fallbacks, usado na execução):**")
                    st.json(debug.get("final_json"))

        for msg in st.session_state.prompt_test_history:
            role = msg["role"]
            content = msg.get("content", "")
            label = "**Você**" if role == "user" else "**Agente**"
            st.markdown(f"{label}")
            st.markdown(content)
            if role == "assistant" and msg.get("table_data") is not None:
                df = msg["table_data"]
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown("---")

        with st.form("prompt_test_chat_form"):
            test_msg = st.text_input(
                "Sua mensagem",
                placeholder="Ex.: Qual o faturamento de hoje? ou De qual período?",
                key="prompt_test_input",
            )
            col_send, col_clear, col_day = st.columns([1, 1, 1])
            with col_send:
                submit_chat = st.form_submit_button("Enviar")
            with col_clear:
                submit_clear = st.form_submit_button("Limpar conversa")
            with col_day:
                submit_day = st.form_submit_button("Testar análise do dia")

        if submit_clear:
            st.session_state.prompt_test_history = []
            st.session_state.last_analysis_debug = None
            st.session_state.last_analysis_question = None
            st.rerun()

        if submit_day:
            try:
                svc = ReportAgentService(db)
                markdown = svc.get_initial_analysis(db)
                st.session_state.prompt_test_history.append({
                    "role": "assistant",
                    "content": markdown,
                    "table_data": None,
                })
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        if submit_chat and (test_msg or "").strip():
            user_text = (test_msg or "").strip()
            st.session_state.prompt_test_history.append({"role": "user", "content": user_text})
            try:
                svc = ReportAgentService(db)
                history_for_agent = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.prompt_test_history[:-1]
                ]
                result = svc.analyze_query(
                    user_text,
                    conversation_history=history_for_agent,
                    return_debug=True,
                )
                if isinstance(result, dict) and "debug" in result:
                    st.session_state.last_analysis_debug = result["debug"]
                    st.session_state.last_analysis_question = user_text
                    query_analysis = result["analysis"]
                else:
                    query_analysis = result
                    st.session_state.last_analysis_debug = None
                    st.session_state.last_analysis_question = None

                if query_analysis.get("intent") == "error":
                    st.session_state.prompt_test_history.append({
                        "role": "assistant",
                        "content": f"**Erro:** {query_analysis.get('error', 'Erro desconhecido')}.",
                        "table_data": None,
                    })
                    st.rerun()

                if query_analysis.get("intent") == "esclarecer_periodo":
                    raw = query_analysis.get("clarification_message")
                    msg = (raw if isinstance(raw, str) and raw.strip() else None) or "De qual período deseja o relatório? (ex.: hoje, esta semana, este mês)"
                    st.session_state.prompt_test_history.append({
                        "role": "assistant",
                        "content": f"**{msg}**",
                        "table_data": None,
                    })
                    st.rerun()

                if query_analysis.get("intent") == "resposta_direta":
                    raw = query_analysis.get("resposta_direta")
                    msg = (raw if isinstance(raw, str) and raw.strip() else None) or "Não entendi. Você pode perguntar sobre faturamento, vendas, estoque, contas a pagar, etc."
                    st.session_state.prompt_test_history.append({
                        "role": "assistant",
                        "content": msg,
                        "table_data": None,
                    })
                    st.rerun()

                query_result = svc.execute_query(db, query_analysis)
                if query_result.get("type") == "error":
                    st.session_state.prompt_test_history.append({
                        "role": "assistant",
                        "content": f"**Erro:** {query_result.get('error', 'Erro desconhecido')}.",
                        "table_data": None,
                    })
                    st.rerun()

                response_text = svc.format_response(query_result, query_analysis, user_text)
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

                st.session_state.prompt_test_history.append({
                    "role": "assistant",
                    "content": response_text,
                    "table_data": table_data,
                })
                st.rerun()
            except Exception as e:
                st.session_state.prompt_test_history.append({
                    "role": "assistant",
                    "content": f"**Erro:** {str(e)}",
                    "table_data": None,
                })
                st.rerun()

    st.markdown("---")
    with st.expander("Prompts do Agente de Contas (Contas a Pagar e Receber)"):
        st.caption(
            "Edite os textos (templates) usados pelo agente de contas. "
            "O **mesmo provedor de IA** configurado acima é usado. "
            "Placeholders são preenchidos automaticamente (ex.: data_hoje, history_block, message). "
            "Use os botões para salvar ou restaurar o texto padrão."
        )
        acc_prompt_labels = {
            "accounts_agent.parse_request": "Interpretação do pedido (parse_request)",
        }
        for key in ACCOUNTS_AGENT_KEYS:
            with st.expander(acc_prompt_labels.get(key, key)):
                current = PromptConfigManager.get_or_default(db, key, DEFAULTS[key])
                st.caption(PLACEHOLDERS_HELP.get(key, ""))
                new_value = st.text_area(
                    "Texto do prompt",
                    value=current,
                    height=280,
                    key=f"acc_prompt_ta_{key}",
                )
                col_save, col_restore = st.columns(2)
                with col_save:
                    if st.button("Salvar", key=f"acc_prompt_save_{key}"):
                        PromptConfigManager.set(db, key, new_value)
                        st.success("Prompt salvo.")
                        st.rerun()
                with col_restore:
                    if st.button("Restaurar padrão", key=f"acc_prompt_restore_{key}"):
                        PromptConfigManager.delete(db, key)
                        st.success("Padrão restaurado.")
                        st.rerun()

        st.markdown("**Testar**")
        st.caption(
            "Converse com o agente como na página Agente de Contas. "
            "O histórico é enviado como **conversation_history** (mesma lógica do agente de relatórios). "
            "Nenhum cadastro ou baixa é gravado no teste."
        )
        if "accounts_test_history" not in st.session_state:
            st.session_state.accounts_test_history = []

        if st.session_state.accounts_test_history:
            with st.expander("Prova de uso do histórico: contexto enviado ao agente"):
                st.caption(
                    "O agente recebe as últimas mensagens abaixo como **conversation_history**. "
                    "Com isso ele mantém o contexto do cadastro (fornecedor, valor, descrição, etc.)."
                )
                history_acc_preview = [
                    {"role": m["role"], "content": m.get("content", "")}
                    for m in st.session_state.accounts_test_history[-10:]
                ]
                for i, h in enumerate(history_acc_preview):
                    role_label = "Usuário" if h["role"] == "user" else "Assistente"
                    content = h["content"]
                    preview = (content[:400] + "..." if len(content) > 400 else content).replace("\n", " ")
                    st.text(f"{i + 1}. [{role_label}] {preview}")
                st.caption(f"Mensagens no contexto: {len(history_acc_preview)} (máx. 10 usadas pelo agente).")

        for msg in st.session_state.accounts_test_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            st.markdown("**Você**" if role == "user" else "**Agente**")
            st.markdown(content)
            if role == "assistant" and msg.get("records"):
                recs = msg["records"]
                if recs and len(recs) <= 20:
                    for i, r in enumerate(recs, 1):
                        v = r.get("valor", 0)
                        d = r.get("data_vencimento", "")
                        if r.get("tipo") == "pagar":
                            st.caption(f"{i}. {r.get('fornecedor', '')} — {format_currency(v)} — venc. {d}")
                        else:
                            st.caption(f"{i}. {r.get('cliente', '')} — {format_currency(v)} — venc. {d}")
                elif recs:
                    st.caption(f"*{len(recs)} registros.*")
            st.markdown("---")

        with st.form("accounts_test_form"):
            acc_msg = st.text_input(
                "Sua mensagem",
                placeholder="Ex.: Cadastre conta de energia 120 reais para 10/02/2026",
                key="accounts_test_input",
            )
            col_acc_send, col_acc_clear = st.columns(2)
            with col_acc_send:
                submit_acc = st.form_submit_button("Enviar")
            with col_acc_clear:
                submit_acc_clear = st.form_submit_button("Limpar conversa")

        if submit_acc_clear:
            st.session_state.accounts_test_history = []
            st.rerun()

        if submit_acc and (acc_msg or "").strip():
            user_text = (acc_msg or "").strip()
            st.session_state.accounts_test_history.append({"role": "user", "content": user_text})
            try:
                agent = AccountsAgentService(db)
                history_acc = [
                    {"role": m["role"], "content": m.get("content", "")}
                    for m in st.session_state.accounts_test_history[:-1]
                ]
                out = agent.parse_request(user_text, conversation_history=history_acc, context={})
                status = out.get("status", "error")
                message = out.get("message", "")
                records = out.get("records", [])
                baixa = out.get("baixa")
                if status == "need_info":
                    st.session_state.accounts_test_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": None,
                    })
                elif status == "confirm" and baixa:
                    st.session_state.accounts_test_history.append({
                        "role": "assistant",
                        "content": message + "\n\n*(Teste: baixa não foi executada.)*",
                        "records": None,
                    })
                elif status == "confirm" and records:
                    st.session_state.accounts_test_history.append({
                        "role": "assistant",
                        "content": message + "\n\n*(Teste: nenhum cadastro foi gravado.)*",
                        "records": records,
                    })
                elif status == "error":
                    st.session_state.accounts_test_history.append({
                        "role": "assistant",
                        "content": f"**Erro:** {message}",
                        "records": None,
                    })
                else:
                    st.session_state.accounts_test_history.append({
                        "role": "assistant",
                        "content": message or "Resposta do agente.",
                        "records": records,
                    })
            except Exception as e:
                st.session_state.accounts_test_history.append({
                    "role": "assistant",
                    "content": f"**Erro:** {str(e)}",
                    "records": None,
                })
            st.rerun()

    st.markdown("---")
    with st.expander("Prompts do Agente de Agenda (página Agenda)"):
        st.caption(
            "Edite o texto (template) usado pelo agente de agenda na página Agenda. "
            "O mesmo provedor de IA configurado acima é usado. "
            "Placeholders: data_hoje, history_block, message. "
            "Use os botões para salvar ou restaurar o texto padrão."
        )
        agenda_prompt_labels = {
            "agenda_agent.parse_request": "Interpretação do pedido (parse_request)",
        }
        for key in AGENDA_AGENT_KEYS:
            with st.expander(agenda_prompt_labels.get(key, key)):
                current = PromptConfigManager.get_or_default(db, key, DEFAULTS[key])
                st.caption(PLACEHOLDERS_HELP.get(key, ""))
                new_value = st.text_area(
                    "Texto do prompt",
                    value=current,
                    height=280,
                    key=f"agenda_prompt_ta_{key}",
                )
                col_save, col_restore = st.columns(2)
                with col_save:
                    if st.button("Salvar", key=f"agenda_prompt_save_{key}"):
                        PromptConfigManager.set(db, key, new_value)
                        st.success("Prompt salvo.")
                        st.rerun()
                with col_restore:
                    if st.button("Restaurar padrão", key=f"agenda_prompt_restore_{key}"):
                        PromptConfigManager.delete(db, key)
                        st.success("Padrão restaurado.")
                        st.rerun()

        st.markdown("**Testar**")
        st.caption(
            "Converse com o agente como na página Agenda (aba Agente). "
            "Nenhum compromisso é gravado no teste."
        )
        if "agenda_test_history" not in st.session_state:
            st.session_state.agenda_test_history = []

        if st.session_state.agenda_test_history:
            with st.expander("Contexto enviado ao agente (últimas mensagens)"):
                history_ag_preview = [
                    {"role": m["role"], "content": m.get("content", "")}
                    for m in st.session_state.agenda_test_history[-10:]
                ]
                for i, h in enumerate(history_ag_preview):
                    role_label = "Usuário" if h["role"] == "user" else "Assistente"
                    content = h["content"]
                    preview = (content[:400] + "..." if len(content) > 400 else content).replace("\n", " ")
                    st.text(f"{i + 1}. [{role_label}] {preview}")

        for msg in st.session_state.agenda_test_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            st.markdown("**Você**" if role == "user" else "**Agente**")
            st.markdown(content)
            if role == "assistant" and msg.get("records") and len(msg["records"]) == 1:
                r = msg["records"][0]
                st.caption(f"*Compromisso: {r.get('titulo', '')} — {r.get('data', '')} {r.get('hora') or ''}*")
            st.markdown("---")

        with st.form("agenda_test_form"):
            agenda_msg = st.text_input(
                "Sua mensagem",
                placeholder="Ex.: Reunião amanhã às 14h",
                key="agenda_test_input",
            )
            col_ag_send, col_ag_clear = st.columns(2)
            with col_ag_send:
                submit_ag = st.form_submit_button("Enviar")
            with col_ag_clear:
                submit_ag_clear = st.form_submit_button("Limpar conversa")

        if submit_ag_clear:
            st.session_state.agenda_test_history = []
            st.rerun()

        if submit_ag and (agenda_msg or "").strip():
            user_text = (agenda_msg or "").strip()
            st.session_state.agenda_test_history.append({"role": "user", "content": user_text})
            try:
                agent = AgendaAgentService(db)
                history_ag = [
                    {"role": m["role"], "content": m.get("content", "")}
                    for m in st.session_state.agenda_test_history[:-1]
                ]
                out = agent.parse_request(user_text, conversation_history=history_ag)
                status = out.get("status", "error")
                message = out.get("message", "")
                record = out.get("record")
                if status == "need_info":
                    st.session_state.agenda_test_history.append({
                        "role": "assistant",
                        "content": message,
                        "records": None,
                    })
                elif status == "confirm" and record:
                    st.session_state.agenda_test_history.append({
                        "role": "assistant",
                        "content": message + "\n\n*(Teste: nenhum compromisso foi gravado.)*",
                        "records": [record],
                    })
                elif status == "error":
                    st.session_state.agenda_test_history.append({
                        "role": "assistant",
                        "content": f"**Erro:** {message}",
                        "records": None,
                    })
                else:
                    st.session_state.agenda_test_history.append({
                        "role": "assistant",
                        "content": message or "Resposta do agente.",
                        "records": None,
                    })
            except Exception as e:
                st.session_state.agenda_test_history.append({
                    "role": "assistant",
                    "content": f"**Erro:** {str(e)}",
                    "records": None,
                })
            st.rerun()

finally:
    db.close()

