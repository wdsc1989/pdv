"""
Agente de cadastro de compromissos na agenda em linguagem natural.
Interpreta pedidos, pede esclarecimentos quando faltam dados e confirma antes de inserir.
"""
import json
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config.prompt_config import (
    KEY_AGENDA_AGENT_PARSE,
    PromptConfigManager,
    safe_substitute_prompt,
)
from models.personal_agenda import PersonalAgenda
from services.ai_service import AIService


def _hoje() -> str:
    return date.today().strftime("%d/%m/%Y")


def _parse_ai_response(text: str) -> Dict[str, Any]:
    """Extrai JSON da resposta da IA."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return json.loads(text)


class AgendaAgentService:
    """
    Agente que interpreta linguagem natural para cadastrar compromissos na agenda.
    Retorna need_info (perguntas), confirm (resumo para confirmar) ou error.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService(db)

    def is_available(self) -> bool:
        return self.ai_service.is_available()

    def parse_request(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Interpreta a mensagem e retorna:
        - status: "need_info" | "confirm" | "error"
        - message: texto para exibir
        - record: dict com titulo, descricao, data, hora (quando status == "confirm")
        """
        data_hoje = _hoje()
        history_block = ""
        if conversation_history:
            recent = conversation_history[-10:]
            lines = []
            for m in recent:
                role = (m.get("role") or "user").strip().lower()
                content = (m.get("content") or "").strip()
                if not content:
                    continue
                label = "Usuário" if role == "user" else "Assistente"
                lines.append(f"{label}: {content[:500]}{'...' if len(content) > 500 else ''}")
            if lines:
                history_block = "\n\n**Histórico recente (use para manter o contexto):**\n" + "\n".join(lines) + "\n\n"

        template = PromptConfigManager.get_or_default(
            self.db,
            KEY_AGENDA_AGENT_PARSE,
            PromptConfigManager.get_default(KEY_AGENDA_AGENT_PARSE),
        )
        prompt = safe_substitute_prompt(
            template,
            data_hoje=data_hoje,
            history_block=history_block,
            message=message,
        )

        if not self.ai_service.is_available():
            return {
                "status": "error",
                "message": "Configure a IA em Administração > Configuração de IA para usar o agente de agenda.",
                "record": None,
            }

        try:
            client, error = self.ai_service._get_client()
            if error:
                return {"status": "error", "message": error, "record": None}
            config = self.ai_service.config
            provider = config["provider"]
            model = config.get("model", "")
            result_text = ""
            if provider == "openai":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result_text = r.choices[0].message.content or ""
            elif provider == "gemini":
                r = client.generate_content(prompt)
                result_text = r.text or ""
            elif provider == "groq":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result_text = r.choices[0].message.content or ""
            elif provider == "ollama":
                r = client.chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.2})
                result_text = r.get("message", {}).get("content", "") or ""
            else:
                return {"status": "error", "message": f"Provedor {provider} não suportado.", "record": None}

            parsed = _parse_ai_response(result_text)
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Erro ao interpretar resposta: {str(e)}", "record": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "record": None}

        self._apply_conversation_context_fallback(parsed, message, conversation_history)

        titulo = (parsed.get("titulo") or "").strip() or None
        descricao = (parsed.get("descricao") or "").strip() or None
        data_str = parsed.get("data")
        hora = (parsed.get("hora") or "").strip() or None
        if hora and len(hora) >= 4 and ":" not in hora:
            hora = hora[:2] + ":" + hora[2:4]
        elif hora and len(hora) != 5:
            hora = None

        missing = list(parsed.get("missing") or [])
        questions = list(parsed.get("clarification_questions") or [])

        if not titulo:
            if "titulo" not in missing:
                missing.append("titulo")
            if not any("título" in (q or "").lower() or "titulo" in (q or "").lower() for q in questions):
                questions.append("Qual o título do compromisso? (ex.: Reunião, Dentista)")
        if not data_str:
            if "data" not in missing:
                missing.append("data")
            if not any("data" in (q or "").lower() or "quando" in (q or "").lower() for q in questions):
                questions.append("Para qual data? (ex.: amanhã, dia 15/03)")

        if missing and questions:
            return {
                "status": "need_info",
                "message": "**Preciso de mais informações:**\n\n" + "\n".join(f"- {q}" for q in questions),
                "record": None,
            }

        try:
            if isinstance(data_str, date):
                data_compromisso = data_str
            else:
                s = str(data_str).strip()
                if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                    data_compromisso = date.fromisoformat(s[:10])
                elif "/" in s and len(s) >= 8:
                    parts = s.split("/")
                    if len(parts) == 3:
                        d, m, a = int(parts[0]), int(parts[1]), int(parts[2])
                        data_compromisso = date(a, m, d)
                    else:
                        data_compromisso = date.fromisoformat(s[:10])
                else:
                    data_compromisso = date.fromisoformat(s[:10])
        except (ValueError, TypeError):
            return {
                "status": "need_info",
                "message": "**Data inválida.** Use formato DD/MM/AAAA ou diga 'amanhã', 'hoje', 'dia 15'.",
                "record": None,
            }

        record = {
            "titulo": titulo,
            "descricao": descricao,
            "data": data_compromisso.isoformat(),
            "hora": hora,
        }
        data_fmt = data_compromisso.strftime("%d/%m/%Y")
        hora_txt = f" às {hora}" if hora else ""
        msg = f"**Compromisso:** {titulo} — {data_fmt}{hora_txt}\n\n**Confirma o cadastro?**"
        return {"status": "confirm", "message": msg, "record": record}

    def _apply_conversation_context_fallback(
        self,
        parsed: Dict[str, Any],
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> None:
        """Se a última mensagem do assistente foi pergunta e o usuário respondeu, preenche o campo correspondente."""
        if not conversation_history or len(conversation_history) < 1:
            return
        last = conversation_history[-1]
        if (last.get("role") or "").strip().lower() != "assistant":
            return
        last_content = (last.get("content") or "").lower()
        user_reply = (message or "").strip()
        if not user_reply or len(user_reply) > 300:
            return
        if "título" in last_content or "titulo" in last_content:
            parsed["titulo"] = user_reply
            parsed["missing"] = [m for m in (parsed.get("missing") or []) if m != "titulo"]
            parsed["clarification_questions"] = [q for q in (parsed.get("clarification_questions") or []) if "título" not in (q or "").lower() and "titulo" not in (q or "").lower()]
        if "qual data" in last_content or "para qual data" in last_content:
            if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", user_reply.replace("-", "/")):
                parts = user_reply.replace("-", "/").split("/")
                parsed["data"] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            elif "amanhã" in user_reply.lower() or "amanha" in user_reply.lower():
                d = date.today() + timedelta(days=1)
                parsed["data"] = d.isoformat()
            elif "hoje" in user_reply.lower():
                parsed["data"] = date.today().isoformat()
            if parsed.get("data"):
                parsed["missing"] = [m for m in (parsed.get("missing") or []) if m != "data"]
                parsed["clarification_questions"] = [q for q in (parsed.get("clarification_questions") or []) if "data" not in (q or "").lower()]

    def execute_insert(self, db: Session, record: Dict[str, Any], user_id: Optional[int]) -> Dict[str, Any]:
        """Insere um compromisso. Retorna { success: bool, message: str }."""
        if not record or not record.get("titulo"):
            return {"success": False, "message": "Título obrigatório."}
        try:
            data_str = record.get("data")
            if isinstance(data_str, date):
                data_comp = data_str
            else:
                data_comp = date.fromisoformat(str(data_str).strip()[:10])
            obj = PersonalAgenda(
                user_id=user_id,
                titulo=(record.get("titulo") or "").strip(),
                descricao=(record.get("descricao") or "").strip() or None,
                data=data_comp,
                hora=(record.get("hora") or "").strip() or None,
            )
            db.add(obj)
            db.commit()
            return {"success": True, "message": "Compromisso registrado na agenda."}
        except Exception as e:
            db.rollback()
            return {"success": False, "message": str(e)}
