"""
Serviço de horóscopo: busca texto na internet e opcionalmente resume com IA.
Exibe o resumo do horóscopo do dia na tela inicial, atualizado diariamente.
"""
import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from urllib.error import URLError
from urllib.request import Request, urlopen


# Map signo (valor no banco) para slug em URLs comuns de horóscopo
SIGN_TO_SLUG = {
    "aries": "aries",
    "touro": "touro",
    "gemeos": "gemeos",
    "cancer": "cancer",
    "leao": "leao",
    "virgem": "virgem",
    "libra": "libra",
    "escorpiao": "escorpiao",
    "sagitario": "sagitario",
    "capricornio": "capricornio",
    "aquario": "aquario",
    "peixes": "peixes",
}

SIGN_DISPLAY = {
    "aries": "Áries",
    "touro": "Touro",
    "gemeos": "Gêmeos",
    "cancer": "Câncer",
    "leao": "Leão",
    "virgem": "Virgem",
    "libra": "Libra",
    "escorpiao": "Escorpião",
    "sagitario": "Sagitário",
    "capricornio": "Capricórnio",
    "aquario": "Aquário",
    "peixes": "Peixes",
}


def fetch_horoscope_from_web(signo: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca o horóscopo do dia na internet para o signo.
    Retorna (texto_bruto, url_fonte) ou (None, None) se falhar.
    """
    slug = SIGN_TO_SLUG.get((signo or "").lower())
    if not slug:
        return (None, None)
    urls = [
        ("https://www.horoscopovirtual.com.br/horoscopo/{slug}".format(slug=slug), "horoscopovirtual.com.br"),
        ("https://www.uol.com.br/astro/horoscopo/{slug}/dia/".format(slug=slug), "uol.com.br/astro"),
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for url, source_label in urls:
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            text = _extract_text_from_html(html)
            if text and len(text.strip()) > 50:
                return (text.strip(), source_label)
        except (URLError, OSError, Exception):
            continue
    return (None, None)


def _extract_text_from_html(html: str) -> str:
    """Remove tags HTML e extrai texto legível."""
    # Remove script e style
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode entidades comuns
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _call_ai(client, provider: str, model: str, prompt: str, max_tokens: int = 500) -> Optional[str]:
    """Chama a IA com o prompt e retorna o texto gerado."""
    try:
        if provider == "openai":
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=max_tokens,
            )
            return (r.choices[0].message.content or "").strip()
        if provider == "gemini":
            r = client.generate_content(prompt)
            return (r.text or "").strip()
        if provider == "groq":
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=max_tokens,
            )
            return (r.choices[0].message.content or "").strip()
        if provider == "ollama":
            r = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.5, "num_predict": max_tokens},
            )
            return (r.get("message", {}).get("content") or "").strip()
    except Exception:
        pass
    return None


def get_horoscope_for_user(db: Session, user_id: int, signo: Optional[str]) -> dict:
    """
    Retorna o horóscopo para exibir na tela inicial.
    Retorno: {"summary": str, "source": str | None}.
    - summary: resumo (IA ou trecho) do horóscopo do dia, atualizado diariamente.
    - source: rótulo da fonte para exibir em texto pequeno.
    """
    if not signo or not signo.strip():
        return {"summary": "", "source": None}

    signo = signo.strip().lower()
    raw, source_label = fetch_horoscope_from_web(signo)
    sign_name = SIGN_DISPLAY.get(signo, signo)

    if not raw:
        msg = f"**Horóscopo – {sign_name}**\n\nNão foi possível buscar a previsão do dia. Tente novamente mais tarde."
        return {"summary": msg, "source": None}

    raw = raw.strip()

    # Resumo principal (IA ou trecho)
    summary_text = None
    try:
        from config.ai_config import AIConfigManager
        from services.ai_service import AIService

        if AIConfigManager.is_configured(db):
            ai = AIService(db)
            client, err = ai._get_client()
            if not err and client:
                config = ai.config
                provider = config["provider"]
                model = config.get("model", "")
                prompt = (
                    f"Resuma em 2 a 4 frases curtas e motivadoras o horóscopo do dia (ou da semana) "
                    f"para o signo de {sign_name}. Use tom positivo e pessoal. "
                    f"Texto de referência:\n\n{raw[:2500]}"
                )
                summary_text = _call_ai(client, provider, model, prompt, max_tokens=300)
    except Exception:
        pass

    if summary_text:
        summary = f"**Horóscopo – {sign_name}**\n\n{summary_text}"
    else:
        snippet = raw[:400].strip()
        if len(raw) > 400:
            snippet += "..."
        summary = f"**Horóscopo – {sign_name}**\n\n{snippet}"

    return {"summary": summary, "source": source_label}
