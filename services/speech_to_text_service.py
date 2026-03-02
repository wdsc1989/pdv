"""
Transcrição de áudio para texto (speech-to-text) para uso nos agentes.
Usa OpenAI Whisper quando a API OpenAI está configurada.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from config.ai_config import AIConfigManager


# Formatos aceitos pelo Whisper
WHISPER_ACCEPT = ("mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm")


def get_openai_api_key(db: Session) -> Optional[str]:
    """Retorna a API key da OpenAI se estiver configurada (provedor openai no banco ou fixo)."""
    config = AIConfigManager.get_config_by_provider(db, "openai")
    if config and getattr(config, "api_key", None):
        key = (config.api_key or "").strip()
        if key:
            return key
    fixed = AIConfigManager._get_fixed_config()
    if fixed and fixed.get("provider") == "openai":
        key = (fixed.get("api_key") or "").strip()
        if key:
            return key
    return None


def transcribe_audio(
    db: Session, audio_bytes: bytes, filename: str = "audio.mp3"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcreve áudio para texto usando OpenAI Whisper.
    Retorna (texto_transcrito, erro). Se sucesso, erro é None. Se falha, texto é None.
    """
    api_key = get_openai_api_key(db)
    if not api_key:
        return None, "Configure a API OpenAI em Administração > Configuração de IA para usar áudio (transcrição Whisper)."

    ext = (filename or "").split(".")[-1].lower()
    if ext not in WHISPER_ACCEPT:
        return None, f"Formato de áudio não suportado. Use: {', '.join(WHISPER_ACCEPT)}."

    try:
        from openai import OpenAI
    except ImportError:
        return None, "Biblioteca 'openai' não instalada. Execute: pip install openai"

    client = OpenAI(api_key=api_key)
    try:
        import io
        file_like = io.BytesIO(audio_bytes)
        file_like.name = filename or "audio.mp3"
        r = client.audio.transcriptions.create(
            model="whisper-1",
            file=file_like,
            language="pt",
        )
        text = (r.text or "").strip()
        if not text:
            return None, "Áudio não pôde ser transcrito (vazio ou inaudível)."
        return text, None
    except Exception as e:
        return None, str(e)
