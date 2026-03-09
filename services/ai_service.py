"""
Serviço de IA para o agente de relatórios (análise de pergunta e formatação de resposta).
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from config.ai_config import AIConfigManager


class AIService:
    """
    Serviço mínimo para chamadas à API de IA (OpenAI, Gemini, Groq, Ollama).
    Usado pelo agente de relatórios para analyze_query e format_response.
    """

    def __init__(self, db: Session):
        self.db = db
        self.config = AIConfigManager.get_config_dict(db)
        self._client = None

    def is_available(self) -> bool:
        """Verifica se a IA está configurada e utilizável."""
        return AIConfigManager.is_configured(self.db) and self.config is not None

    def _get_client(self):
        """
        Retorna o cliente da API de IA conforme o provedor configurado.
        Retorna (client, error_message); error_message é None em caso de sucesso.
        Para Gemini, client é um GenerativeModel (usa generate_content).
        """
        if not self.config:
            return None, "Configuração de IA não encontrada"

        if self._client is not None:
            return self._client, None

        provider = self.config["provider"]
        api_key = (self.config.get("api_key") or "").strip()

        if provider != "ollama" and not api_key:
            return None, f"Chave de API não configurada para {provider}"

        try:
            if provider == "openai":
                try:
                    from openai import OpenAI
                except ImportError:
                    return None, "Biblioteca 'openai' não instalada. Execute: pip install openai"
                self._client = OpenAI(api_key=api_key)
                return self._client, None

            if provider == "gemini":
                try:
                    import google.generativeai as genai
                except ImportError:
                    return None, "Biblioteca 'google-generativeai' não instalada. Execute: pip install google-generativeai"
                genai.configure(api_key=api_key)
                model_name = self.config.get("model", "gemini-1.5-flash")
                self._client = genai.GenerativeModel(model_name)
                return self._client, None

            if provider == "ollama":
                try:
                    from openai import OpenAI
                except ImportError:
                    return None, "Biblioteca 'openai' não instalada. Execute: pip install openai"
                base_url = self.config.get("base_url", "http://localhost:11434") or "http://localhost:11434"
                if not base_url.rstrip("/").endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"
                self._client = OpenAI(api_key="ollama", base_url=base_url)
                return self._client, None

            if provider == "groq":
                try:
                    from groq import Groq
                except ImportError:
                    return None, "Biblioteca 'groq' não instalada. Execute: pip install groq"
                self._client = Groq(api_key=api_key)
                return self._client, None

            return None, f"Provedor '{provider}' não suportado"

        except Exception as e:
            return None, f"Erro ao inicializar cliente de IA ({provider}): {str(e)}"

    def test_connection(self):
        """
        Testa a conexão com a API (chamada mínima).
        Retorna (success: bool, message: str).
        """
        client, error = self._get_client()
        if error:
            return False, error
        provider = self.config["provider"]
        model = self.config.get("model", "")
        try:
            if provider == "openai":
                client.chat.completions.create(
                    model=model or "gpt-4o-mini",
                    messages=[{"role": "user", "content": "Diga apenas OK"}],
                    max_tokens=5,
                )
            elif provider == "gemini":
                client.generate_content("Diga apenas OK")
            elif provider == "groq":
                client.chat.completions.create(
                    model=model or "llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": "Diga apenas OK"}],
                    max_tokens=5,
                )
            elif provider == "ollama":
                client.chat(
                    model=model or "llama3.2",
                    messages=[{"role": "user", "content": "Diga apenas OK"}],
                    options={"num_predict": 5},
                )
            else:
                return False, f"Provedor {provider} não suportado"
            return True, "Conexão com a API realizada com sucesso."
        except Exception as e:
            return False, str(e)

    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 300,
        json_mode: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Envia um prompt e retorna o texto da resposta.
        Retorna (content, error): em sucesso content é o texto e error é None;
        em falha content é None e error é a mensagem.
        Para json_mode=True, usa response_format onde suportado (OpenAI, Groq);
        para Gemini/Ollama o prompt já deve pedir JSON.
        """
        client, err = self._get_client()
        if err:
            return None, err
        if not self.config:
            return None, "Configuração de IA não encontrada"
        provider = self.config["provider"]
        model = self.config.get("model", "") or (
            "gpt-4o-mini" if provider == "openai"
            else "gemini-1.5-flash" if provider == "gemini"
            else "llama-3.3-70b-versatile" if provider == "groq"
            else "llama3.2"
        )
        try:
            if provider == "openai":
                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                r = client.chat.completions.create(**kwargs)
                content = (r.choices[0].message.content or "").strip()
                return (content or None, None)
            if provider == "gemini":
                r = client.generate_content(prompt)
                content = (r.text or "").strip()
                return (content or None, None)
            if provider == "groq":
                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                r = client.chat.completions.create(**kwargs)
                content = (r.choices[0].message.content or "").strip()
                return (content or None, None)
            if provider == "ollama":
                r = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": temperature, "num_predict": max_tokens},
                )
                content = (r.get("message", {}).get("content") or "").strip()
                return (content or None, None)
            return None, f"Provedor '{provider}' não suportado"
        except Exception as e:
            return None, str(e)
