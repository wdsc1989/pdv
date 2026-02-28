"""
Serviço de horóscopo: busca texto na internet e opcionalmente resume com IA.
No expander, exibe apenas a parte relacionada a trabalho, formatada pela IA, com período.
"""
import re
from datetime import date
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session


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


def fetch_horoscope_from_web(signo: str) -> Optional[str]:
    """
    Busca o horóscopo do dia na internet para o signo.
    Retorna texto bruto ou None se falhar.
    """
    slug = SIGN_TO_SLUG.get((signo or "").lower())
    if not slug:
        return None
    urls = [
        f"https://www.horoscopovirtual.com.br/horoscopo/{slug}",
        f"https://www.uol.com.br/astro/horoscopo/{slug}/dia/",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for url in urls:
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            text = _extract_text_from_html(html)
            if text and len(text.strip()) > 50:
                return text.strip()
        except (URLError, OSError, Exception):
            continue
    return None


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


def _build_work_horoscope_expander(
    db: Session, raw: str, sign_name: str, period_label: str
) -> Optional[str]:
    """
    Usa a IA para extrair e formatar apenas a parte de TRABALHO do horóscopo.
    Retorna texto para o expander (período + conteúdo trabalho) ou None.
    """
    from config.ai_config import AIConfigManager
    from services.ai_service import AIService

    if not AIConfigManager.is_configured(db):
        return None
    ai = AIService(db)
    client, err = ai._get_client()
    if err or not client:
        return None
    config = ai.config
    provider = config["provider"]
    model = config.get("model", "")
    prompt = (
        f"Do texto abaixo do horóscopo do signo de {sign_name}, extraia e reformule APENAS o que for "
        "relacionado a TRABALHO, CARREIRA, PROFISSIONAL ou NEGÓCIOS. Formate em português claro e objetivo, "
        "em 2 a 5 frases, com boa legibilidade. Se não houver menção explícita a trabalho, resuma em 1 ou 2 "
        "frases o que o horóscopo sugere para o âmbito profissional com base no tom geral. Não invente informações. "
        "Use markdown leve (negrito para ênfase).\n\nTexto:\n" + (raw[:3000] or "")
    )
    work_text = _call_ai(client, provider, model, prompt, max_tokens=400)
    if not work_text:
        return None
    return f"{period_label}\n\n{work_text}"


def get_horoscope_for_user(db: Session, user_id: int, signo: Optional[str]) -> dict:
    """
    Retorna o horóscopo para exibir na tela inicial.
    Retorno: {"summary": str, "full": str | None}.
    - summary: resumo (IA ou trecho) para exibir sempre.
    - full: no expander, apenas horóscopo focado em TRABALHO, formatado pela IA, com período.
    """
    if not signo or not signo.strip():
        return {"summary": "", "full": None}

    signo = signo.strip().lower()
    raw = fetch_horoscope_from_web(signo)
    sign_name = SIGN_DISPLAY.get(signo, signo)

    if not raw:
        msg = f"**Horóscopo – {sign_name}**\n\nNão foi possível buscar a previsão do dia. Tente novamente mais tarde."
        return {"summary": msg, "full": None}

    raw = raw.strip()
    period_label = f"**Período:** dia {date.today().strftime('%d/%m/%Y')}"

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

    # Expander: só horóscopo de trabalho, formatado pela IA, com período
    full = _build_work_horoscope_expander(db, raw, sign_name, period_label)
    if not full:
        full = (
            f"{period_label}\n\n"
            "*Para ver a previsão focada em **trabalho** (formatada pela IA), configure a IA em Administração.*"
        )

    return {"summary": summary, "full": full}
