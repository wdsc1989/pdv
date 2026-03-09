import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no path (para rodar de qualquer cwd)
_ROOT = Path(__file__).resolve().parents[0]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from config.database import init_db
from services.auth_service import AuthService, ensure_default_admin
from services.chat_memory import SCOPE_REPORT_AGENT, clear as clear_chat_memory
from utils.login_config import load_login_config
from utils.navigation import show_sidebar
from utils.sidebar_logo import get_sidebar_logo_base64_data_uri, get_sidebar_logo_path
from utils.theme import apply_theme, apply_login_vertical_center, get_theme


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
    apply_theme()
    apply_login_vertical_center()
    lc = load_login_config()
    login_title = lc.get("login_title") or "🔐 PDV - Loja de Roupas"
    login_subtitle = lc.get("login_subtitle") or "Sistema de Ponto de Venda para loja de roupas"
    login_show_title = lc.get("login_show_title", True)
    login_show_subtitle = lc.get("login_show_subtitle", True)
    login_show_logo = lc.get("login_show_logo", True)
    login_logo_align = (lc.get("login_logo_align") or "centro").strip().lower()
    if login_logo_align not in ("esquerda", "centro", "direita"):
        login_logo_align = "centro"
    use_identidade = get_theme() == "identidade_visual"

    logo_path = get_sidebar_logo_path()
    logo_data_uri = get_sidebar_logo_base64_data_uri()

    def _render_logo_and_brand():
        """Na tela de login, logo é tratada como imagem em um único bloco; alinhamento via CSS (esq/centro/dir)."""
        if not use_identidade:
            return
        align_map = {"esquerda": "vc-brand-wrap-left", "centro": "vc-brand-wrap-center", "direita": "vc-brand-wrap-right"}
        align_class = align_map.get(login_logo_align, "vc-brand-wrap-center")
        wrap_class = f"vc-brand-wrap {align_class}"
        parts = [f'<div class="{wrap_class}">']
        logo_width = lc.get("login_logo_width", 280)
        if logo_data_uri and login_show_logo:
            parts.append(
                f'<img class="vc-login-img" src="{logo_data_uri}" alt="Logo" style="max-width:100%;width:{logo_width}px;height:auto;" />'
            )
        else:
            parts.append('<p class="vc-brand-title">Vieira Closet</p>')
            parts.append('<p class="vc-brand-sub">BOUTIQUE</p>')
        if login_show_title:
            parts.append(f'<p class="vc-login-subtitle" style="margin-top:0.5rem;">🔒 {login_title}</p>')
        if login_show_subtitle and login_subtitle:
            parts.append(f'<p class="vc-login-subtitle" style="margin-top:0.25rem;">{login_subtitle}</p>')
        parts.append("</div>")
        st.markdown("".join(parts), unsafe_allow_html=True)

    if use_identidade:
        _render_logo_and_brand()
    else:
        if login_logo_align == "centro" and logo_path and login_show_logo:
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                st.image(str(logo_path), width=lc.get("login_logo_width", 280))
        elif login_logo_align == "direita" and logo_path and login_show_logo:
            c1, c2, c3 = st.columns([1, 1, 2])
            with c3:
                st.image(str(logo_path), width=lc.get("login_logo_width", 280))
        elif logo_path and login_show_logo:
            st.image(str(logo_path), width=lc.get("login_logo_width", 280))
        if login_show_title:
            st.markdown(f"# {login_title}")
        if login_show_subtitle:
            st.caption(login_subtitle)
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if use_identidade:
            st.markdown(
                '<div class="vc-login-intro">'
                '<p class="vc-login-title">Entrar no sistema</p>'
                '<p class="vc-login-subtitle">Digite seu usuário e senha para acessar o PDV.</p>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.subheader("Entrar no sistema")
            st.caption("Digite seu usuário e senha para acessar o PDV.")

        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Entrar →", use_container_width=True, type="primary")

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
                        # Atualizar análise do dia na próxima abertura do Início: limpa histórico do agente de relatórios
                        clear_chat_memory(db, user.id, SCOPE_REPORT_AGENT)
                        for key in ("chat_history", "agente_initial_analysis_user_id"):
                            st.session_state.pop(key, None)
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
    apply_theme()
    initialize_app()
    AuthService.init_session_state()

    if not AuthService.is_authenticated():
        login_page()
    else:
        show_sidebar()
        home_page()


if __name__ == "__main__":
    main()

