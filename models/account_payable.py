from datetime import datetime, date

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String

from config.database import Base


class AccountPayable(Base):
    """
    Contas a pagar.
    """

    __tablename__ = "accounts_payable"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    fornecedor = Column(String(200), nullable=False)
    descricao = Column(String(255), nullable=True)
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(Date, nullable=True)
    valor = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="aberta")  # aberta / paga / atrasada
    observacao = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def update_status(self):
        """
        Atualiza o status com base em data_pagamento e data_vencimento.
        """
        hoje = date.today()
        if self.data_pagamento:
            self.status = "paga"
        else:
            if self.data_vencimento < hoje:
                self.status = "atrasada"
            else:
                self.status = "aberta"
