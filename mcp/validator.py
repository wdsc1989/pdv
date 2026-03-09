"""
Serviço MCP para validação de dados no PDV.
Valida por entidade: contas_pagar, contas_receber, agenda.
Quando há erros, pode usar IA para gerar mensagem clara (message_ia).
"""
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from mcp.schemas import ValidateResponse


class MCPValidator:
    """
    Valida dados antes de salvar (INSERT/UPDATE/DELETE).
    Com IA configurada, gera message_ia em linguagem natural quando há erros (clareza).
    """

    def __init__(self, db: Session):
        self.db = db
        self._ai_service = None

    def _get_ai_service(self):
        """AIService lazy (mesma config dos agentes)."""
        if self._ai_service is None:
            from services.ai_service import AIService
            self._ai_service = AIService(self.db)
        return self._ai_service

    def _message_errors_with_ai(
        self,
        errors: List[str],
        warnings: List[str],
        action: str,
        entity: str,
    ) -> Optional[str]:
        """Gera uma mensagem em linguagem natural explicando os erros (para o usuário)."""
        ai = self._get_ai_service()
        if not ai.is_available() or not errors:
            return None
        prompt = f"""Lista de erros de validação ({entity}, ação {action}):
Erros: {errors}
Avisos: {warnings}

Escreva UMA frase curta e amigável em português explicando o que o usuário precisa corrigir. Não repita a lista; resuma. Ex.: "Faltam o valor e a data de vencimento." ou "O valor precisa ser maior que zero e a data deve estar no formato correto."
Responda só com essa frase, sem aspas nem prefixos."""
        content, _ = ai.complete(prompt, temperature=0.2, max_tokens=120, json_mode=False)
        if not content or not content.strip():
            return None
        return content.strip()

    def validate(
        self, data: Dict[str, Any], action: str, entity: str
    ) -> ValidateResponse:
        """
        Valida dados conforme action e entity.
        Se houver erros e IA disponível, preenche message_ia com explicação clara.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if entity in ("contas_pagar", "contas_receber"):
            errors, warnings = self._validate_contas(data, action, entity)
        elif entity == "agenda":
            errors, warnings = self._validate_agenda(data, action)
        else:
            errors, warnings = self._validate_contas(
                data, action, "contas_pagar"
            )

        message_ia: Optional[str] = None
        if not errors:
            message_ia = None
        else:
            message_ia = self._message_errors_with_ai(
                errors, warnings, action, entity
            )

        return ValidateResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            message_ia=message_ia,
        )

    def _validate_contas(
        self, data: Dict[str, Any], action: str, entity: str
    ) -> Tuple[List[str], List[str]]:
        """Valida dados de contas a pagar/receber."""
        errors: List[str] = []
        warnings: List[str] = []

        if action == "INSERT":
            name_field = "fornecedor" if entity == "contas_pagar" else "cliente"
            if name_field not in data or not str(data.get(name_field, "")).strip():
                errors.append(f"Campo obrigatório: {name_field}")
            elif len(str(data[name_field]).strip()) > 200:
                errors.append(f"{name_field} deve ter no máximo 200 caracteres")

            if "valor" not in data:
                errors.append("Campo obrigatório: valor")
            else:
                try:
                    v = float(data["valor"])
                    if v <= 0:
                        errors.append("valor deve ser maior que zero")
                except (ValueError, TypeError):
                    errors.append("valor deve ser um número válido")

            if "data_vencimento" not in data:
                errors.append("Campo obrigatório: data_vencimento")
            else:
                try:
                    d = data["data_vencimento"]
                    if isinstance(d, str):
                        d = date.fromisoformat(d)
                    if d < date.today():
                        warnings.append("data_vencimento está no passado")
                except (ValueError, TypeError):
                    errors.append(
                        "data_vencimento deve ser uma data válida (YYYY-MM-DD)"
                    )

            if "descricao" in data and data["descricao"]:
                if len(str(data["descricao"])) > 255:
                    errors.append("descricao deve ter no máximo 255 caracteres")
            if "observacao" in data and data["observacao"]:
                if len(str(data["observacao"])) > 255:
                    errors.append("observacao deve ter no máximo 255 caracteres")

        elif action == "UPDATE":
            if data.get("id") is None and not data.get("fornecedor") and not data.get("cliente"):
                errors.append("Informe o id da conta ou o nome (fornecedor/cliente) para dar baixa")
            if "id" in data and data["id"]:
                try:
                    if int(data["id"]) <= 0:
                        errors.append("id deve ser um número positivo")
                except (ValueError, TypeError):
                    errors.append("id deve ser um número inteiro válido")

        elif action == "DELETE":
            if "id" not in data or data.get("id") is None:
                errors.append("Campo obrigatório: id")
            else:
                try:
                    if int(data["id"]) <= 0:
                        errors.append("id deve ser um número positivo")
                except (ValueError, TypeError):
                    errors.append("id deve ser um número inteiro válido")

        return errors, warnings

    def _validate_agenda(
        self, data: Dict[str, Any], action: str
    ) -> Tuple[List[str], List[str]]:
        """Valida dados de agenda."""
        errors: List[str] = []
        warnings: List[str] = []

        if action == "INSERT":
            if "titulo" not in data or not str(data.get("titulo", "")).strip():
                errors.append("Campo obrigatório: titulo")
            elif len(str(data["titulo"]).strip()) > 200:
                errors.append("titulo deve ter no máximo 200 caracteres")

            if "data" not in data:
                errors.append("Campo obrigatório: data")
            else:
                try:
                    d = data["data"]
                    if isinstance(d, str):
                        d = date.fromisoformat(d)
                    if d < date.today():
                        warnings.append("data está no passado")
                except (ValueError, TypeError):
                    errors.append("data deve ser uma data válida (YYYY-MM-DD)")

            if "descricao" in data and data["descricao"]:
                if len(str(data["descricao"])) > 500:
                    errors.append("descricao deve ter no máximo 500 caracteres")
            if "hora" in data and data["hora"]:
                import re
                if not re.match(r"^\d{1,2}:\d{2}$", str(data["hora"])):
                    errors.append("hora deve estar no formato HH:MM")

        return errors, warnings
