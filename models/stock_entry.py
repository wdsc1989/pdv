"""
Entrada de estoque: registro de cada entrada por produto para acompanhamento por período.
"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from config.database import Base


class StockEntry(Base):
    """
    Registro de entrada de estoque para um produto (data, quantidade, observação).
    """

    __tablename__ = "stock_entries"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=0.0)
    data_entrada = Column(Date, nullable=False, index=True)
    observacao = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    product = relationship("Product", backref="stock_entries")
