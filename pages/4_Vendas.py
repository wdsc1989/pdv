import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select, func

from config.database import SessionLocal
from models.cash_session import CashSession
from models.product import Product
from models.sale import Sale, SaleItem
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar


st.set_page_config(page_title="Vendas", page_icon="🧾", layout="wide")


AuthService.require_roles(["admin", "gerente", "vendedor"])
show_sidebar()

if "show_total_dia" not in st.session_state:
    st.session_state.show_total_dia = False  # Por padrão valor fica oculto

db = SessionLocal()

try:
    sessao_aberta = (
        db.query(CashSession).filter(CashSession.status == "aberta").first()
    )
    if not sessao_aberta:
        st.error("Não há caixa aberto. Abra o caixa em **Caixa** para liberar vendas.")
        st.stop()

    produtos = (
        db.execute(
            select(Product)
            .where(Product.ativo.is_(True))
            .order_by(Product.nome)
        )
        .scalars()
        .all()
    )
    if not produtos:
        st.info("Nenhum produto cadastrado. Cadastre produtos em **Produtos** antes de vender.")
        st.stop()

    # Total vendido hoje no canto superior direito (compacto)
    total_dia = (
        db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
        .filter(Sale.data_venda == date.today())
        .filter(Sale.status != "cancelada")
        .scalar()
    )
    valor_visivel = (
        format_currency(total_dia)
        if st.session_state.show_total_dia
        else "••••••"
    )

    col_titulo, col_total = st.columns([1, 1])
    with col_titulo:
        st.markdown(
            "<p style='margin:0 0 0.25rem 0; font-size:1.25rem;'><strong>🧾 Vendas (PDV)</strong></p>"
            "<p style='margin:0; font-size:0.8rem; color:#666;'>Adicione os produtos à sacola e finalize a venda. Caixa precisa estar aberto.</p>",
            unsafe_allow_html=True,
        )
    with col_total:
        # Valor + botão ícone na mesma linha; CSS para botão menor
        st.markdown(
            "<style>div:has(#total-dia-toggle-wrap) + div button { font-size: 0.7rem !important; "
            "padding: 0.15rem 0.4rem !important; min-height: 1.5rem !important; line-height: 1.2 !important; }</style>"
            "<div id='total-dia-toggle-wrap' style='display:none'></div>",
            unsafe_allow_html=True,
        )
        c_val, c_btn = st.columns([5, 1])
        with c_val:
            st.markdown(
                f"<p style='margin:0; text-align:right; font-size:1rem;'><strong>{valor_visivel}</strong></p>",
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button(
                "\u25CB" if not st.session_state.show_total_dia else "\u25CF",  # ○ / ●
                key="toggle_total_dia",
                help="Mostrar ou ocultar valor",
            ):
                st.session_state.show_total_dia = not st.session_state.show_total_dia
                st.rerun()

    st.markdown("---")

    if "cart_items" not in st.session_state:
        st.session_state.cart_items = []

    if st.session_state.get("need_reset_qty_inputs"):
        st.session_state.pop("need_reset_qty_inputs", None)
        st.rerun()

    cart = st.session_state.cart_items
    n_itens = sum(int(item["quantidade"]) for item in cart)
    if n_itens > 0:
        st.markdown(f"**Itens na sacola:** {n_itens} peça(s)")
        st.markdown("---")

    col_prod, col_cart = st.columns([1, 2])

    # Passo 1: botão para abrir página de busca de produtos
    with col_prod:
        st.subheader("Passo 1: Selecionar produto")
        st.caption("Clique em **Buscar produto** para abrir o catálogo, escolher os itens e voltar com a sacola preenchida.")

        if st.button("🔍 Buscar produto", type="primary", use_container_width=True, key="btn_buscar_produto"):
            st.switch_page("pages/4a_Selecionar_Produtos.py")

    with col_cart:
        st.subheader("Passo 2: Sacola e finalizar")
        cart = st.session_state.cart_items
        if not cart:
            st.info("Nenhum item na sacola. Adicione produtos na coluna à esquerda.")
        else:
            linhas = []
            total_vendido = 0.0
            total_lucro = 0.0
            total_pecas = 0
            for i, item in enumerate(cart):
                subtotal = item["preco_venda"] * item["quantidade"]
                lucro_item = (
                    (item["preco_venda"] - item["preco_custo"]) * item["quantidade"]
                )
                total_vendido += subtotal
                total_lucro += lucro_item
                total_pecas += int(item["quantidade"])
                linhas.append(
                    {
                        "Item": i + 1,
                        "Código": item["codigo"],
                        "Nome": item["nome"],
                        "Qtd": item["quantidade"],
                        "Preço": format_currency(item["preco_venda"]),
                        "Subtotal": format_currency(subtotal),
                    }
                )

            st.dataframe(linhas, use_container_width=True, hide_index=True)

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric("Peças", total_pecas)
            with col_t2:
                st.metric("Total da venda", format_currency(total_vendido))
            with col_t3:
                margem = (total_lucro / total_vendido * 100) if total_vendido > 0 else 0.0
                st.metric("Margem (%)", f"{margem:.2f}")

            st.markdown("---")
            st.subheader("Confirmação da venda")
            col_pg, col_chk = st.columns([2, 1])
            with col_pg:
                tipo_pagamento = st.selectbox(
                    "Tipo de pagamento",
                    options=["dinheiro", "debito", "credito", "pix", "outro"],
                )
            with col_chk:
                imprimir_extrato = st.checkbox(
                    "Imprimir extrato não fiscal", value=True
                )

            # Confirmação antes de finalizar: sacola é limpa imediatamente após confirmar
            if st.session_state.get("confirmar_venda") is True:
                st.warning(
                    f"Confirmar venda de **{format_currency(total_vendido)}**? "
                    "A sacola será esvaziada após a confirmação."
                )
                col_ok, col_cancel = st.columns(2)
                with col_ok:
                    if st.button("Sim, confirmar e finalizar", type="primary", use_container_width=True):
                        venda = Sale(
                            cash_session_id=sessao_aberta.id,
                            data_venda=date.today(),
                            total_vendido=total_vendido,
                            total_lucro=total_lucro,
                            total_pecas=total_pecas,
                            tipo_pagamento=tipo_pagamento,
                            status="concluida",
                        )
                        db.add(venda)
                        db.flush()
                        for item in cart:
                            produto = db.get(Product, item["product_id"])
                            if not produto:
                                continue
                            produto.estoque_atual = (produto.estoque_atual or 0) - item["quantidade"]
                            subtotal = item["preco_venda"] * item["quantidade"]
                            lucro_item = (item["preco_venda"] - item["preco_custo"]) * item["quantidade"]
                            db.add(
                                SaleItem(
                                    sale_id=venda.id,
                                    product_id=produto.id,
                                    quantidade=item["quantidade"],
                                    preco_unitario=item["preco_venda"],
                                    preco_custo_unitario=item["preco_custo"],
                                    subtotal=subtotal,
                                    lucro_item=lucro_item,
                                )
                            )
                        db.commit()
                        st.session_state.cart_items = []
                        st.session_state.pop("confirmar_venda", None)
                        st.session_state.need_reset_qty_inputs = True
                        st.success(f"Venda registrada. Total: {format_currency(total_vendido)}. Sacola esvaziada.")
                        if imprimir_extrato:
                            st.session_state.print_receipt_sale_id = venda.id
                            st.switch_page("pages/9_Recibo_Impressao.py")
                        else:
                            st.rerun()
                with col_cancel:
                    if st.button("Cancelar", use_container_width=True):
                        st.session_state.pop("confirmar_venda", None)
                        st.rerun()
            else:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("Finalizar venda", type="primary", use_container_width=True):
                        st.session_state.confirmar_venda = True
                        st.rerun()
                with col_btn2:
                    if st.button("Limpar sacola", use_container_width=True):
                        st.session_state.cart_items = []
                        st.session_state.need_reset_qty_inputs = True
                        st.rerun()

    # Registros de vendas da sessão de caixa aberta + edição
    st.markdown("---")
    with st.expander("Vendas registradas nesta sessão de caixa", expanded=False):
        vendas_sessao = (
            db.query(Sale)
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .order_by(Sale.id.desc())
            .limit(50)
            .all()
        )

        if not vendas_sessao:
            st.info("Nenhuma venda registrada ainda nesta sessão de caixa.")
        else:
            # status pode não existir em bancos antigos
            for v in vendas_sessao:
                status_v = getattr(v, "status", "concluida")
                st.markdown(f"**Venda #{v.id}** — {v.data_venda.strftime('%d/%m/%Y') if v.data_venda else '-'} — {format_currency(v.total_vendido)} — {v.tipo_pagamento or '-'} — *{status_v}*")
                col_info, col_edit = st.columns([3, 1])
                with col_edit:
                    if st.button("Editar", key=f"edit_{v.id}", use_container_width=True):
                        st.session_state.editar_venda_id = v.id
                        st.rerun()

            # Área de edição da venda selecionada
            editar_id = st.session_state.get("editar_venda_id")
            if editar_id is not None:
                st.markdown("---")
                venda_edit = db.get(Sale, editar_id)
                if venda_edit is None or venda_edit.cash_session_id != sessao_aberta.id:
                    st.session_state.pop("editar_venda_id", None)
                    st.rerun()
                else:
                    status_edit = getattr(venda_edit, "status", "concluida")
                    if status_edit == "cancelada":
                        st.info("Esta venda está cancelada (stornada). Não é possível editar.")
                        if st.button("Fechar", key="fechar_edit"):
                            st.session_state.pop("editar_venda_id", None)
                            st.rerun()
                    else:
                        # Remover item da venda (se foi clicado "Remover" em algum item)
                        remover_item_id = st.session_state.pop("remover_item_id", None)
                        if remover_item_id is not None:
                            item_rem = db.get(SaleItem, remover_item_id)
                            if item_rem and item_rem.sale_id == venda_edit.id:
                                prod = db.get(Product, item_rem.product_id)
                                if prod:
                                    prod.estoque_atual = (prod.estoque_atual or 0) + item_rem.quantidade
                                venda_edit.total_vendido = (venda_edit.total_vendido or 0) - (item_rem.subtotal or 0)
                                venda_edit.total_lucro = (venda_edit.total_lucro or 0) - (item_rem.lucro_item or 0)
                                venda_edit.total_pecas = (venda_edit.total_pecas or 0) - int(item_rem.quantidade or 0)
                                db.delete(item_rem)
                                # Se não restar nenhum item, marca a venda como cancelada automaticamente
                                if (venda_edit.total_pecas or 0) <= 0:
                                    venda_edit.status = "cancelada"
                                db.commit()
                                st.success(
                                    "Item removido. Estoque devolvido."
                                    + (" Venda cancelada por não possuir mais itens." if (venda_edit.total_pecas or 0) <= 0 else "")
                                )
                                st.rerun()

                        st.subheader(f"Edição da venda #{venda_edit.id}")
                        st.caption("Altere o tipo de pagamento ou remova itens colocados por engano. O estoque é ajustado ao remover.")

                        # Lista de itens da venda para edição (remover item)
                        st.markdown("#### Itens da venda")
                        itens_venda = list(venda_edit.itens)
                        if not itens_venda:
                            st.info("Esta venda não possui mais itens. Você pode fechar ou stornar a venda.")
                        else:
                            for item in itens_venda:
                                prod = db.get(Product, item.product_id)
                                cod = prod.codigo if prod else "-"
                                nome = prod.nome if prod else "-"
                                col1, col2, col3, col4, col5 = st.columns([1, 2, 0.6, 1, 0.8])
                                with col1:
                                    st.text(cod)
                                with col2:
                                    st.text(nome)
                                with col3:
                                    st.text(f"{int(item.quantidade)} un.")
                                with col4:
                                    st.text(format_currency(item.subtotal or 0))
                                with col5:
                                    if st.button("Remover", key=f"remover_item_{item.id}", type="secondary"):
                                        st.session_state.remover_item_id = item.id
                                        st.rerun()
                            st.markdown(f"**Total da venda:** {format_currency(venda_edit.total_vendido or 0)} — **Peças:** {venda_edit.total_pecas or 0}")

                        st.markdown("---")
                        st.markdown("#### Tipo de pagamento")
                        opcoes_pag = ["dinheiro", "debito", "credito", "pix", "outro"]
                        idx_atual = opcoes_pag.index(
                            (venda_edit.tipo_pagamento or "dinheiro").lower()
                        ) if (venda_edit.tipo_pagamento or "").lower() in opcoes_pag else 0
                        novo_tipo = st.selectbox(
                            "Tipo de pagamento",
                            options=opcoes_pag,
                            index=idx_atual,
                            key="edit_tipo_pag",
                        )
                        col_salvar, col_stornar, col_fechar = st.columns(3)
                        with col_salvar:
                            if st.button("Salvar alterações", key="salvar_edit"):
                                venda_edit.tipo_pagamento = novo_tipo
                                db.commit()
                                st.success("Alterações salvas.")
                                st.rerun()
                        with col_stornar:
                            if st.button("Stornar venda (cancelar)", type="secondary", key="stornar_edit"):
                                st.session_state.confirmar_storno_id = venda_edit.id
                                st.rerun()
                        with col_fechar:
                            if st.button("Fechar", key="fechar_edit2"):
                                st.session_state.pop("editar_venda_id", None)
                                st.rerun()

    # Confirmação de storno (reverter estoque e marcar venda como cancelada)
    if st.session_state.get("confirmar_storno_id") is not None:
        st.markdown("---")
        sid = st.session_state.confirmar_storno_id
        v_storno = db.get(Sale, sid)
        if v_storno and v_storno.cash_session_id == sessao_aberta.id:
            st.warning(f"Stornar a venda **#{sid}**? O estoque dos itens será devolvido e a venda ficará cancelada.")
            if st.button("Sim, stornar venda", type="primary", key="confirm_storno"):
                for item in v_storno.itens:
                    prod = db.get(Product, item.product_id)
                    if prod:
                        prod.estoque_atual = (prod.estoque_atual or 0) + item.quantidade
                v_storno.status = "cancelada"
                db.commit()
                st.session_state.pop("confirmar_storno_id", None)
                st.session_state.pop("editar_venda_id", None)
                st.success("Venda stornada. Estoque devolvido.")
                st.rerun()
            if st.button("Não, cancelar", key="cancel_storno"):
                st.session_state.pop("confirmar_storno_id", None)
                st.rerun()
finally:
    db.close()

