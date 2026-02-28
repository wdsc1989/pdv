"""
Modelo de configuração de IA para o agente de relatórios.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from config.database import Base


class AIConfig(Base):
    """
    Configuração de IA do sistema (provedor, API key, modelo).
    """

    __tablename__ = "ai_config"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False)  # openai, gemini, ollama, groq
    api_key = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    base_url = Column(String(500), nullable=True)  # Ollama ou APIs customizadas
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AIConfig(provider='{self.provider}', enabled={self.enabled})>"
