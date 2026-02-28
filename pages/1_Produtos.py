import os
import sys
from pathlib import Path
from datetime import date

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import SessionLocal
from models.product import Product
from models.product_category import ProductCategory
from models.stock_entry import StockEntry
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar


st.set_page_config(page_title="Produtos", page_icon="📦", layout="wide")

AuthService.require_auth()
show_sidebar()
user = AuthService.get_current_user()
role = user["role"] if user else None

st.markdown(
    "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>📦 Produtos</strong></p>"
    "<p style='margin:0; font-size:0.8rem; color:#666;'>Busque, cadastre e edite produtos. Registre entradas de estoque para acompanhamento por período.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

db = SessionLocal()

try:
    can_edit = role in ("admin", "gerente")
    if not can_edit:
        st.info(
            "Somente **gerente** ou **admin** podem cadastrar ou editar produtos. "
            "Você pode visualizar a lista e buscar."
        )

    # Ordem: Cadastrar ou editar, Categorias, Lista de produtos, Estoque (último)
    tab_labels = ["Cadastrar ou editar"]
    if can_edit:
        tab_labels.append("Categorias")
    tab_labels.append("Lista de produtos")
    tab_labels.append("Estoque")

    tabs = st.tabs(tab_labels)
    tab_cadastro = tabs[0]
    tab_categorias = tabs[1] if can_edit else None
    tab_lista = tabs[2] if can_edit else tabs[1]
    tab_estoque = tabs[3] if can_edit else tabs[2]

    # Produto selecionado para edição (vindo da lista ou do grid)
    edit_product_id = st.session_state.pop("edit_product_id", None)
    if "selected_product_id" not in st.session_state:
        st.session_state.selected_product_id = None
    if edit_product_id is not None:
        st.session_state.selected_product_id = edit_product_id

    with tab_cadastro:
        st.subheader("Selecionar produto")
        st.caption("Busque por nome, código, categoria ou marca. Clique em **Editar** no card para abrir o formulário abaixo.")

        produtos = db.execute(select(Product).order_by(Product.nome)).scalars().all()
        col_busca, col_novo = st.columns([3, 1])
        with col_busca:
            busca_cadastro = st.text_input(
                "Buscar produto",
                placeholder="Ex: P0001, camiseta, jeans, infantil...",
                key="busca_cadastro",
            ).strip().lower()
        with col_novo:
            st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)  # alinha com o input
            if st.button("➕ Novo produto", type="primary", use_container_width=True):
                st.session_state.selected_product_id = None
                st.rerun()

        termo = busca_cadastro
        if termo:
            produtos_filtrados = [
                p
                for p in produtos
                if termo in (p.codigo or "").lower()
                or termo in (p.nome or "").lower()
                or termo in (p.categoria or "").lower()
                or termo in (p.marca or "").lower()
            ]
        else:
            produtos_filtrados = list(produtos)

        # Grid de cards (estilo página de vendas)
        if not produtos_filtrados:
            st.info("Nenhum produto encontrado. Use outro termo de busca ou clique em **Novo produto**.")
        else:
            PAGE_SIZE = 6
            total = len(produtos_filtrados)
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            if "cadastro_prod_page" not in st.session_state:
                st.session_state.cadastro_prod_page = 0
            page = max(0, min(st.session_state.cadastro_prod_page, total_pages - 1))
            st.session_state.cadastro_prod_page = page

            if total_pages > 1:
                c_prev, c_info, c_next = st.columns([1, 2, 1])
                with c_prev:
                    if st.button("◀ Anterior", key="cadastro_prev", disabled=page == 0):
                        st.session_state.cadastro_prod_page = max(0, page - 1)
                        st.rerun()
                with c_info:
                    st.caption(f"Página {page + 1} de {total_pages} — {total} produto(s)")
                with c_next:
                    if st.button("Próximo ▶", key="cadastro_next", disabled=page >= total_pages - 1):
                        st.session_state.cadastro_prod_page = min(total_pages - 1, page + 1)
                        st.rerun()

            start = page * PAGE_SIZE
            subset = produtos_filtrados[start : start + PAGE_SIZE]
            uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
            cols = st.columns(2)
            for idx, p in enumerate(subset):
                with cols[idx % 2]:
                    selected = st.session_state.selected_product_id == p.id
                    if selected:
                        st.caption("✓ Selecionado para edição")
                    container = st.container()
                    with container:
                        img_path = None
                        if p.imagem_path:
                            candidate = uploads_dir / p.imagem_path
                            if candidate.exists():
                                img_path = candidate
                        if img_path:
                            st.image(str(img_path), width=100)
                        else:
                            st.markdown(
                                "<div style='width:100px;height:70px;background:#eee;border-radius:4px;"
                                "display:flex;align-items:center;justify-content:center;font-size:10px;color:#999;'>"
                                "Sem imagem</div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown(f"**{p.codigo}**")
                        st.caption((p.nome or "")[:40] + ("..." if (p.nome or "") and len(p.nome or "") > 40 else ""))
                        st.caption(f"Venda: {format_currency(p.preco_venda)} | Estoque: {int(p.estoque_atual or 0)}")
                        if st.button("Editar", key=f"edit_cadastro_{p.id}", use_container_width=True):
                            st.session_state.selected_product_id = p.id
                            st.rerun()

        produto_atual = None
        if st.session_state.selected_product_id:
            produto_atual = db.get(Product, st.session_state.selected_product_id)

        st.markdown("---")
        st.subheader("Dados do produto" if produto_atual else "Novo produto")
        if produto_atual:
            st.caption(f"Editando: **{produto_atual.codigo}** — {produto_atual.nome}")
        else:
            st.caption("Preencha os campos abaixo para cadastrar um novo produto.")

        categorias = (
            db.execute(
                select(ProductCategory)
                .where(ProductCategory.ativo.is_(True))
                .order_by(ProductCategory.nome)
            )
            .scalars()
            .all()
        )

        with st.expander("Dados básicos", expanded=True):
            codigo = st.text_input(
                "Código (deixe em branco para gerar automaticamente)",
                value=produto_atual.codigo if produto_atual else "",
                disabled=not can_edit,
            )
            nome = st.text_input(
                "Nome",
                value=produto_atual.nome if produto_atual else "",
                disabled=not can_edit,
            )

            cat_opcoes = ["(Sem categoria)"] + [c.nome for c in categorias]
            default_cat = "(Sem categoria)"
            if produto_atual and produto_atual.categoria_id:
                atual = next(
                    (c.nome for c in categorias if c.id == produto_atual.categoria_id),
                    None,
                )
                if atual:
                    default_cat = atual

            categoria_nome = st.selectbox(
                "Categoria",
                options=cat_opcoes,
                index=cat_opcoes.index(default_cat) if default_cat in cat_opcoes else 0,
                disabled=not can_edit,
            )

            marca = st.text_input(
                "Marca",
                value=produto_atual.marca or "" if produto_atual else "",
                disabled=not can_edit,
            )

            ativo = st.checkbox(
                "Produto ativo",
                value=produto_atual.ativo if produto_atual else True,
                disabled=not can_edit,
            )
        with st.expander("Preços e estoque", expanded=True):
            preco_custo = st.number_input(
                "Preço de custo",
                min_value=0.0,
                value=max(0.0, float(produto_atual.preco_custo)) if produto_atual else 0.0,
                step=1.0,
                disabled=not can_edit,
            )
            preco_venda = st.number_input(
                "Preço de venda",
                min_value=0.0,
                value=max(0.0, float(produto_atual.preco_venda)) if produto_atual else 0.0,
                step=1.0,
                disabled=not can_edit,
            )

            estoque_val = 0.0
            if produto_atual and produto_atual.estoque_atual is not None:
                try:
                    estoque_val = max(0.0, float(produto_atual.estoque_atual))
                except Exception:
                    estoque_val = 0.0

            if produto_atual:
                st.metric("Estoque atual", f"{estoque_val:.0f}" if estoque_val == int(estoque_val) else f"{estoque_val:.2f}")
                estoque_inicial = estoque_val
                if can_edit:
                    st.caption("Para alterar o estoque, use **Dar entrada em estoque** abaixo. O valor acima é apenas informativo.")
                    st.markdown("---")
                    entrada_qtd = st.number_input(
                        "Quantidade a dar entrada",
                        min_value=0.0,
                        value=0.0,
                        step=1.0,
                        key="entrada_qtd",
                        help="Quantidade que está entrando no estoque (compra/reposição).",
                    )
                    entrada_obs = st.text_input(
                        "Observação (opcional)",
                        placeholder="Ex: Compra fornecedor X, lote 123",
                        key="entrada_obs",
                    )
                    if st.button("Registrar entrada de estoque", type="secondary", key="btn_entrada") and entrada_qtd > 0:
                        entry = StockEntry(
                            product_id=produto_atual.id,
                            quantity=entrada_qtd,
                            data_entrada=date.today(),
                            observacao=entrada_obs.strip() or None,
                        )
                        db.add(entry)
                        produto_atual.estoque_atual = (produto_atual.estoque_atual or 0) + entrada_qtd
                        db.commit()
                        st.success(f"Entrada de {entrada_qtd:.0f} un. registrada. Estoque atual: {produto_atual.estoque_atual:.0f}.")
                        st.rerun()
            else:
                estoque_inicial = st.number_input(
                    "Estoque inicial",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    disabled=not can_edit,
                    help="Quantidade em estoque ao cadastrar o produto.",
                )

            estoque_min_val = 0.0
            if produto_atual and produto_atual.estoque_minimo is not None:
                try:
                    estoque_min_val = max(0.0, float(produto_atual.estoque_minimo))
                except Exception:
                    estoque_min_val = 0.0

            estoque_minimo = st.number_input(
                "Estoque mínimo (alerta)",
                min_value=0.0,
                value=estoque_min_val,
                step=1.0,
                disabled=not can_edit,
            )
            margem = 0.0
            if preco_custo > 0:
                margem = ((preco_venda - preco_custo) / preco_custo) * 100
            st.metric("Margem de lucro (%)", f"{margem:.2f}%")

        with st.expander("Imagem do produto (opcional)"):
            imagem = st.file_uploader(
                "Enviar imagem",
                type=["png", "jpg", "jpeg", "webp"],
                disabled=not can_edit,
            )
            if produto_atual and produto_atual.imagem_path:
                uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
                img_path = uploads_dir / produto_atual.imagem_path
                if img_path.exists():
                    st.image(str(img_path), caption="Imagem atual", use_column_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            salvar = st.button(
                "Salvar",
                type="primary",
                use_container_width=True,
                disabled=not can_edit,
            )
        with col_b:
            excluir = st.button(
                "Excluir",
                type="secondary",
                use_container_width=True,
                disabled=(not can_edit) or (produto_atual is None),
            )

        if salvar and can_edit:
            if not nome:
                st.error("Preencha **Nome**.")
            else:
                # Resolve categoria selecionada
                categoria_obj = None
                if categoria_nome != "(Sem categoria)":
                    categoria_obj = next(
                        (c for c in categorias if c.nome == categoria_nome), None
                    )

                # Geração automática de código se novo produto e campo em branco
                if not produto_atual and not codigo:
                    # Busca maior código no formato PNNNN
                    todos_codigos = [
                        p.codigo
                        for p in db.execute(select(Product.codigo)).scalars().all()
                        if p
                    ]
                    nums = []
                    for c in todos_codigos:
                        if c.startswith("P") and c[1:].isdigit():
                            nums.append(int(c[1:]))
                    prox = (max(nums) + 1) if nums else 1
                    codigo = f"P{prox:04d}"

                if not codigo:
                    st.error("Código não pode ficar vazio.")
                else:
                    if not produto_atual:
                        existe_codigo = (
                            db.query(Product).filter(Product.codigo == codigo).first()
                        )
                        if existe_codigo:
                            st.error("Já existe um produto com este código.")
                        else:
                            produto_atual = Product(
                                codigo=codigo,
                                nome=nome,
                                categoria=categoria_obj.nome
                                if categoria_obj
                                else None,
                                marca=marca or None,
                                preco_custo=preco_custo,
                                preco_venda=preco_venda,
                                estoque_atual=estoque_inicial,
                                estoque_minimo=estoque_minimo or None,
                                ativo=ativo,
                                categoria_id=categoria_obj.id if categoria_obj else None,
                            )
                            db.add(produto_atual)
                    else:
                        produto_atual.codigo = codigo
                        produto_atual.nome = nome
                        produto_atual.categoria = (
                            categoria_obj.nome if categoria_obj else None
                        )
                        produto_atual.marca = marca or None
                        produto_atual.preco_custo = preco_custo
                        produto_atual.preco_venda = preco_venda
                        produto_atual.estoque_atual = estoque_inicial
                        produto_atual.estoque_minimo = estoque_minimo or None
                        produto_atual.ativo = ativo
                        produto_atual.categoria_id = (
                            categoria_obj.id if categoria_obj else None
                        )

                db.commit()
                db.refresh(produto_atual)

                # Salva imagem se enviada
                if imagem is not None and produto_atual is not None:
                    uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
                    products_dir = uploads_dir / "products"
                    products_dir.mkdir(parents=True, exist_ok=True)

                    ext = os.path.splitext(imagem.name)[1].lower()
                    filename = f"{produto_atual.id}{ext}"
                    rel_path = Path("products") / filename
                    full_path = products_dir / filename
                    with open(full_path, "wb") as f:
                        f.write(imagem.getbuffer())
                    produto_atual.imagem_path = str(rel_path).replace("\\", "/")
                    db.commit()

                st.success("Produto salvo com sucesso.")
                st.rerun()

        if excluir and can_edit and produto_atual:
            db.delete(produto_atual)
            db.commit()
            st.success("Produto excluído.")
            st.rerun()

    with tab_estoque:
        st.subheader("Estoque")
        st.caption("Quantidades em estoque. Abaixo do mínimo em destaque.")

        categorias_est = (
            db.execute(
                select(ProductCategory)
                .where(ProductCategory.ativo.is_(True))
                .order_by(ProductCategory.nome)
            )
            .scalars().all()
        )
        cat_opcoes_est = ["Todas as categorias"] + [c.nome for c in categorias_est]

        col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
        with col_f1:
            busca_estoque = st.text_input(
                "Buscar produto (nome ou código)",
                placeholder="Ex: vestido, VEST001, jeans...",
                key="busca_estoque",
            ).strip().lower()
        with col_f2:
            cat_est = st.selectbox("Categoria", options=cat_opcoes_est, key="cat_estoque")
        with col_f3:
            status_est = st.selectbox(
                "Status",
                options=["Apenas ativos", "Todos", "Apenas inativos"],
                index=0,
                key="status_estoque",
            )

        query_est = select(Product).order_by(Product.nome)
        if status_est == "Apenas ativos":
            query_est = query_est.filter(Product.ativo.is_(True))
        elif status_est == "Apenas inativos":
            query_est = query_est.filter(Product.ativo.is_(False))

        produtos_est = db.execute(query_est).scalars().all()
        if cat_est != "Todas as categorias":
            cat_obj_est = next((c for c in categorias_est if c.nome == cat_est), None)
            if cat_obj_est:
                produtos_est = [p for p in produtos_est if p.categoria_id == cat_obj_est.id]
        if busca_estoque:
            produtos_est = [
                p
                for p in produtos_est
                if busca_estoque in (p.nome or "").lower()
                or busca_estoque in (p.codigo or "").lower()
            ]

        if not produtos_est:
            st.info("Nenhum produto encontrado com os filtros atuais.")
        else:
            linhas_est = []
            baixo_est = []
            valor_estoque_custo = 0.0
            valor_estoque_venda = 0.0
            valor_lucro_total = 0.0
            for p in produtos_est:
                estoque = float(p.estoque_atual or 0)
                estoque_min = float(p.estoque_minimo or 0)
                custo = p.preco_custo or 0
                venda = p.preco_venda or 0
                lucro_un = venda - custo
                lucro_estoque = lucro_un * estoque
                valor_estoque_custo += custo * estoque
                valor_estoque_venda += venda * estoque
                valor_lucro_total += lucro_estoque
                linha_est = {
                    "Código": p.codigo,
                    "Nome": p.nome,
                    "Categoria": p.categoria or "",
                    "Marca": p.marca or "",
                    "Estoque": estoque,
                    "Estoque mín.": estoque_min,
                    "Preço venda": format_currency(venda),
                    "Lucro un.": format_currency(lucro_un),
                    "Lucro (estoque)": format_currency(lucro_estoque),
                }
                linhas_est.append(linha_est)
                if p.estoque_minimo is not None and p.estoque_atual <= p.estoque_minimo:
                    baixo_est.append(linha_est)

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total de produtos", len(produtos_est))
            with col2:
                st.metric("Em alerta (estoque baixo)", len(baixo_est))
            with col3:
                st.metric("Valor estoque (custo)", format_currency(valor_estoque_custo))
            with col4:
                st.metric("Valor estoque (venda)", format_currency(valor_estoque_venda))
            with col5:
                st.metric("Lucro (estoque)", format_currency(valor_lucro_total))

            if baixo_est:
                st.markdown("---")
                st.subheader("Produtos com estoque baixo")
                st.caption("Quantidade igual ou abaixo do mínimo definido.")
                st.dataframe(baixo_est, use_container_width=True, hide_index=True)
                st.markdown("---")

            st.subheader("Todos os produtos")
            st.dataframe(linhas_est, use_container_width=True, hide_index=True)

    with tab_lista:
        st.subheader("Lista de produtos")
        st.caption("Busque por código ou nome, filtre por categoria e status. Selecione um produto e clique em **Editar** para abrir na aba de cadastro.")

        categorias_lista = (
            db.execute(
                select(ProductCategory).order_by(ProductCategory.nome)
            )
            .scalars().all()
        )
        cat_opcoes_lista = ["Todas as categorias"] + [c.nome for c in categorias_lista]

        col_busca, col_cat, col_status = st.columns([2, 1, 1])
        with col_busca:
            busca = st.text_input(
                "Buscar (código ou nome)",
                placeholder="Ex: P0001, camiseta, jeans...",
                key="busca_produtos",
            ).strip().lower()
        with col_cat:
            cat_lista = st.selectbox("Categoria", options=cat_opcoes_lista, key="cat_lista")
        with col_status:
            filtro_status = st.selectbox(
                "Status",
                options=["Todos", "Apenas ativos", "Apenas inativos"],
                index=0,
                key="filtro_status_lista",
            )

        query = select(Product).order_by(Product.nome)
        if filtro_status == "Apenas ativos":
            query = query.filter(Product.ativo.is_(True))
        elif filtro_status == "Apenas inativos":
            query = query.filter(Product.ativo.is_(False))

        produtos_lista = db.execute(query).scalars().all()

        if cat_lista != "Todas as categorias":
            cat_obj = next((c for c in categorias_lista if c.nome == cat_lista), None)
            if cat_obj:
                produtos_lista = [p for p in produtos_lista if p.categoria_id == cat_obj.id]

        if busca:
            produtos_lista = [
                p
                for p in produtos_lista
                if busca in (p.codigo or "").lower() or busca in (p.nome or "").lower()
            ]

        if not produtos_lista:
            st.info("Nenhum produto encontrado com os filtros informados.")
        else:
            linhas = []
            uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
            for p in produtos_lista:
                margem = 0.0
                if p.preco_custo > 0:
                    margem = ((p.preco_venda - p.preco_custo) / p.preco_custo) * 100
                img_url = ""
                if p.imagem_path:
                    img_path = uploads_dir / p.imagem_path
                    if img_path.exists():
                        img_url = str(p.imagem_path)
                estoque = float(p.estoque_atual or 0)
                valor_custo = (p.preco_custo or 0) * estoque
                linhas.append(
                    {
                        "Código": p.codigo,
                        "Nome": p.nome,
                        "Categoria": p.categoria or "",
                        "Marca": p.marca or "",
                        "Preço custo": format_currency(p.preco_custo),
                        "Preço venda": format_currency(p.preco_venda),
                        "Valor de custo": format_currency(valor_custo),
                        "Margem (%)": f"{margem:.2f}",
                        "Estoque": estoque,
                        "Estoque mín.": float(p.estoque_minimo or 0),
                        "Status": "Ativo" if p.ativo else "Inativo",
                        "Imagem": img_url,
                    }
                )
            st.dataframe(linhas, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Editar produto")
            opcoes_editar = [f"{p.codigo} — {p.nome}" for p in produtos_lista]
            ids_editar = [p.id for p in produtos_lista]
            escolha_editar = st.selectbox(
                "Selecione o produto que deseja editar",
                options=opcoes_editar,
                index=0,
                key="escolha_editar",
            )
            if st.button("Abrir para edição", type="primary", key="btn_editar"):
                idx_ed = opcoes_editar.index(escolha_editar)
                st.session_state.edit_product_id = ids_editar[idx_ed]
                st.rerun()

    # Aba de categorias (apenas para admin/gerente)
    if tab_categorias is not None:
        with tab_categorias:
            st.subheader("Categorias cadastradas")
            st.caption("Busque por nome ou descrição. Selecione uma categoria e clique em **Abrir para edição** ou use **Nova categoria** para cadastrar.")

            # Busca e filtro (layout igual às outras abas)
            col_busca_cat, col_status_cat = st.columns([2, 1])
            with col_busca_cat:
                busca_cat = st.text_input(
                    "Buscar categoria (nome ou descrição)",
                    placeholder="Ex: infantil, masculino...",
                    key="busca_categoria",
                ).strip().lower()
            with col_status_cat:
                filtro_status_cat = st.selectbox(
                    "Status",
                    options=["Todas", "Apenas ativas", "Apenas inativas"],
                    index=0,
                    key="filtro_status_cat",
                )

            query_cat = select(ProductCategory).order_by(ProductCategory.nome)
            if filtro_status_cat == "Apenas ativas":
                query_cat = query_cat.filter(ProductCategory.ativo.is_(True))
            elif filtro_status_cat == "Apenas inativas":
                query_cat = query_cat.filter(ProductCategory.ativo.is_(False))

            categorias_all = db.execute(query_cat).scalars().all()
            if busca_cat:
                categorias_list = [
                    c
                    for c in categorias_all
                    if busca_cat in (c.nome or "").lower()
                    or busca_cat in (c.descricao or "").lower()
                ]
            else:
                categorias_list = list(categorias_all)

            if not categorias_list:
                st.info("Nenhuma categoria encontrada. Use outro filtro ou clique em **Nova categoria** abaixo para cadastrar.")
            else:
                linhas_cat = []
                for c in categorias_list:
                    linhas_cat.append(
                        {
                            "ID": c.id,
                            "Nome": c.nome,
                            "Descrição": (c.descricao or "")[:60] + ("..." if (c.descricao or "") and len(c.descricao or "") > 60 else ""),
                            "Ativa": "Sim" if c.ativo else "Não",
                        }
                    )
                st.dataframe(linhas_cat, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.caption("Selecione uma categoria da lista acima para editar ou desativar.")
                opcoes_cat_editar = [f"{c.nome}" for c in categorias_list]
                ids_cat_editar = [c.id for c in categorias_list]
                escolha_cat_editar = st.selectbox(
                    "Categoria para editar",
                    options=opcoes_cat_editar,
                    index=0,
                    key="escolha_cat_editar",
                )
                if st.button("Abrir para edição", type="primary", key="btn_abrir_cat"):
                    idx_ed = opcoes_cat_editar.index(escolha_cat_editar)
                    st.session_state.edit_categoria_id = ids_cat_editar[idx_ed]
                    st.rerun()

            st.markdown("---")
            st.subheader("Cadastrar ou editar categoria")

            edit_categoria_id = st.session_state.get("edit_categoria_id")
            categoria_atual = None
            if edit_categoria_id:
                categoria_atual = db.get(ProductCategory, edit_categoria_id)
                if not categoria_atual:
                    st.session_state.pop("edit_categoria_id", None)

            col_novo, col_esp = st.columns([1, 3])
            with col_novo:
                if st.button("➕ Nova categoria", key="btn_nova_cat"):
                    st.session_state.pop("edit_categoria_id", None)
                    st.rerun()
            if categoria_atual:
                st.caption(f"Editando: **{categoria_atual.nome}**")

            nome_cat = st.text_input(
                "Nome da categoria",
                value=categoria_atual.nome if categoria_atual else "",
                key="nome_cat_input",
            )
            descricao_cat = st.text_area(
                "Descrição (opcional)",
                value=categoria_atual.descricao or "" if categoria_atual else "",
                key="descricao_cat_input",
            )
            ativo_cat = st.checkbox(
                "Categoria ativa",
                value=categoria_atual.ativo if categoria_atual else True,
                key="ativo_cat_check",
            )

            col_ca, col_cb = st.columns(2)
            with col_ca:
                salvar_cat = st.button(
                    "Salvar categoria", type="primary", use_container_width=True, key="salvar_cat_btn"
                )
            with col_cb:
                desativar_cat = st.button(
                    "Desativar",
                    use_container_width=True,
                    disabled=categoria_atual is None or not categoria_atual.ativo,
                    key="desativar_cat_btn",
                )

            if salvar_cat:
                if not nome_cat.strip():
                    st.error("Informe um nome para a categoria.")
                else:
                    existente = (
                        db.query(ProductCategory)
                        .filter(ProductCategory.nome == nome_cat.strip())
                        .first()
                    )
                    if existente and (
                        not categoria_atual or existente.id != categoria_atual.id
                    ):
                        st.error("Já existe uma categoria com esse nome.")
                    else:
                        if not categoria_atual:
                            categoria_atual = ProductCategory(
                                nome=nome_cat.strip(),
                                descricao=descricao_cat or None,
                                ativo=ativo_cat,
                            )
                            db.add(categoria_atual)
                        else:
                            categoria_atual.nome = nome_cat.strip()
                            categoria_atual.descricao = descricao_cat or None
                            categoria_atual.ativo = ativo_cat
                        db.commit()
                        st.success("Categoria salva com sucesso.")
                        st.rerun()

            if desativar_cat and categoria_atual:
                categoria_atual.ativo = False
                db.commit()
                st.success("Categoria desativada.")
                st.rerun()

finally:
    db.close()

