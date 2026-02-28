import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.ai_config import AIConfigManager
from config.database import SessionLocal
from models.user import User
from services.ai_service import AIService
from services.auth_service import AuthService
from utils.navigation import show_sidebar
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
    with st.expander("Configuração de IA (Agente de Relatórios)"):
        st.caption(
            "Configure o provedor de IA para o agente de relatórios por pergunta. "
            "Usado na página \"Agente Relatórios\" para interpretar perguntas em linguagem natural."
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

finally:
    db.close()

