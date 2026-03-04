# PDV — Deploy para produção

## Pré-requisitos

- Python 3.10+
- PostgreSQL (produção) ou SQLite (desenvolvimento)
- Conta OpenAI (ou outro provedor) para relatórios por voz e agentes de IA

## 1. Variáveis de ambiente

Copie o exemplo e ajuste:

```bash
cp .env.example .env
```

Edite `.env` e defina pelo menos:

| Variável | Obrigatório em produção | Descrição |
|----------|-------------------------|-----------|
| `DATABASE_URL` | Sim (PostgreSQL) | Ex: `postgresql://usuario:senha@host:5432/pdv_db` |
| `AI_FIXED_API_KEY` | Opcional | API key da OpenAI (ou use a tela Administração > Configuração de IA) |
| `AI_FIXED_CONFIG_ENABLED` | Opcional | `true` para forçar uso das variáveis de IA (ignora config no banco) |

Sem `DATABASE_URL`, o app usa SQLite em `data/pdv.db` (adequado só para dev/teste).

## 2. Instalação

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

## 3. Executar em produção

### Hostinger (VPS já configurada)

Se o PDV já está na Hostinger e você só quer **atualizar o código**, use o redeploy: commit + push para `main`, depois execute `.\scripts\Redeploy-PDV.ps1` na pasta do projeto. Detalhes em **[DEPLOY_HOSTINGER.md](DEPLOY_HOSTINGER.md)** (seção "Publicar evolução").

### Opção A: Servidor próprio (Linux)

```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Recomendado: colocar atrás de um reverse proxy (Nginx/Caddy) com HTTPS e configurar `--server.headless true` (já em `.streamlit/config.toml`).

### Opção B: Streamlit Community Cloud

1. Suba o repositório no GitHub.
2. Em [share.streamlit.io](https://share.streamlit.io), conecte o repo e configure:
   - **Main file path:** `app.py`
   - **Secrets** (ou variáveis do app): adicione `DATABASE_URL` e, se quiser, `AI_FIXED_API_KEY`.
3. Para PostgreSQL na nuvem, use um serviço (Neon, Supabase, Hostinger, etc.) e use a URL de conexão em `DATABASE_URL`.

### Opção C: Docker (exemplo)

Crie um `Dockerfile` na raiz:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build e execução:

```bash
docker build -t pdv-app .
docker run -p 8501:8501 --env-file .env pdv-app
```

## 4. Segurança

- **Nunca** commite `.env` ou `.streamlit/secrets.toml` (já estão no `.gitignore`).
- Em produção, use **HTTPS** (proxy reverso ou provedor com SSL).
- Troque a senha do usuário admin padrão após o primeiro acesso (Administração > Usuários).
- Se usar `AI_FIXED_API_KEY`, restrinja o acesso à aplicação (login obrigatório já está no app).

## 6. Banco de dados (PostgreSQL)

- Crie o banco, por exemplo: `CREATE DATABASE pdv_db;`
- O app cria as tabelas na primeira execução (`init_db()`).
- Usuário admin padrão é criado automaticamente (veja `services/auth_service.py` — altere a senha inicial no código ou pela tela após o primeiro login).

## 7. Versões fixas (opcional)

Para reproduzir exatamente o ambiente:

```bash
pip freeze > requirements-lock.txt
# Em produção: pip install -r requirements-lock.txt
```
