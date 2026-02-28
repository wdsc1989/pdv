"""
Configuração do banco de dados para o PDV
- Suporta SQLite para desenvolvimento local
- Suporta PostgreSQL (Hostinger/produção) via DATABASE_URL
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Carrega variáveis de ambiente do arquivo .env na raiz do projeto
PROJECT_ROOT = Path(__file__).parent.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Diretório do banco de dados local (SQLite)
DB_DIR = PROJECT_ROOT / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)

# DATABASE_URL:
# - Em produção (Hostinger): postgresql://usuario:senha@host:porta/pdv_db
# - Em desenvolvimento:
#     - Se não definido, usa SQLite em data/pdv.db
#     - Opcionalmente, você pode apontar para um PostgreSQL local
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DB_DIR / 'pdv.db'}"

# Criação do engine conforme o tipo de banco
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
    )
else:
    # SQLite (desenvolvimento local)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para os modelos
Base = declarative_base()


def get_db():
    """
    Dependency simples para obter uma sessão do banco de dados.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Cria todas as tabelas definidas nos modelos.
    Deve ser chamada uma vez na inicialização da aplicação.
    """
    # Importa modelos aqui para registrar no metadata
    from models import (  # noqa: F401
        user,
        product_category,
        product,
        stock_entry,
        accessory,
        cash_session,
        sale,
        account_payable,
        ai_config,
    )

    Base.metadata.create_all(bind=engine)

    # Migração: tabelas accessory_stock e accessory_sales (SQLite)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            for table_name, create_sql in [
                (
                    "accessory_stock",
                    """
                    CREATE TABLE accessory_stock (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        preco REAL NOT NULL UNIQUE,
                        quantidade REAL NOT NULL DEFAULT 0.0
                    )
                    """,
                ),
                (
                    "accessory_sales",
                    """
                    CREATE TABLE accessory_sales (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        data_venda DATE NOT NULL,
                        preco REAL NOT NULL,
                        quantidade REAL NOT NULL DEFAULT 0.0
                    )
                    """,
                ),
                (
                    "accessory_stock_entries",
                    """
                    CREATE TABLE accessory_stock_entries (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        data_entrada DATE NOT NULL,
                        preco REAL NOT NULL,
                        quantidade REAL NOT NULL DEFAULT 0.0
                    )
                    """,
                ),
            ]:
                r = conn.execute(
                    text(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                    )
                )
                if r.fetchone() is None:
                    conn.execute(text(create_sql))
                    conn.commit()
            # Migração: coluna repasse_feito em accessory_sales (SQLite)
            r = conn.execute(
                text("SELECT name FROM pragma_table_info('accessory_sales') WHERE name = 'repasse_feito'")
            )
            if r.fetchone() is None:
                conn.execute(
                    text("ALTER TABLE accessory_sales ADD COLUMN repasse_feito BOOLEAN DEFAULT 0")
                )
                conn.commit()

            # Índices para accessory_sales e accessory_stock_entries
            for idx_name, create_idx in [
                ("ix_accessory_sales_data_venda", "CREATE INDEX ix_accessory_sales_data_venda ON accessory_sales (data_venda)"),
                ("ix_accessory_stock_entries_data_entrada", "CREATE INDEX ix_accessory_stock_entries_data_entrada ON accessory_stock_entries (data_entrada)"),
            ]:
                r = conn.execute(
                    text(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'")
                )
                if r.fetchone() is None:
                    conn.execute(text(create_idx))
                    conn.commit()

    # Migração: tabela stock_entries (SQLite)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            r = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_entries'"
                )
            )
            if r.fetchone() is None:
                conn.execute(
                    text(
                        """
                    CREATE TABLE stock_entries (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        product_id INTEGER NOT NULL,
                        quantity REAL NOT NULL DEFAULT 0.0,
                        data_entrada DATE NOT NULL,
                        observacao VARCHAR(200),
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(product_id) REFERENCES products (id)
                    )
                    """
                    )
                )
                conn.execute(
                    text("CREATE INDEX ix_stock_entries_product_id ON stock_entries (product_id)")
                )
                conn.execute(
                    text("CREATE INDEX ix_stock_entries_data_entrada ON stock_entries (data_entrada)")
                )
                conn.commit()

    # Migração: adiciona coluna status na tabela sales se não existir (SQLite)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            r = conn.execute(
                text("SELECT name FROM pragma_table_info('sales') WHERE name = 'status'")
            )
            if r.fetchone() is None:
                conn.execute(
                    text(
                        "ALTER TABLE sales ADD COLUMN status VARCHAR(20) DEFAULT 'concluida'"
                    )
                )
                conn.commit()

    # Migração: adiciona coluna signo na tabela users se não existir (SQLite)
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            r = conn.execute(
                text("SELECT name FROM pragma_table_info('users') WHERE name = 'signo'")
            )
            if r.fetchone() is None:
                conn.execute(text("ALTER TABLE users ADD COLUMN signo VARCHAR(20)"))
                conn.commit()

    # Migração: adiciona coluna signo na tabela users se não existir (PostgreSQL)
    if DATABASE_URL.startswith("postgresql"):
        with engine.connect() as conn:
            r = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'signo'"
                )
            )
            if r.fetchone() is None:
                conn.execute(text("ALTER TABLE users ADD COLUMN signo VARCHAR(20)"))
                conn.commit()

