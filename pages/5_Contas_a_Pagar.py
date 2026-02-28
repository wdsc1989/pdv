import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.account_payable import AccountPayable
from services.auth_service import AuthService
from utils.formatters import format_currency, format_date
from utils.navigation import show_sidebar


st.set_page_config(page_title="Contas a Pagar", page_icon="📄", layout="wide")

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📄 Contas a Pagar</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Cadastre contas e marque como pagas ao efetuar o pagamento.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    col_form, col_list = st.columns([1, 2])

    with col_form:
        st.subheader("Nova conta")
        st.caption("Preencha e clique em **Salvar conta**.")
        fornecedor = st.text_input("Fornecedor", placeholder="Nome do fornecedor")
        descricao = st.text_input("Descrição (opcional)")
        data_vencimento = st.date_input("Data de vencimento", value=date.today())
        valor = st.number_input(
            "Valor",
            min_value=0.0,
            value=0.0,
            step=1.0,
        )
        observacao = st.text_input("Observação (opcional)")
        if st.button("Salvar conta", type="primary", use_container_width=True):
            if not fornecedor or valor <= 0:
                st.error("Fornecedor e valor > 0 são obrigatórios.")
            else:
                conta = AccountPayable(
                    fornecedor=fornecedor,
                    descricao=descricao or None,
                    data_vencimento=data_vencimento,
                    valor=valor,
                    observacao=observacao or None,
                )
                conta.update_status()
                db.add(conta)
                db.commit()
                st.success("Conta a pagar cadastrada com sucesso.")
                st.rerun()

    with col_list:
        st.subheader("Contas cadastradas")
        contas = db.execute(
            select(AccountPayable).order_by(AccountPayable.data_vencimento)
        ).scalars().all()
        if not contas:
            st.info("Nenhuma conta a pagar cadastrada.")
        else:
            linhas = []
            ids = []
            for c in contas:
                c.update_status()
                ids.append(c.id)
                linhas.append(
                    {
                        "Fornecedor": c.fornecedor,
                        "Descrição": c.descricao or "",
                        "Vencimento": format_date(c.data_vencimento),
                        "Pagamento": format_date(c.data_pagamento)
                        if c.data_pagamento
                        else "-",
                        "Valor": format_currency(c.valor),
                        "Status": c.status,
                    }
                )
            st.dataframe(linhas, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("**Marcar como paga**")
            if ids:
                idx = st.selectbox(
                    "Selecione a conta",
                    options=list(range(len(ids))),
                    format_func=lambda i: f"{contas[i].fornecedor} - "
                    f"{format_currency(contas[i].valor)} "
                    f"(venc. {format_date(contas[i].data_vencimento)})",
                )
                if st.button(
                    "Marcar selecionada como paga", use_container_width=True
                ):
                    conta = contas[idx]
                    conta.data_pagamento = date.today()
                    conta.update_status()
                    db.commit()
                    st.success("Conta marcada como paga.")
                    st.rerun()

finally:
    db.close()

