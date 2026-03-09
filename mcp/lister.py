"""
Serviço MCP para listagem de contas e agenda no PDV.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from mcp.schemas import ListResponse


class MCPLister:
    """
    Lista contas a pagar/receber e opcionalmente agenda com filtros.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_accounts(
        self,
        entity: str,
        data_inicial: Optional[date] = None,
        data_final: Optional[date] = None,
        status: Optional[str] = None,
    ) -> ListResponse:
        """
        Lista contas (contas_pagar ou contas_receber) com filtros.
        """
        if entity == "contas_pagar":
            from models.account_payable import AccountPayable
            q = self.db.query(AccountPayable)
            if data_inicial:
                q = q.filter(AccountPayable.data_vencimento >= data_inicial)
            if data_final:
                q = q.filter(AccountPayable.data_vencimento <= data_final)
            if status:
                q = q.filter(AccountPayable.status == status)
            rows = q.order_by(AccountPayable.data_vencimento.desc()).all()
            items = []
            total_valor = 0.0
            for r in rows:
                total_valor += float(r.valor)
                items.append({
                    "id": r.id,
                    "fornecedor": r.fornecedor,
                    "descricao": r.descricao,
                    "valor": float(r.valor),
                    "data_vencimento": r.data_vencimento.isoformat() if r.data_vencimento else None,
                    "data_pagamento": r.data_pagamento.isoformat() if r.data_pagamento else None,
                    "status": r.status,
                    "observacao": r.observacao,
                })
            return ListResponse(
                items=items,
                total=len(items),
                total_valor=total_valor,
            )
        elif entity == "contas_receber":
            from models.account_receivable import AccountReceivable
            q = self.db.query(AccountReceivable)
            if data_inicial:
                q = q.filter(AccountReceivable.data_vencimento >= data_inicial)
            if data_final:
                q = q.filter(AccountReceivable.data_vencimento <= data_final)
            if status:
                q = q.filter(AccountReceivable.status == status)
            rows = q.order_by(AccountReceivable.data_vencimento.desc()).all()
            items = []
            total_valor = 0.0
            for r in rows:
                total_valor += float(r.valor)
                items.append({
                    "id": r.id,
                    "cliente": r.cliente,
                    "descricao": r.descricao,
                    "valor": float(r.valor),
                    "data_vencimento": r.data_vencimento.isoformat() if r.data_vencimento else None,
                    "data_recebimento": r.data_recebimento.isoformat() if r.data_recebimento else None,
                    "status": r.status,
                    "observacao": r.observacao,
                })
            return ListResponse(
                items=items,
                total=len(items),
                total_valor=total_valor,
            )
        return ListResponse(items=[], total=0, total_valor=None)

    def list_agenda(
        self,
        user_id: Optional[int] = None,
        data_inicial: Optional[date] = None,
        data_final: Optional[date] = None,
    ) -> ListResponse:
        """
        Lista compromissos da agenda (opcional).
        """
        from models.personal_agenda import PersonalAgenda
        q = self.db.query(PersonalAgenda)
        if user_id is not None:
            q = q.filter(PersonalAgenda.user_id == user_id)
        if data_inicial:
            q = q.filter(PersonalAgenda.data >= data_inicial)
        if data_final:
            q = q.filter(PersonalAgenda.data <= data_final)
        rows = q.order_by(PersonalAgenda.data.asc(), PersonalAgenda.hora.asc()).all()
        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "titulo": r.titulo,
                "descricao": r.descricao,
                "data": r.data.isoformat() if r.data else None,
                "hora": r.hora,
            })
        return ListResponse(
            items=items,
            total=len(items),
            total_valor=None,
        )
