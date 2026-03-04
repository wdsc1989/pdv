from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String

from config.database import Base


class PersonalAgenda(Base):
    """
    Agenda pessoal de compromissos para usuários administradores.
    Os registros podem ser usados pelo Agente de Relatórios para gerar alertas no resumo diário.
    """

    __tablename__ = "personal_agenda"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    titulo = Column(String(200), nullable=False)
    descricao = Column(String(500), nullable=True)
    data = Column(Date, nullable=False, default=date.today)
    hora = Column(String(5), nullable=True)  # HH:MM
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

