"""
Página de seleção de produtos para a venda.
Acessada por "Buscar produto" na página de Vendas.
Permite adicionar produtos à sacola e voltar para vendas.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
from sqlalchemy import select

from config.database import init_db, SessionLocal
from models.cash_session import CashSession
from models.product import Product
from models.user_cart import UserCartItem
from services.auth_service import AuthService
from utils.formatters import format_currency
from utils.navigation import show_sidebar

init_db()


st.set_page_config(page_title="Buscar produto", page_icon=":material/search:", layout="wide")

AuthService.require_roles(["admin", "gerente", "vendedor"])
show_sidebar()

db = SessionLocal()

try:
    sessao_aberta = db.query(CashSession).filter(CashSession.status == "aberta").first()
    if not sessao_aberta:
        st.error("Não há caixa aberto. Abra o caixa em **Caixa** para liberar vendas.")
        if st.button("Voltar para Vendas"):
            st.switch_page("pages/4_Vendas.py")
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
        if st.button("Voltar para Vendas"):
            st.switch_page("pages/4_Vendas.py")
        st.stop()

    user = AuthService.get_current_user()
    user_id = user.get("id") if user else None

    if "cart_items" not in st.session_state:
        st.session_state.cart_items = []

    # Carrega carrinho persistido do banco quando vazio (quantidades fixas ao refazer login)
    if user_id is not None and len(st.session_state.cart_items) == 0:
        saved = (
            db.execute(
                select(UserCartItem, Product)
                .join(Product, UserCartItem.product_id == Product.id)
                .where(UserCartItem.user_id == user_id)
                .where(UserCartItem.quantity > 0)
            )
            .all()
        )
        if saved:
            st.session_state.cart_items = [
                {
                    "product_id": row[1].id,
                    "codigo": row[1].codigo,
                    "nome": row[1].nome,
                    "quantidade": int(row[0].quantity),
                    "preco_venda": row[1].preco_venda,
                    "preco_custo": row[1].preco_custo,
                }
                for row in saved
            ]

    cart = st.session_state.cart_items
    n_itens = sum(int(item["quantidade"]) for item in cart)

    # Filtros: busca (campo de texto — digite e pressione Enter para filtrar), categoria, etc.
    categorias = sorted({p.categoria for p in produtos if p.categoria}, key=lambda x: (x or "").lower())
    marcas = sorted({p.marca for p in produtos if p.marca}, key=lambda x: (x or "").lower())

    # Linha 1: Filtros (Categoria, Fornecedor, Estoque, Ordenar)
    col_cat, col_forn, col_estoque, col_ordem = st.columns(4)
    with col_cat:
        filtro_cat = st.selectbox(
            "Categoria",
            options=["Todas"] + categorias,
            key="filtro_cat_sel",
        )

    with col_forn:
        filtro_marca = st.selectbox(
            "Fornecedor",
            options=["Todas"] + marcas,
            key="filtro_marca_sel",
        )

    with col_estoque:
        filtro_estoque = st.selectbox(
            "Estoque",
            options=["Todos", "Com estoque", "Sem estoque"],
            key="filtro_estoque_sel",
        )

    with col_ordem:
        ordem = st.selectbox(
            "Ordenar por",
            options=["Nome", "Código", "Preço (menor)", "Preço (maior)", "Estoque"],
            key="ordem_sel",
        )

    # Linha 2: Busca — lista atualiza ao pressionar Enter ou após 2 s de pausa na digitação
    termo = st.text_input(
        "Buscar",
        placeholder="Pesquisar...",
        key="busca_selecionar_prod",
    )
    termo = (termo or "").strip().lower()

    # Debounce + Enter aplicam o filtro; loop mantém foco na caixa após cada rerun
    _busca_debounce_js = """
    <div id="busca-debounce-helper"></div>
    <script>
    (function() {
        var DELAY_MS = 500;
        var REFOCUS_KEY = "pdv_refocus_busca";
        var PLACEHOLDER_PART = "Pesquisar";
        function findBuscaInput() {
            var inputs = document.querySelectorAll('input[placeholder*="' + PLACEHOLDER_PART + '"]');
            return inputs.length > 0 ? inputs[0] : null;
        }
        function startRefocusLoop() {
            if (sessionStorage.getItem(REFOCUS_KEY) !== "1") return;
            var count = 0;
            var maxTicks = 6000;
            var iv = setInterval(function() {
                count++;
                if (count > maxTicks) {
                    clearInterval(iv);
                    sessionStorage.removeItem(REFOCUS_KEY);
                    return;
                }
                var el = findBuscaInput();
                if (el && document.activeElement !== el) el.focus();
            }, 50);
        }
        function attachDebounce() {
            var input = findBuscaInput();
            if (!input) return;
            if (input._buscaDebounceAttached) return;
            input._buscaDebounceAttached = true;
            var timeout;
            input.addEventListener("input", function() {
                clearTimeout(timeout);
                timeout = setTimeout(function() {
                    sessionStorage.setItem(REFOCUS_KEY, "1");
                    input.blur();
                    var e = new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true });
                    input.dispatchEvent(e);
                }, DELAY_MS);
            });
            input.addEventListener("keydown", function(ev) {
                if (ev.key === "Enter") sessionStorage.setItem(REFOCUS_KEY, "1");
            });
        }
        function init() {
            if (sessionStorage.getItem(REFOCUS_KEY) === "1") startRefocusLoop();
            attachDebounce();
        }
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
        else init();
        setTimeout(init, 200);
        setTimeout(init, 500);
        setTimeout(init, 1000);
        setTimeout(init, 2000);
    })();
    </script>
    """
    try:
        st.html(_busca_debounce_js, unsafe_allow_javascript=True)
    except (AttributeError, TypeError):
        pass  # Streamlit antigo sem st.html: use Enter para filtrar

    # Voltar para vendas (abaixo da pesquisa, largura fixa — não responsivo)
    if st.button("Voltar para vendas", type="primary", key="btn_voltar_vendas", use_container_width=False):
        st.switch_page("pages/4_Vendas.py")

    # Aplica filtros
    produtos_filtrados = produtos

    if termo:
        produtos_filtrados = [
            p for p in produtos_filtrados
            if termo in (p.nome or "").lower()
            or termo in (p.codigo or "").lower()
        ]

    if filtro_cat != "Todas":
        produtos_filtrados = [p for p in produtos_filtrados if p.categoria == filtro_cat]

    if filtro_marca != "Todas":
        produtos_filtrados = [p for p in produtos_filtrados if p.marca == filtro_marca]

    if filtro_estoque == "Com estoque":
        produtos_filtrados = [p for p in produtos_filtrados if (p.estoque_atual or 0) > 0]
    elif filtro_estoque == "Sem estoque":
        produtos_filtrados = [p for p in produtos_filtrados if (p.estoque_atual or 0) <= 0]

    # Ordenação
    if ordem == "Nome":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: (p.nome or "").lower())
    elif ordem == "Código":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: (p.codigo or "").lower())
    elif ordem == "Preço (menor)":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.preco_venda or 0))
    elif ordem == "Preço (maior)":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.preco_venda or 0), reverse=True)
    elif ordem == "Estoque":
        produtos_filtrados = sorted(produtos_filtrados, key=lambda p: float(p.estoque_atual or 0), reverse=True)

    if n_itens > 0:
        st.markdown(f"**Itens na sacola:** {n_itens} peça(s)")

    st.markdown("---")

    if not produtos_filtrados:
        st.info("Nenhum produto encontrado para este filtro.")
    else:
        st.markdown(
            "<style>"
            "[data-testid='stNumberInput'] input { "
            "width: 70px !important; max-width: 70px !important; min-width: 70px !important; "
            "box-sizing: border-box !important; } "
            "div[data-testid='stHorizontalBlock']:has(.qtd-col-spacer) { align-items: stretch !important; } "
            "div[data-testid='stHorizontalBlock']:has(.qtd-col-spacer) > div:first-child { "
            "display: flex !important; flex-direction: column !important; min-height: 140px !important; align-self: stretch !important; } "
            "div[data-testid='stHorizontalBlock']:has(.qtd-col-spacer) > div:first-child > div:first-child { "
            "flex: 1 1 0 !important; min-height: 0 !important; } "
            "</style>",
            unsafe_allow_html=True,
        )
        uploads_dir = Path(__file__).resolve().parents[1] / "uploads"
        # Cabeçalho da tabela: Quantidade, Imagem, Código, Nome, Categoria, Estoque
        w = [0.1, 0.12, 0.12, 0.35, 0.2, 0.11]
        h_cols = st.columns(w)
        with h_cols[0]:
            st.markdown("**Quantidade**")
        with h_cols[1]:
            st.markdown("**Imagem**")
        with h_cols[2]:
            st.markdown("**Código**")
        with h_cols[3]:
            st.markdown("**Nome**")
        with h_cols[4]:
            st.markdown("**Categoria**")
        with h_cols[5]:
            st.markdown("**Estoque**")
        st.markdown("---")

        for p in produtos_filtrados:
            row = st.columns(w)
            with row[0]:
                st.markdown("<div class='qtd-col-spacer'></div>", unsafe_allow_html=True)
                qtd_atual = sum(int(item["quantidade"]) for item in cart if item["product_id"] == p.id)
                nova_qtd = st.number_input(
                    "Quantidade",
                    min_value=0,
                    value=int(qtd_atual),
                    step=1,
                    key=f"qty_sel_{p.id}",
                    label_visibility="collapsed",
                )
                if int(nova_qtd) != qtd_atual:
                    novo_cart = list(cart)
                    if nova_qtd <= 0:
                        novo_cart = [item for item in novo_cart if item["product_id"] != p.id]
                    else:
                        for item in novo_cart:
                            if item["product_id"] == p.id:
                                item["quantidade"] = int(nova_qtd)
                                break
                        else:
                            novo_cart.append({
                                "product_id": p.id,
                                "codigo": p.codigo,
                                "nome": p.nome,
                                "quantidade": int(nova_qtd),
                                "preco_venda": p.preco_venda,
                                "preco_custo": p.preco_custo,
                            })
                    st.session_state.cart_items = novo_cart
                    if user_id is not None:
                        existente = db.query(UserCartItem).filter(
                            UserCartItem.user_id == user_id,
                            UserCartItem.product_id == p.id,
                        ).first()
                        if nova_qtd <= 0:
                            if existente:
                                db.delete(existente)
                        else:
                            if existente:
                                existente.quantity = int(nova_qtd)
                            else:
                                db.add(UserCartItem(
                                    user_id=user_id,
                                    product_id=p.id,
                                    quantity=int(nova_qtd),
                                ))
                        db.commit()
                    st.rerun()
            with row[1]:
                img_path = None
                if p.imagem_path:
                    candidate = uploads_dir / p.imagem_path
                    if candidate.exists():
                        img_path = candidate
                if img_path:
                    st.image(str(img_path), width=70)
                else:
                    st.markdown(
                        "<div style='width:70px;height:50px;background:#eee;border-radius:4px;"
                        "display:flex;align-items:center;justify-content:center;font-size:9px;color:#999;'>"
                        "Sem imagem</div>",
                        unsafe_allow_html=True,
                    )
            with row[2]:
                st.markdown(f"**{p.codigo}**")
            with row[3]:
                nome_safe = (p.nome or "").replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(nome_safe)
            with row[4]:
                st.markdown(p.categoria or "—")
            with row[5]:
                estoque = p.estoque_atual if p.estoque_atual is not None else 0
                estoque_str = f"{estoque:.0f}" if estoque == int(estoque) else f"{estoque:.2f}"
                st.markdown(estoque_str)
            st.markdown("---")

finally:
    db.close()
