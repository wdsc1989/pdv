"""
Script para inicializar o banco de dados do PDV.
- Cria todas as tabelas
- Garante a existência de um usuário admin padrão
"""
from config.database import init_db, SessionLocal
from services.auth_service import AuthService
from models.user import User


def main() -> None:
    print("📦 Inicializando banco de dados do PDV...")
    init_db()
    print("✅ Tabelas criadas (se não existiam).")

    # Garante usuário admin padrão
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
            print(
                "✅ Usuário admin criado: username=admin, senha=admin123 "
                "(altere em produção)."
            )
        else:
            print("ℹ️ Usuário admin já existe.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

