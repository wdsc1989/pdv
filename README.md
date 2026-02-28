# PDV Loja de Roupas (Streamlit + PostgreSQL)

Aplicação de Ponto de Venda (PDV) para loja de roupas, construída em **Streamlit** com banco de dados **PostgreSQL** (novo database na Hostinger), suportando também **teste local com SQLite ou PostgreSQL local**.

## Funcionalidades principais

- **Autenticação e permissões**
  - Login por usuário/senha
  - Perfis: `admin`, `gerente`, `vendedor`
  - Controle de acesso por página (apenas gerente/admin veem faturamento e contas a pagar)

- **Caixa**
  - Abertura e fechamento de caixa
  - Uma sessão de caixa aberta por vez
  - Vendas sempre vinculadas a uma sessão de caixa

- **Produtos**
  - Cadastro de produtos com:
    - Código, nome, categoria, marca
    - Preço de custo, preço de venda
    - Estoque atual, estoque mínimo
    - **Imagem do produto** (upload e exibição)
  - Cálculo automático de **% de lucro** com base em custo e venda

- **Estoque**
  - Visualização do estoque atual
  - Atualização automática após vendas
  - Alerta de estoque baixo (com base em estoque mínimo)

- **Vendas (PDV)**
  - Seleção de produtos e quantidades
  - Finalização de venda:
    - Cria registros de venda e itens
    - Atualiza estoque
    - Vincula venda à sessão de caixa aberta

- **Contas a Pagar**
  - Cadastro, listagem, filtro por status e período
  - Marcar contas como pagas
  - Apenas `admin` e `gerente` têm acesso

- **Relatórios**
  - Diário, semanal, mensal e geral
  - Total vendido, total de lucro, quantidade de peças vendidas
  - Produtos mais vendidos
  - Sessões de caixa no período (aberturas, fechamentos, total vendido)
  - Visão de contas a pagar (apenas para `admin`/`gerente`)

## Estrutura básica do projeto

```text
PDV/
  app.py
  requirements.txt
  env.example.txt
  .env                # (não versionado)
  config/
    database.py
  models/
    __init__.py
    user.py
    product.py
    cash_session.py
    sale.py
    account_payable.py
  services/
    auth_service.py
  pages/
    0_Caixa.py
    1_Produtos.py
    2_Estoque.py
    3_Relatorios.py
    4_Vendas.py
    5_Contas_a_Pagar.py
    10_Admin.py
  utils/
    formatters.py
  uploads/
    products/         # Imagens dos produtos
  init_db.py
```

## Configuração de ambiente

1. Crie um ambiente virtual (recomendado):

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Configure o arquivo `.env`:

- Copie `env.example.txt` para `.env` e ajuste:
  - Para testes locais, deixe `DATABASE_URL` em branco (usa SQLite `data/pdv.db`) **ou** use um PostgreSQL local.
  - Em produção (Hostinger), configure `DATABASE_URL` com o banco PostgreSQL da VPS.

## Executando localmente

Com o ambiente configurado:

```bash
streamlit run app.py
```

- O sistema criará o banco (SQLite ou PostgreSQL, conforme `DATABASE_URL`).
- Um usuário `admin` padrão será criado (credenciais definidas no código `auth_service.py`).
- A partir daí você poderá:
  - Fazer login
  - Cadastrar produtos
  - Abrir caixa, registrar vendas
  - Controlar estoque, contas a pagar e gerar relatórios

Depois de testar localmente, basta configurar o `.env` no servidor (Hostinger) com o `DATABASE_URL` de produção e subir o código.

