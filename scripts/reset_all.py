"""
Script para limpar todas as bases e testar do zero.
- Limpa todos os dados do banco (via SQL, sem apagar o arquivo)
- Remove imagens em uploads/ (logo e produtos)
- Recria o usuário admin padrão

Pode rodar mesmo com o Streamlit aberto.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import text

from config.database import DATABASE_URL, init_db, SessionLocal, engine
from services.auth_service import AuthService
from models.user import User


# Ordem: tabelas filhas primeiro (por causa das chaves estrangeiras)
TABLES_TO_TRUNCATE = [
    "stock_entries",
    "sale_items",
    "sales",
    "accounts_payable",
    "cash_sessions",
    "products",
    "product_categories",
    "accessory_sales",
    "accessory_stock_entries",
    "accessory_stock",
    "users",
]


def main() -> None:
    print("Limpando bases do PDV...")

    # 1. Limpar dados do banco (sem remover o arquivo)
    if DATABASE_URL.startswith("sqlite"):
        init_db()  # garante que tabelas existem
        with engine.connect() as conn:
            for table in TABLES_TO_TRUNCATE:
                try:
                    conn.execute(text(f"DELETE FROM {table}"))
                    conn.commit()
                    print("  Limpo:", table)
                except Exception as e:
                    # tabela pode não existir em DB antigo
                    print("  ", table, "-", e)
            # Resetar contadores de ID no SQLite
            try:
                conn.execute(text("DELETE FROM sqlite_sequence"))
                conn.commit()
            except Exception:
                pass
        print("  Banco de dados limpo (dados removidos).")
    else:
        print("  PostgreSQL: limpando tabelas...")
        init_db()
        with engine.connect() as conn:
            for table in TABLES_TO_TRUNCATE:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    conn.commit()
                    print("  Limpo:", table)
                except Exception as e:
                    print("  ", table, "-", e)

    # 2. Remover uploads (logo e produtos)
    uploads_dir = _ROOT / "uploads"
    removed = 0
    for subdir in ("logo", "products"):
        d = uploads_dir / subdir
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        removed += 1
                        print("  Removido:", f.name)
                    except Exception as e:
                        print("  Erro ao remover", f.name, "-", e)
    if removed == 0:
        print("  Nenhum arquivo em uploads para remover.")
    else:
        print("  Total em uploads:", removed)

    # 3. Criar usuário admin
    print("\nCriando usuario admin...")
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin:
            AuthService.create_user(
                db=db,
                username="admin",
                name="Administrador",
                password="admin123",
                role="admin",
            )
            print("  Usuario admin criado: admin / admin123")
        else:
            print("  Usuario admin ja existia (mantido).")
    finally:
        db.close()

    print("\nPronto. Pode testar do zero. (Atualize a pagina no navegador se o Streamlit estiver aberto.)")


if __name__ == "__main__":
    main()
