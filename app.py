import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no path (para rodar de qualquer cwd)
_ROOT = Path(__file__).resolve().parents[0]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from config.database import init_db
from services.auth_service import AuthService, ensure_default_admin
from utils.navigation import show_sidebar


st.set_page_config(
    page_title="PDV - Loja de Roupas",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": None,
    },
)


@st.cache_resource
def initialize_app():
    """
    Inicializa o banco de dados e garante usuário admin padrão.
    """
    init_db()
    ensure_default_admin()


def login_page():
    st.markdown("# 🔐 PDV - Loja de Roupas")
    st.caption("Sistema de Ponto de Venda para loja de roupas")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Entrar no sistema")
        st.caption("Digite seu usuário e senha para acessar o PDV.")
        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Ex: admin")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if submit:
            if not username or not password:
                st.error("Por favor, preencha usuário e senha.")
            else:
                from config.database import SessionLocal

                db = SessionLocal()
                try:
                    user = AuthService.authenticate(db, username, password)
                    if user:
                        AuthService.login(user)
                        st.success(f"Bem-vindo, {user.name}!")
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos.")
                finally:
                    db.close()


def home_page():
    from datetime import date

    from config.database import SessionLocal
    from models.user import User
    from services.horoscope_service import get_horoscope_for_user

    user = AuthService.get_current_user()

    st.markdown(
        "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>🏠 Início</strong></p>"
        "<p style='margin:0; font-size:0.8rem; color:#666;'>"
        + (f"Olá, {user['name']}! Use o menu ao lado para navegar." if user else "")
        + "</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Horóscopo: cache por dia (signo + data); ao mudar o dia ou signo, busca de novo (economiza tokens de IA)
    if user:
        db = SessionLocal()
        try:
            user_id = user.get("id")
            u = db.query(User).filter(User.id == user_id).first() if user_id else None
            signo = u.signo if u else user.get("signo")
            if signo:
                hoje = date.today().isoformat()
                cache = st.session_state.get("horoscope_cache")
                if (
                    cache
                    and cache.get("signo") == signo
                    and cache.get("date") == hoje
                    and cache.get("summary")
                ):
                    horoscope = cache
                else:
                    if cache and (cache.get("signo") != signo or cache.get("date") != hoje):
                        st.session_state.pop("horoscope_cache", None)
                    with st.spinner("Buscando seu horóscopo..."):
                        horoscope = get_horoscope_for_user(db, user_id or 0, signo)
                    if horoscope.get("summary"):
                        st.session_state["horoscope_cache"] = {
                            "signo": signo,
                            "date": hoje,
                            **horoscope,
                        }
                if horoscope.get("summary"):
                    st.markdown("#### 🌟 Horóscopo do dia")
                    st.markdown(horoscope["summary"])
                    if horoscope.get("source"):
                        st.caption(f"Fonte: {horoscope['source']}")
                    st.markdown("---")
            else:
                st.info(
                    "Cadastre seu **signo** em **Administração** (usuários) para ver aqui "
                    "o horóscopo do dia, buscado na internet e resumido com IA."
                )
                st.markdown("---")
        finally:
            db.close()

    # Agente de Relatórios (conversa + análise do dia) — somente para administradores
    if user and user.get("role") == "admin":
        from utils.agente_relatorios_ui import render_agente_relatorios_ui

        render_agente_relatorios_ui()


def main():
    initialize_app()
    AuthService.init_session_state()

    if not AuthService.is_authenticated():
        login_page()
    else:
        show_sidebar()
        home_page()


if __name__ == "__main__":
    main()

