from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from config.database import Base


class CashSession(Base):
    """
    Sessões de caixa (abertura/fechamento).
    Apenas uma sessão com status 'aberta' deve existir por vez.
    """

    __tablename__ = "cash_sessions"

    id = Column(Integer, primary_key=True, index=True)
    data_abertura = Column(DateTime, nullable=False, default=datetime.utcnow)
    data_fechamento = Column(DateTime, nullable=True)
    valor_abertura = Column(Float, nullable=False, default=0.0)
    valor_fechamento = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="aberta")  # aberta / fechada
    observacao = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
