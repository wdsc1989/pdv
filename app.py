import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no path (para rodar de qualquer cwd)
_ROOT = Path(__file__).resolve().parents[0]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from config.database import init_db
from services.auth_service import AuthService, ensure_default_admin
from utils.formatters import format_date
from utils.navigation import show_sidebar


st.set_page_config(
    page_title="PDV - Loja de Roupas",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": None,
    },
)


@st.cache_resource
def initialize_app():
    """
    Inicializa o banco de dados e garante usuário admin padrão.
    """
    init_db()
    ensure_default_admin()


def login_page():
    st.markdown("# 🔐 PDV - Loja de Roupas")
    st.caption("Sistema de Ponto de Venda para loja de roupas")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Entrar no sistema")
        st.caption("Digite seu usuário e senha para acessar o PDV.")
        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Ex: admin")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if submit:
            if not username or not password:
                st.error("Por favor, preencha usuário e senha.")
            else:
                from config.database import SessionLocal

                db = SessionLocal()
                try:
                    user = AuthService.authenticate(db, username, password)
                    if user:
                        AuthService.login(user)
                        st.success(f"Bem-vindo, {user.name}!")
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos.")
                finally:
                    db.close()


def home_page():
    from datetime import datetime

    from config.database import SessionLocal
    from models.user import User
    from services.horoscope_service import get_horoscope_for_user

    user = AuthService.get_current_user()

    st.markdown("# 🏠 Início")
    if user:
        st.markdown(f"Olá, **{user['name']}**! Use o menu ao lado para navegar.")
    st.markdown("---")

    # Horóscopo: uma vez por sessão (cache); ao fazer logout e login de novo, carrega de novo (economiza tokens de IA)
    if user:
        db = SessionLocal()
        try:
            user_id = user.get("id")
            u = db.query(User).filter(User.id == user_id).first() if user_id else None
            signo = u.signo if u else user.get("signo")
            if signo:
                cache = st.session_state.get("horoscope_cache")
                if cache and cache.get("signo") == signo and cache.get("summary"):
                    horoscope = cache
                else:
                    if cache and cache.get("signo") != signo:
                        st.session_state.pop("horoscope_cache", None)
                    with st.spinner("Buscando seu horóscopo..."):
                        horoscope = get_horoscope_for_user(db, user_id or 0, signo)
                    if horoscope.get("summary"):
                        st.session_state["horoscope_cache"] = {"signo": signo, **horoscope}
                if horoscope.get("summary"):
                    st.markdown("#### 🌟 Horóscopo do dia")
                    st.markdown(horoscope["summary"])
                    if horoscope.get("full"):
                        with st.expander("Ver horóscopo no trabalho"):
                            st.markdown(horoscope["full"])
                    st.markdown("---")
            else:
                st.info(
                    "Cadastre seu **signo** em **Administração** (usuários) para ver aqui "
                    "o horóscopo do dia, buscado na internet e resumido com IA."
                )
                st.markdown("---")
        finally:
            db.close()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Módulos", "8", help="Caixa, Produtos, Vendas, Acessórios, Contas a Pagar, Relatórios, Agente de Relatórios, Administração")
    with col2:
        st.metric("Hoje", format_date(datetime.now()))
    with col3:
        st.metric("Perfil", user["role"] if user else "-")

    st.markdown("### O que o sistema oferece")

    st.markdown("#### 💰 Caixa")
    st.markdown("Abra e feche o caixa. As vendas ficam vinculadas à sessão de caixa aberta. Sem caixa aberto, não é possível vender.")

    st.markdown("#### 📦 Produtos")
    st.markdown(
        "- **Lista de produtos**: busque por código ou nome, filtre por categoria e status; selecione um produto e use **Abrir para edição**.\n"
        "- **Cadastrar ou editar**: grid de cards (como em Vendas) com busca por nome, código, categoria ou fornecedor; clique em **Editar** no card e preencha o formulário abaixo. **Novo produto** para cadastrar.\n"
        "- **Entrada de estoque**: ao editar um produto, registre entradas (quantidade e observação); o histórico aparece em Relatórios por período.\n"
        "- **Categorias**: na aba Categorias, visualize todas, busque por nome ou descrição, filtre por ativas/inativas; cadastre ou edite e desative quando necessário."
    )

    st.markdown("#### 📊 Estoque (aba dentro de Produtos)")
    st.markdown("Na página **Produtos**, aba **Estoque**: quantidades, estoque mínimo, valor em custo e venda, lucro no estoque. Destaque para produtos com estoque baixo.")

    st.markdown("#### 🧾 Vendas (PDV)")
    st.markdown(
        "Grid de produtos com busca (nome, código, categoria, fornecedor), paginação e quantidade no card. Sacola à direita com totais. "
        "Ao finalizar, marque **Imprimir extrato não fiscal** para abrir uma página de impressão do recibo para o cliente (layout configurável em Administração)."
    )

    st.markdown("#### 💎 Acessórios")
    st.markdown(
        "Controle de vendas de acessórios por preço e quantidade (tabelas separadas do PDV). "
        "**Aba Venda**: registrar venda (baixa no estoque), relatório de vendas com filtro por período (hoje, 7, 15, 30 dias, mês, personalizado) e por repasse; lucro 50%; marcar repasses ao fornecedor (50%) realizados. "
        "**Aba Ajuste de estoque**: estoque atual por preço (com totais), adicionar novo preço ou ajustar quantidade; relatório de entradas no período com filtros."
    )

    st.markdown("#### 📄 Contas a Pagar")
    st.markdown("Cadastre contas com fornecedor, vencimento e valor. Marque como pagas e acompanhe por período nos Relatórios.")

    st.markdown("#### 📈 Relatórios")
    st.markdown(
        "Filtro por período (diário, semanal, mensal, geral). Resumo: total vendido, lucro, margem, peças, número de vendas, ticket médio. "
        "Valor de estoque (custo e venda). **Entradas de estoque no período**. Produtos mais vendidos. Sessões de caixa. Contas a pagar por vencimento."
    )

    st.markdown("#### 🤖 Agente de Relatórios (admin/gerente)")
    st.markdown(
        "Perguntas em linguagem natural e respostas em tempo real com base nos dados do PDV. Ao abrir a página, uma **análise inicial do dia** é exibida (tendência, sazonalidade, pontos fortes e fracos para roupas femininas). "
        "**Análises avançadas**: previsões, tendências, sazonalidade (dados e mercado) e notícias atuais. Respeita a data do dia e, perto da virada do mês, inclui insights para a semana que começa. Cada usuário vê sua própria análise ao acessar (após troca de login, a análise é renovada)."
    )

    st.markdown("#### ⚙️ Administração (admin)")
    st.markdown(
        "Crie e gerencie usuários (perfis: admin, gerente, vendedor; **signo** para exibir o horóscopo na página Início). **Layout do recibo**: largura do papel, margem, fonte, textos de cabeçalho e rodapé. "
        "**Logo do menu**: envie uma imagem para aparecer no menu lateral no lugar de \"PDV\"."
    )

    st.markdown("---")
    st.markdown("### Próximos passos")
    st.markdown(
        "1. Abra o **Caixa** para liberar vendas.  \n"
        "2. Cadastre **Produtos** e **Categorias** em Produtos.  \n"
        "3. Use **Vendas** para registrar vendas e, se quiser, imprimir o recibo.  \n"
        "4. Em **Acessórios**, cadastre preços e quantidades no ajuste de estoque, registre vendas e marque os repasses (50%) ao fornecedor.  \n"
        "5. Acompanhe **Estoque** (aba em Produtos) e **Relatórios** (incluindo entradas de estoque por período).  \n"
        "6. Use o **Agente de Relatórios** para perguntas em linguagem natural e análise do dia (admin/gerente).  \n"
        "7. Em **Administração**, configure o recibo, a logo do menu e o **signo** do usuário para ver o horóscopo aqui na página Início."
    )


def main():
    initialize_app()
    AuthService.init_session_state()

    if not AuthService.is_authenticated():
        login_page()
    else:
        show_sidebar()
        home_page()


if __name__ == "__main__":
    main()

