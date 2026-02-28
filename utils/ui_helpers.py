"""
Helpers para deixar as telas mais intuitivas e consistentes.
"""
import streamlit as st


def page_header(title: str, icon: str, subtitle: str = ""):
    """Título da página com possível subtítulo."""
    st.markdown(f"# {icon} {title}")
    if subtitle:
        st.caption(subtitle)
    st.markdown("---")


def info_box(message: str, icon: str = "ℹ️"):
    """Caixa de informação destacada."""
    st.markdown(
        f"""
    <div style="
        background-color: #e8f4fd;
        border-left: 4px solid #1e88e5;
        padding: 12px 16px;
        margin: 12px 0;
        border-radius: 0 8px 8px 0;
    ">
        <strong>{icon}</strong> {message}
    </div>
    """,
        unsafe_allow_html=True,
    )


def success_box(message: str):
    """Caixa de status positivo (ex.: caixa aberto)."""
    st.markdown(
        f"""
    <div style="
        background-color: #e8f5e9;
        border-left: 4px solid #43a047;
        padding: 14px 18px;
        margin: 12px 0;
        border-radius: 0 8px 8px 0;
        font-weight: 500;
    ">
        ✅ {message}
    </div>
    """,
        unsafe_allow_html=True,
    )


def warning_box(message: str):
    """Caixa de atenção (ex.: caixa fechado)."""
    st.markdown(
        f"""
    <div style="
        background-color: #fff3e0;
        border-left: 4px solid #fb8c00;
        padding: 14px 18px;
        margin: 12px 0;
        border-radius: 0 8px 8px 0;
        font-weight: 500;
    ">
        ⚠️ {message}
    </div>
    """,
        unsafe_allow_html=True,
    )


def step_label(step: int, label: str):
    """Rótulo de passo (ex.: 'Passo 1: Adicionar itens')."""
    st.markdown(f"**Passo {step}:** {label}")
