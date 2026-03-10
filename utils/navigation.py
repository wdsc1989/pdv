import streamlit as st

from services.auth_service import AuthService
from utils.sidebar_logo import get_sidebar_logo_path
from utils.theme import apply_theme

# CSS: ícones do menu dourados e texto preto (aplica em todas as páginas com sidebar)
MENU_GOLD_CSS = """
<style>
section[data-testid="stSidebar"] [data-testid="stPageLink"] {
  color: #000000 !important;
}
section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover {
  color: #000000 !important;
}
section[data-testid="stSidebar"] [data-testid="stPageLink"] > div:first-child,
section[data-testid="stSidebar"] [data-testid="stPageLink"] svg,
section[data-testid="stSidebar"] [data-testid="stPageLink"] span[data-testid="stPageLinkIcon"],
section[data-testid="stSidebar"] [data-testid="stPageLink"] .stPageLinkIcon {
  color: #C9A227 !important;
  fill: #C9A227 !important;
}
section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover > div:first-child,
section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover svg,
section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover span[data-testid="stPageLinkIcon"],
section[data-testid="stSidebar"] [data-testid="stPageLink"]:hover .stPageLinkIcon {
  color: #B8860B !important;
  fill: #B8860B !important;
}
</style>
"""


def show_sidebar() -> None:
    """
    Sidebar com informações do usuário e links para as páginas do PDV.
    Exibe a logo em uploads/logo/ se existir; caso contrário, o título "PDV".
    Ícones do menu em dourado e texto em preto.
    """
    apply_theme()
    user = AuthService.get_current_user()
    role = user["role"] if user else None

    with st.sidebar:
        st.markdown(MENU_GOLD_CSS, unsafe_allow_html=True)
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
        st.page_link("app.py", label="Início", icon=":material/home:")
        st.page_link("pages/0_Caixa.py", label="Caixa", icon=":material/savings:")
        st.page_link("pages/1_Produtos.py", label="Produtos", icon=":material/inventory_2:")
        st.page_link("pages/4_Vendas.py", label="Vendas", icon=":material/receipt_long:")
        st.page_link("pages/7_Acessorios.py", label="Acessórios", icon=":material/diamond:")
        st.page_link("pages/5_Contas_a_Pagar.py", label="Contas a Pagar e a Receber", icon=":material/description:")
        st.page_link("pages/3_Relatorios.py", label="Relatórios", icon=":material/bar_chart:")
        if role == "admin":
            st.page_link("pages/12_Agenda.py", label="Agenda Pessoal", icon=":material/calendar_today:")
        if role == "admin":
            st.page_link("pages/10_Admin.py", label="Administração", icon=":material/settings:")
        st.page_link("pages/11_Sobre.py", label="Sobre", icon=":material/info:")

        st.markdown("---")
        if st.button("Sair", use_container_width=True):
            AuthService.logout()
            if hasattr(st, "switch_page"):
                st.switch_page("app.py")
            else:
                st.rerun()

        