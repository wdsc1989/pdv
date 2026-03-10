import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.product_category import ProductCategory
from services.auth_service import AuthService
from utils.navigation import show_sidebar


st.set_page_config(page_title="Categorias", page_icon="🗂️", layout="wide")

AuthService.require_roles(["admin", "gerente"])
show_sidebar()

db = SessionLocal()

try:
    col_form, col_list = st.columns([1, 2])

    with col_form:
        st.subheader("Cadastro / Edição")

        categorias = (
            db.execute(select(ProductCategory).order_by(ProductCategory.nome))
            .scalars()
            .all()
        )
        opcoes = ["➕ Nova categoria"] + [c.nome for c in categorias]
        escolha = st.selectbox("Categoria", options=opcoes, label_visibility="collapsed")

        categoria_atual = None
        if escolha != "➕ Nova categoria":
            idx = opcoes.index(escolha) - 1
            categoria_atual = categorias[idx]

        nome = st.text_input(
            "Nome da categoria",
            value=categoria_atual.nome if categoria_atual else "",
        )
        descricao = st.text_area(
            "Descrição (opcional)",
            value=categoria_atual.descricao or "" if categoria_atual else "",
        )
        ativo = st.checkbox(
            "Categoria ativa",
            value=categoria_atual.ativo if categoria_atual else True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            salvar = st.button("Salvar", type="primary", use_container_width=True)
        with col_b:
            desativar = st.button(
                "Desativar",
                use_container_width=True,
                disabled=categoria_atual is None or not categoria_atual.ativo,
            )

        if salvar:
            if not nome.strip():
                st.error("Informe um nome para a categoria.")
            else:
                # Verifica se já existe categoria com mesmo nome (diferente da atual)
                existente = (
                    db.query(ProductCategory)
                    .filter(ProductCategory.nome == nome.strip())
                    .first()
                )
                if existente and (not categoria_atual or existente.id != categoria_atual.id):
                    st.error("Já existe uma categoria com esse nome.")
                else:
                    if not categoria_atual:
                        categoria_atual = ProductCategory(
                            nome=nome.strip(),
                            descricao=descricao or None,
                            ativo=ativo,
                        )
                        db.add(categoria_atual)
                    else:
                        categoria_atual.nome = nome.strip()
                        categoria_atual.descricao = descricao or None
                        categoria_atual.ativo = ativo
                    db.commit()
                    st.success("Categoria salva com sucesso.")
                    st.rerun()

        if desativar and categoria_atual:
            categoria_atual.ativo = False
            db.commit()
            st.success("Categoria desativada.")
            st.rerun()

    with col_list:
        st.subheader("Lista de categorias")
        filtro_status = st.selectbox(
            "Status",
            options=["Todas", "Apenas ativas", "Apenas inativas"],
            index=0,
        )

        query = select(ProductCategory).order_by(ProductCategory.nome)
        if filtro_status == "Apenas ativas":
            query = query.filter(ProductCategory.ativo.is_(True))
        elif filtro_status == "Apenas inativas":
            query = query.filter(ProductCategory.ativo.is_(False))

        categorias = db.execute(query).scalars().all()
        if not categorias:
            st.info("Nenhuma categoria cadastrada ainda.")
        else:
            linhas = []
            for c in categorias:
                linhas.append(
                    {
                        "Nome": c.nome,
                        "Descrição": c.descricao or "",
                        "Ativa": "Sim" if c.ativo else "Não",
                    }
                )
            st.dataframe(linhas, use_container_width=True, hide_index=True)

finally:
    db.close()

