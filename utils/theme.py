"""
Aplicação do tema visual do app (padrão Streamlit ou identidade visual da empresa).
Cores: #FEEEF0 (rosa claro), gradiente dourado, #000000 (preto).
Fontes: Alex Brush (marca), Montserrat (interface).
"""
import streamlit as st

from utils.login_config import load_login_config

# Identidade visual: rosa claro, dourado, preto + Alex Brush & Montserrat
IDENTIDADE_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Alex+Brush&family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --vc-rosa: #FEEEF0;
  --vc-dourado-escuro: #B8860B;
  --vc-dourado: #C9A227;
  --vc-preto: #000000;
  --vc-preto-suave: #27333B;
}
/* Aplica em todo o app quando tema = identidade_visual */
[data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, var(--vc-rosa) 0%, #fff 40%) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
/* Sidebar */
section[data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, var(--vc-rosa) 0%, #fff 100%) !important;
}
/* Títulos e textos principais */
h1, h2, h3, .stMarkdown p, [data-testid="stMarkdownContainer"] p {
  font-family: 'Montserrat', sans-serif !important;
  color: var(--vc-preto) !important;
}
/* Botões: fundo claro e texto escuro para boa leitura */
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  background: var(--vc-dourado) !important;
  color: var(--vc-preto) !important;
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 600 !important;
  border: 1px solid var(--vc-dourado-escuro) !important;
  border-radius: 8px !important;
}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="baseButton-primary"]:hover {
  background: var(--vc-dourado-escuro) !important;
  color: #fff !important;
  border-color: var(--vc-preto-suave) !important;
}
/* Botões secundários: contorno visível e texto legível */
.stButton > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {
  color: var(--vc-preto-suave) !important;
  background: #fff !important;
  border: 1px solid var(--vc-dourado-escuro) !important;
}
.stButton > button:not([kind="primary"]):hover {
  background: var(--vc-rosa) !important;
  color: var(--vc-preto) !important;
}
/* Inputs */
.stTextInput input, .stTextInput label {
  font-family: 'Montserrat', sans-serif !important;
}
/* Bloco "Entrar no sistema" na tela de login: sem retângulo/cor, centralizado e menor */
.vc-login-intro,
.vc-login-intro *,
[data-testid="stVerticalBlock"]:has(.vc-login-intro) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
.vc-login-intro {
  border-radius: 0 !important;
  padding: 0.5rem 0 !important;
  text-align: center !important;
  max-width: 320px !important;
  margin-left: auto !important;
  margin-right: auto !important;
}
.vc-login-title {
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 600 !important;
  font-size: 1rem !important;
  color: var(--vc-preto) !important;
  margin-bottom: 0.2rem !important;
  text-align: center !important;
}
.vc-login-intro .vc-login-subtitle {
  font-family: 'Montserrat', sans-serif !important;
  font-size: 0.8rem !important;
  color: #555 !important;
  text-align: center !important;
  margin: 0 !important;
}
/* Bloco da logo centralizado (na coluna central) */
.vc-brand-wrap {
  text-align: center !important;
  width: 100% !important;
  max-width: 100% !important;
  margin-left: auto !important;
  margin-right: auto !important;
  margin-bottom: 0.5rem !important;
}
.vc-brand-wrap .vc-brand-title,
.vc-brand-wrap .vc-brand-sub,
.vc-brand-wrap .vc-login-subtitle { display: block !important; }
.vc-brand-wrap-center .vc-brand-title,
.vc-brand-wrap-center .vc-brand-sub,
.vc-brand-wrap-center .vc-login-subtitle { text-align: center !important; }
.vc-brand-wrap-left .vc-brand-title,
.vc-brand-wrap-left .vc-brand-sub,
.vc-brand-wrap-left .vc-login-subtitle { text-align: left !important; }
.vc-brand-wrap-right .vc-brand-title,
.vc-brand-wrap-right .vc-brand-sub,
.vc-brand-wrap-right .vc-login-subtitle { text-align: right !important; }
.vc-brand-title {
  font-family: 'Alex Brush', cursive !important;
  font-size: 2.5rem !important;
  color: var(--vc-dourado) !important;
  margin: 0 !important;
}
.vc-brand-sub {
  font-family: 'Montserrat', sans-serif !important;
  font-size: 0.75rem !important;
  letter-spacing: 0.15em !important;
  color: var(--vc-dourado-escuro) !important;
  margin-top: -0.5rem !important;
}
/* Imagem da logo na tela de login: tratada como imagem em um único bloco; alinhamento por classe */
.vc-login-img { display: block !important; max-width: 100% !important; height: auto !important; }
.vc-brand-wrap-center .vc-login-img { margin-left: auto !important; margin-right: auto !important; }
.vc-brand-wrap-left .vc-login-img { margin-left: 0 !important; margin-right: auto !important; }
.vc-brand-wrap-right .vc-login-img { margin-left: auto !important; margin-right: 0 !important; }
.vc-login-logo-wrap { text-align: center !important; width: 100% !important; }
.vc-login-logo-wrap img { margin-left: auto !important; margin-right: auto !important; display: block !important; }
</style>
"""

# Centralização vertical da tela de login (só injetar quando estiver na login page)
# Não usar align-items: center para não encolher o bloco; esquerda/centro/direita vêm das colunas do Streamlit.
LOGIN_VERTICAL_CENTER_CSS = """
<style>
/* Centraliza verticalmente o conteúdo da tela de login; largura total para as colunas (esq/centro/dir) */
[data-testid="stAppViewContainer"] > div {
  min-height: 100vh !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
}
[data-testid="stAppViewContainer"] > div > section {
  flex: 0 1 auto !important;
  width: 100% !important;
  max-width: 100% !important;
}
/* Largura total na tela de login para esquerda/centro/direita funcionarem (colunas ocupam a viewport) */
[data-testid="stAppViewContainer"] .block-container {
  max-width: 100% !important;
  padding-left: 2rem !important;
  padding-right: 2rem !important;
}
/* Remove retângulo/cor do formulário de login */
[data-testid="stForm"],
[data-testid="stForm"] > div,
section:has([data-testid="stForm"]) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
</style>
"""


def get_theme() -> str:
    """Retorna o tema atual: 'default' ou 'identidade_visual'."""
    lc = load_login_config()
    return (lc.get("theme_visual") or "default").strip().lower()


def apply_theme() -> None:
    """Injeta CSS da identidade visual quando o tema estiver ativo (em todas as telas)."""
    if get_theme() != "identidade_visual":
        return
    st.markdown(IDENTIDADE_CSS, unsafe_allow_html=True)


def apply_login_vertical_center() -> None:
    """Injeta CSS para centralizar verticalmente o conteúdo da tela de login. Chamar só em login_page()."""
    if get_theme() != "identidade_visual":
        return
    st.markdown(LOGIN_VERTICAL_CENTER_CSS, unsafe_allow_html=True)
