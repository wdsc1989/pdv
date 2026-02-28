from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from config.database import Base


class User(Base):
    """
    Usuários do sistema PDV.
    Perfis suportados (role):
    - admin
    - gerente
    - vendedor
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="vendedor")
    active = Column(Boolean, nullable=False, default=True)
    signo = Column(String(20), nullable=True)  # Signo para horóscopo: aries, touro, gemeos, etc.
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
