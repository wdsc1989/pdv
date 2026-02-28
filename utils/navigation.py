import streamlit as st

from services.auth_service import AuthService
from utils.sidebar_logo import get_sidebar_logo_path


def show_sidebar() -> None:
    """
    Sidebar com informações do usuário e links para as páginas do PDV.
    Exibe a logo em uploads/logo/ se existir; caso contrário, o título "PDV".
    """
    user = AuthService.get_current_user()
    role = user["role"] if user else None

    with st.sidebar:
        logo_path = get_sidebar_logo_path()
        if logo_path:
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown("## 🛍️ PDV")
        if user:
            st.markdown(f"**{user['name']}**")
            st.caption(f"Perfil: {role}")

        st.markdown("---")
        st.markdown("### Menu")
        st.page_link("app.py", label="Início", icon="🏠")
        st.page_link("pages/0_Caixa.py", label="Caixa", icon="💰")
        st.page_link("pages/1_Produtos.py", label="Produtos", icon="📦")
        st.page_link("pages/4_Vendas.py", label="Vendas", icon="🧾")
        st.page_link("pages/7_Acessorios.py", label="Acessórios", icon="💎")
        st.page_link("pages/5_Contas_a_Pagar.py", label="Contas a Pagar", icon="📄")
        st.page_link("pages/3_Relatorios.py", label="Relatórios", icon="📈")
        if role in ("admin", "gerente"):
            st.page_link("pages/Agente_Relatorios.py", label="Agente Relatórios", icon="🤖")
        if role == "admin":
            st.page_link("pages/10_Admin.py", label="Administração", icon="⚙️")

        st.markdown("---")
        if st.button("Sair", use_container_width=True):
            AuthService.logout()
            if hasattr(st, "switch_page"):
                st.switch_page("app.py")
            else:
                st.rerun()

        