"""
Estoque e vendas de acessórios por preço (tabelas separadas do PDV principal).
Controle: quantidade de peças por valor (ex.: 10 peças de 19,99).
"""
from sqlalchemy import Boolean, Column, Date, Float, Integer


from config.database import Base


class AccessoryStock(Base):
    """
    Estoque atual de acessórios por preço: uma linha por valor (preco, quantidade).
    """

    __tablename__ = "accessory_stock"

    id = Column(Integer, primary_key=True, index=True)
    preco = Column(Float, nullable=False, unique=True, index=True)
    quantidade = Column(Float, nullable=False, default=0.0)


class AccessorySale(Base):
    """
    Histórico de vendas de acessórios: data, preço, quantidade e flag de repasse (50%) ao fornecedor.
    """

    __tablename__ = "accessory_sales"

    id = Column(Integer, primary_key=True, index=True)
    data_venda = Column(Date, nullable=False, index=True)
    preco = Column(Float, nullable=False)
    quantidade = Column(Float, nullable=False, default=0.0)
    repasse_feito = Column(Boolean, nullable=False, default=False)


class AccessoryStockEntry(Base):
    """
    Histórico de entradas de estoque de acessórios: data da inclusão, preço e quantidade.
    """

    __tablename__ = "accessory_stock_entries"

    id = Column(Integer, primary_key=True, index=True)
    data_entrada = Column(Date, nullable=False, index=True)
    preco = Column(Float, nullable=False)
    quantidade = Column(Float, nullable=False, default=0.0)
