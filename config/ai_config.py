"""
Configuração e gerenciamento de IA para o agente de relatórios.
"""
import os
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models.ai_config import AIConfig


class AIConfigManager:
    """
    Gerenciador de configurações de IA (provedor, API key, modelo).
    """

    DEFAULT_MODELS = {
        "openai": "gpt-4o",
        "gemini": "gemini-1.5-flash",
        "ollama": "llama3.2",
        "groq": "llama-3.3-70b-versatile",
    }

    DEFAULT_BASE_URLS = {
        "ollama": "http://localhost:11434",
    }

    FIXED_PROVIDER = os.getenv("AI_FIXED_PROVIDER", "openai")
    FIXED_MODEL = os.getenv("AI_FIXED_MODEL", DEFAULT_MODELS.get("openai", "gpt-4o"))
    FIXED_API_KEY = os.getenv("AI_FIXED_API_KEY", None)
    FIXED_CONFIG_ENABLED = os.getenv("AI_FIXED_CONFIG_ENABLED", "false").lower() == "true"

    @staticmethod
    def get_config(db: Session) -> Optional[AIConfig]:
        """Obtém a configuração de IA ativa."""
        return db.query(AIConfig).filter(AIConfig.enabled == True).first()

    @staticmethod
    def get_config_by_provider(db: Session, provider: str) -> Optional[AIConfig]:
        """Obtém configuração por provedor."""
        return db.query(AIConfig).filter(AIConfig.provider == provider).first()

    @staticmethod
    def save_config(
        db: Session,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: bool = True,
    ) -> AIConfig:
        """Salva ou atualiza configuração de IA."""
        if enabled:
            db.query(AIConfig).filter(AIConfig.enabled == True).update({"enabled": False})

        config = db.query(AIConfig).filter(AIConfig.provider == provider).first()

        if config:
            if api_key is not None:
                config.api_key = api_key
            if model is not None:
                config.model = model
            if base_url is not None:
                config.base_url = base_url
            config.enabled = enabled
        else:
            if model is None:
                model = AIConfigManager.DEFAULT_MODELS.get(provider)
            if base_url is None and provider in AIConfigManager.DEFAULT_BASE_URLS:
                base_url = AIConfigManager.DEFAULT_BASE_URLS[provider]
            config = AIConfig(
                provider=provider,
                api_key=api_key or "",
                model=model,
                base_url=base_url,
                enabled=enabled,
            )
            db.add(config)

        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def delete_config(db: Session, provider: str) -> bool:
        """Remove configuração de IA."""
        config = db.query(AIConfig).filter(AIConfig.provider == provider).first()
        if config:
            db.delete(config)
            db.commit()
            return True
        return False

    @staticmethod
    def get_all_configs(db: Session) -> list:
        """Obtém todas as configurações."""
        return db.query(AIConfig).all()

    @staticmethod
    def is_configured(db: Session) -> bool:
        """Verifica se há configuração de IA ativa (banco ou fixa)."""
        config = AIConfigManager.get_config(db)
        if config and config.api_key and config.enabled:
            return True
        return AIConfigManager._get_fixed_config() is not None

    @staticmethod
    def get_config_dict(db: Session) -> Optional[Dict[str, Any]]:
        """Retorna configuração ativa como dicionário."""
        config = AIConfigManager.get_config(db)
        if not config:
            return AIConfigManager._get_fixed_config()
        return {
            "provider": config.provider,
            "api_key": config.api_key,
            "model": config.model,
            "base_url": config.base_url,
            "enabled": config.enabled,
        }

    @staticmethod
    def _get_fixed_config() -> Optional[Dict[str, Any]]:
        """Fallback: configuração via variáveis de ambiente."""
        if not AIConfigManager.FIXED_CONFIG_ENABLED:
            return None
        api_key = (AIConfigManager.FIXED_API_KEY or "").strip()
        if not api_key:
            return None
        return {
            "provider": AIConfigManager.FIXED_PROVIDER,
            "api_key": api_key,
            "model": AIConfigManager.FIXED_MODEL,
            "base_url": AIConfigManager.DEFAULT_BASE_URLS.get(AIConfigManager.FIXED_PROVIDER),
            "enabled": True,
        }
