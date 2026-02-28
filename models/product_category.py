from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from config.database import Base


class ProductCategory(Base):
    """
    Categoria de produto para organização do catálogo.
    """

    __tablename__ = "product_categories"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False, index=True)
    descricao = Column(String(255), nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

