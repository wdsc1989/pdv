import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import func

from config.database import SessionLocal
from models.cash_session import CashSession
from models.sale import Sale
from services.auth_service import AuthService
from utils.formatters import format_currency, format_date
from utils.navigation import show_sidebar
from utils.ui_helpers import success_box, warning_box


st.set_page_config(page_title="Caixa", page_icon="💰", layout="wide")

AuthService.require_auth()
show_sidebar()

user = AuthService.get_current_user()
role = user["role"] if user else None

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>💰 Caixa</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Abra o caixa no início do dia e feche ao encerrar. Vendas vinculadas à sessão.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    sessao_aberta = (
        db.query(CashSession).filter(CashSession.status == "aberta").first()
    )

    # Status em destaque no topo
    if sessao_aberta:
        total_sessao = (
            db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .scalar()
        )
        success_box(
            f"Caixa aberto desde {format_date(sessao_aberta.data_abertura)} — "
            f"Troco inicial: {format_currency(sessao_aberta.valor_abertura)} — "
            f"Vendas nesta sessão: {format_currency(total_sessao)}"
        )
    else:
        warning_box("Nenhum caixa aberto no momento. Abra o caixa para permitir vendas.")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. Abrir caixa")
        st.caption("Defina o valor de troco inicial (ex.: dinheiro na gaveta).")
        if role in ("admin", "gerente"):
            if sessao_aberta:
                st.info(
                    f"Já existe uma sessão aberta desde "
                    f"{format_date(sessao_aberta.data_abertura)} "
                    f"com valor de abertura {format_currency(sessao_aberta.valor_abertura)}."
                )
            else:
                with st.form("abrir_caixa"):
                    valor_abertura = st.number_input(
                        "Valor de abertura (troco inicial)",
                        min_value=0.0,
                        value=0.0,
                        step=1.0,
                    )
                    observacao = st.text_input(
                        "Observação (opcional)", placeholder="Ex: Início do dia"
                    )
                    abrir = st.form_submit_button("Abrir caixa", type="primary")
                if abrir:
                    nova = CashSession(
                        valor_abertura=valor_abertura,
                        observacao=observacao or None,
                        status="aberta",
                    )
                    db.add(nova)
                    db.commit()
                    st.success("Caixa aberto com sucesso.")
                    st.rerun()
        else:
            st.info("Abertura de caixa disponível apenas para gerente/admin.")

    with col2:
        st.subheader("2. Fechar caixa")
        st.caption("Ao encerrar o expediente, informe o valor contado no caixa e feche a sessão.")
        if role in ("admin", "gerente"):
            if not sessao_aberta:
                st.info("Não há caixa aberto no momento.")
            else:
                total_sessao = (
                    db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
                    .filter(Sale.cash_session_id == sessao_aberta.id)
                    .filter(Sale.status != "cancelada")
                    .scalar()
                )
                st.markdown(f"**Aberta em:** {format_date(sessao_aberta.data_abertura)}")
                st.markdown(f"**Total de vendas na sessão:** {format_currency(total_sessao)}")

                with st.form("fechar_caixa"):
                    valor_fechamento = st.number_input(
                        "Valor no fechamento (contagem do caixa)",
                        min_value=0.0,
                        value=float(total_sessao),
                        step=1.0,
                    )
                    fechar = st.form_submit_button("Fechar caixa", type="primary")
                if fechar:
                    sessao_aberta.valor_fechamento = valor_fechamento
                    sessao_aberta.status = "fechada"
                    from datetime import datetime

                    sessao_aberta.data_fechamento = datetime.utcnow()
                    db.commit()
                    st.success("Caixa fechado com sucesso.")
                    st.rerun()
        else:
            st.info("Fechamento de caixa disponível apenas para gerente/admin.")

    st.markdown("---")
    with st.expander("📋 Ver histórico de sessões de caixa"):
        sessoes = db.query(CashSession).order_by(CashSession.id.desc()).limit(50).all()
        if not sessoes:
            st.info("Nenhuma sessão de caixa registrada ainda.")
        else:
            linhas = []
            for s in sessoes:
                total_vendas = (
                    db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
                    .filter(Sale.cash_session_id == s.id)
                    .filter(Sale.status != "cancelada")
                    .scalar()
                )
                linhas.append(
                    {
                        "ID": s.id,
                        "Abertura": format_date(s.data_abertura),
                        "Fechamento": format_date(s.data_fechamento) if s.data_fechamento else "-",
                        "Valor abertura": format_currency(s.valor_abertura),
                        "Valor fechamento": format_currency(s.valor_fechamento) if s.valor_fechamento is not None else "-",
                        "Status": s.status,
                        "Total vendas": format_currency(total_vendas),
                        "Obs.": s.observacao or "",
                    }
                )
            st.dataframe(linhas, use_container_width=True, hide_index=True)
finally:
    db.close()

