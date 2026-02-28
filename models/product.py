from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from config.database import Base


class Product(Base):
    """
    Produtos da loja de roupas.
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    # Texto livre mantido para compatibilidade e exibição
    categoria = Column(String(100), nullable=True)
    marca = Column(String(100), nullable=True)
    preco_custo = Column(Float, nullable=False, default=0.0)
    preco_venda = Column(Float, nullable=False, default=0.0)
    estoque_atual = Column(Float, nullable=False, default=0.0)
    estoque_minimo = Column(Float, nullable=True)
    imagem_path = Column(String(255), nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    categoria_id = Column(Integer, ForeignKey("product_categories.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    categoria_rel = relationship("ProductCategory", lazy="joined")
