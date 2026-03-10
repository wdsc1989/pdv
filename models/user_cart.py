"""
Carrinho de seleção de produtos por usuário (página Buscar produto).
Persiste quantidades escolhidas para manter ao refazer login.
"""
from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from config.database import Base


class UserCartItem(Base):
    """
    Item do carrinho do usuário na página de seleção de produtos.
    Um registro por (user_id, product_id) com quantidade.
    """

    __tablename__ = "user_cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_cart_user_product"),)

    user = relationship("User", backref="cart_items")
    product = relationship("Product", backref="user_cart_items")
