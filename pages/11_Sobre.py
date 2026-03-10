import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from services.auth_service import AuthService
from utils.navigation import show_sidebar


st.set_page_config(page_title="Sobre", page_icon="ℹ️", layout="wide")

if not AuthService.is_authenticated():
    st.warning("Faça login para acessar esta página.")
    st.stop()
show_sidebar()

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

st.markdown("#### 📄 Contas a Pagar e Contas a Receber")
st.markdown(
    "**Contas a pagar:** cadastre contas com fornecedor, vencimento e valor; marque como pagas. "
    "**Contas a receber:** cadastre vendas fiado (cliente, vencimento, valor) e marque como recebidas. "
    "Ambos são alertados no resumo diário do Agente de Relatórios."
)

st.markdown("#### 📋 Agente de Contas")
st.markdown(
    "Cadastre contas a pagar e a receber em **linguagem natural**. Exemplos: \"Cadastre conta de energia no valor de 120 para 10/02/2026\", "
    "\"Para o cliente Maria, 50 reais a receber em 05/02/2026\", \"Aluguel 800 reais todo dia 8 dos meses de 2026\". "
    "O agente pergunta o que faltar e **confirma antes de inserir**. Suporta cadastro em massa (mensal, ano inteiro)."
)

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
    "6. Use o **Agente de Relatórios** para perguntas em linguagem natural e análise do dia (admin).  \n"
    "7. Em **Administração**, configure o recibo, a logo do menu e o **signo** do usuário para ver o horóscopo na página Início."
)
