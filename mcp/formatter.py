"""
Serviço MCP para formatação de confirmações no PDV.
Suporta contas_pagar, contas_receber e agenda.
"""
from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from mcp.schemas import FormatConfirmationResponse


def _fmt_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return str(iso or "")
    try:
        d = date.fromisoformat(iso) if isinstance(iso, str) else iso
        return d.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(iso)


class MCPFormatter:
    """
    Formata mensagens de confirmação para contas e agenda.
    """

    def __init__(self, db: Session):
        self.db = db

    def format(
        self,
        action: str,
        data: Dict[str, Any],
        old_data: Optional[Dict[str, Any]] = None,
        entity: str = "contas_pagar",
    ) -> FormatConfirmationResponse:
        """
        Formata mensagem de confirmação conforme action e entity.
        """
        if entity == "agenda":
            return self._format_agenda(action, data, old_data)
        return self._format_contas(action, data, old_data, entity)

    def _format_contas(
        self,
        action: str,
        data: Dict[str, Any],
        old_data: Optional[Dict[str, Any]],
        entity: str,
    ) -> FormatConfirmationResponse:
        """Formata confirmação para contas a pagar/receber."""
        if action == "INSERT":
            return self._format_contas_insert(data, entity)
        if action == "UPDATE":
            return self._format_contas_update(data, old_data, entity)
        if action == "DELETE":
            return self._format_contas_delete(data)
        return FormatConfirmationResponse(
            message="Ação não suportada.",
            preview=data,
        )

    def _format_contas_insert(
        self, data: Dict[str, Any], entity: str
    ) -> FormatConfirmationResponse:
        label = "Conta a pagar" if entity == "contas_pagar" else "Conta a receber"
        name = data.get("fornecedor") or data.get("cliente") or "—"
        valor = data.get("valor", 0)
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            valor = 0
        data_venc = data.get("data_vencimento", "")
        desc = (data.get("descricao") or "").strip() or "—"
        message = f"**{label}:** {name} — {desc} — {_fmt_currency(valor)} — venc. {_fmt_date(data_venc)}\n\n**Confirma o cadastro?**"
        preview = {
            "fornecedor" if entity == "contas_pagar" else "cliente": name,
            "valor": valor,
            "data_vencimento": data_venc,
            "descricao": data.get("descricao"),
        }
        return FormatConfirmationResponse(message=message, preview=preview)

    def _format_contas_update(
        self,
        data: Dict[str, Any],
        old_data: Optional[Dict[str, Any]],
        entity: str,
    ) -> FormatConfirmationResponse:
        if data.get("subtype") == "baixa":
            name = data.get("fornecedor") or data.get("cliente") or "conta"
            message = f"**Dar baixa** na conta de {name}?\n\n**Confirma?**"
        else:
            message = f"**Atualizar conta** (ID {data.get('id', '?')})?\n\n**Confirma?**"
        return FormatConfirmationResponse(message=message, preview=data)

    def _format_contas_delete(self, data: Dict[str, Any]) -> FormatConfirmationResponse:
        message = f"**Excluir conta** ID {data.get('id', '?')}?\n\n**Confirma?**"
        return FormatConfirmationResponse(message=message, preview=data)

    def _format_agenda(
        self,
        action: str,
        data: Dict[str, Any],
        old_data: Optional[Dict[str, Any]],
    ) -> FormatConfirmationResponse:
        """Formata confirmação para agenda."""
        if action != "INSERT":
            return FormatConfirmationResponse(
                message="Ação não suportada para agenda.",
                preview=data,
            )
        titulo = (data.get("titulo") or "").strip() or "Compromisso"
        data_str = data.get("data", "")
        hora = (data.get("hora") or "").strip()
        desc = (data.get("descricao") or "").strip()
        message = f"**Compromisso:** {titulo}\n**Data:** {_fmt_date(data_str)}"
        if hora:
            message += f"\n**Hora:** {hora}"
        if desc:
            message += f"\n**Descrição:** {desc}"
        message += "\n\n**Confirma o cadastro?**"
        return FormatConfirmationResponse(
            message=message,
            preview={"titulo": titulo, "data": data_str, "hora": data.get("hora"), "descricao": desc},
        )
