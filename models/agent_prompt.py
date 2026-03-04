"""
Modelo para armazenar prompts editáveis do agente de relatórios (e outros agentes).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from config.database import Base


class AgentPrompt(Base):
    """
    Prompt configurável por chave (ex.: report_agent.analyze_query).
    O valor é o texto do template com placeholders.
    """

    __tablename__ = "agent_prompts"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(120), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AgentPrompt(key='{self.key}')>"
