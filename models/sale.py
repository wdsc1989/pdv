from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from config.database import Base


class Sale(Base):
    """
    Venda (cabeçalho) vinculada a uma sessão de caixa.
    """

    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    cash_session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=False)
    data_venda = Column(Date, nullable=False)
    total_vendido = Column(Float, nullable=False, default=0.0)
    total_lucro = Column(Float, nullable=False, default=0.0)
    total_pecas = Column(Integer, nullable=False, default=0)
    tipo_pagamento = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="concluida")  # concluida | cancelada
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    cash_session = relationship("CashSession")
    itens = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    """
    Itens de venda.
    """

    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantidade = Column(Float, nullable=False, default=1.0)
    preco_unitario = Column(Float, nullable=False, default=0.0)
    preco_custo_unitario = Column(Float, nullable=False, default=0.0)
    subtotal = Column(Float, nullable=False, default=0.0)
    lucro_item = Column(Float, nullable=False, default=0.0)

    sale = relationship("Sale", back_populates="itens")
