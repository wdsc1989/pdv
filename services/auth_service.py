"""
Serviço de autenticação e controle de acesso do PDV.
"""
from typing import Optional, Sequence

import bcrypt
import streamlit as st
from sqlalchemy.orm import Session

from config.database import SessionLocal
from models.user import User


class AuthService:
    """
    Gerencia autenticação, sessão e permissões básicas (roles).
    """

    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[User]:
        user = (
            db.query(User)
            .filter(User.username == username, User.active.is_(True))
            .first()
        )
        if user and AuthService.verify_password(password, user.password_hash):
            return user
        return None

    @staticmethod
    def create_user(
        db: Session,
        username: str,
        name: str,
        password: str,
        role: str,
        signo: Optional[str] = None,
    ) -> User:
        password_hash = AuthService.hash_password(password)
        user = User(
            username=username,
            name=name,
            password_hash=password_hash,
            role=role,
            active=True,
            signo=signo,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # ----- Session / estado -----

    @staticmethod
    def init_session_state() -> None:
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "user" not in st.session_state:
            st.session_state.user = None

    @staticmethod
    def login(user: User) -> None:
        st.session_state.authenticated = True
        st.session_state.user = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "signo": getattr(user, "signo", None),
        }

    @staticmethod
    def logout() -> None:
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.pop("horoscope_cache", None)
        st.session_state.pop("agente_initial_analysis_user_id", None)
        st.session_state.pop("chat_history", None)

    @staticmethod
    def is_authenticated() -> bool:
        return st.session_state.get("authenticated", False)

    @staticmethod
    def get_current_user() -> Optional[dict]:
        return st.session_state.get("user")

    # ----- Requisitos de acesso -----

    @staticmethod
    def require_auth() -> None:
        """
        Garante que o usuário esteja autenticado.
        Se não estiver, mostra mensagem e interrompe a execução da página.
        """
        AuthService.init_session_state()
        if not AuthService.is_authenticated():
            st.warning("Você precisa fazer login para acessar esta página.")
            st.stop()

    @staticmethod
    def require_roles(allowed_roles: Sequence[str]) -> None:
        """
        Garante que o usuário autenticado tenha um dos perfis permitidos.
        """
        AuthService.require_auth()
        user = AuthService.get_current_user()
        if not user or user.get("role") not in allowed_roles:
            st.error("Você não tem permissão para acessar esta funcionalidade.")
            st.stop()


def ensure_default_admin() -> None:
    """
    Garante a existência de um usuário admin padrão.
    Executado na inicialização da aplicação.
    """
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin:
            admin = AuthService.create_user(
                db=db,
                username="admin",
                name="Administrador",
                password="admin123",
                role="admin",
            )
            print(
                "Usuário admin criado com sucesso: "
                f"username=admin, senha=admin123 (altere em produção)"
            )
    finally:
        db.close()

