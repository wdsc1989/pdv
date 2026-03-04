"""
Modelo genérico para histórico de chat dos agentes (por usuário e scope).
Uma única tabela para report_agent, accounts_agent, etc.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from config.database import Base


class AgentChatMessage(Base):
    """
    Uma mensagem de chat de qualquer agente (Relatórios, Contas, etc.).
    O campo scope identifica o agente; ordenação por created_at define a ordem da conversa.
    """

    __tablename__ = "agent_chat_memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scope = Column(String(50), nullable=False, index=True)  # "report_agent", "accounts_agent", etc.
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    extra_json = Column(Text, nullable=True)  # JSON: table_data (orient="split") ou {"records": [...]}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_agent_chat_memory_user_scope_created", "user_id", "scope", "created_at"),)

    def __repr__(self):
        return f"<AgentChatMessage(user_id={self.user_id}, scope='{self.scope}', role='{self.role}')>"
