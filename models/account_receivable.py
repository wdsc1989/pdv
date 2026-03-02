"""
Contas a receber (vendas fiado / clientes que devem).
"""
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, Integer, String

from config.database import Base


class AccountReceivable(Base):
    """
    Contas a receber: valores a receber de clientes (vendas fiado).
    """

    __tablename__ = "accounts_receivable"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    cliente = Column(String(200), nullable=False)
    descricao = Column(String(255), nullable=True)
    data_vencimento = Column(Date, nullable=False)
    data_recebimento = Column(Date, nullable=True)
    valor = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="aberta")  # aberta / recebida / atrasada
    observacao = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def update_status(self):
        """Atualiza o status com base em data_recebimento e data_vencimento."""
        hoje = date.today()
        if self.data_recebimento:
            self.status = "recebida"
        else:
            if self.data_vencimento < hoje:
                self.status = "atrasada"
            else:
                self.status = "aberta"
