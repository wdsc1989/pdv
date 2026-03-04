"""
Serviço único de persistência do histórico de chat dos agentes (por scope).
Formato extra_json: report_agent = orient="split" do pandas; accounts_agent = {"records": [...]}.
"""
import json
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from config.database import engine
from models.agent_chat_memory import AgentChatMessage

SCOPE_REPORT_AGENT = "report_agent"
SCOPE_ACCOUNTS_AGENT = "accounts_agent"
SCOPE_AGENDA_AGENT = "agenda_agent"


def _ensure_table():
    """Cria a tabela agent_chat_memory se não existir (ex.: app rodando antes do modelo ser adicionado)."""
    AgentChatMessage.__table__.create(engine, checkfirst=True)
HISTORY_LIMIT = 100
CONTEXT_LIMIT = 20


def _serialize_extra(extra: Any) -> Optional[str]:
    """Serializa extra para extra_json: DataFrame -> orient=split; lista de dicts -> {"records": ...}."""
    if extra is None:
        return None
    if isinstance(extra, pd.DataFrame):
        if extra.empty:
            return None
        return extra.to_json(orient="split", date_format="iso", default_handler=str)
    if isinstance(extra, list) and extra:
        return json.dumps({"records": extra}, ensure_ascii=False, default=str)
    return None


def _table_data_from_json(raw: Optional[str]) -> Optional[pd.DataFrame]:
    """Desserializa extra_json no formato orient='split' para DataFrame."""
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "columns" in obj and "data" in obj:
            return pd.DataFrame(data=obj["data"], columns=obj["columns"])
        return None
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _records_from_json(raw: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Desserializa extra_json no formato {"records": [...]} para lista de dicts."""
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "records" in obj:
            return obj["records"] if isinstance(obj["records"], list) else None
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def add_message(
    db: Session,
    user_id: int,
    scope: str,
    role: str,
    content: str,
    extra: Any = None,
) -> AgentChatMessage:
    """
    Grava uma mensagem no histórico do scope.
    extra: None, pd.DataFrame (serializado orient="split") ou lista de dicts (serializado como {"records": ...}).
    """
    _ensure_table()
    if content is None:
        content = ""
    extra_json = _serialize_extra(extra)
    msg = AgentChatMessage(
        user_id=user_id,
        scope=scope,
        role=role,
        content=content,
        extra_json=extra_json,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_messages(
    db: Session,
    user_id: int,
    scope: str,
    limit: int = HISTORY_LIMIT,
) -> List[Dict[str, Any]]:
    """
    Retorna o histórico do usuário no scope como lista de dicts.
    report_agent: {role, content, table_data} (table_data é DataFrame ou None).
    accounts_agent: {role, content, records} (records é lista ou None).
    Ordenação: created_at ascendente.
    """
    _ensure_table()
    rows = (
        db.query(AgentChatMessage)
        .filter(AgentChatMessage.user_id == user_id, AgentChatMessage.scope == scope)
        .order_by(AgentChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        if scope == SCOPE_REPORT_AGENT:
            table_data = _table_data_from_json(r.extra_json)
            out.append({"role": r.role, "content": r.content or "", "table_data": table_data})
        else:
            records = _records_from_json(r.extra_json)
            out.append({"role": r.role, "content": r.content or "", "records": records})
    return out


def get_messages_for_agent(
    db: Session,
    user_id: int,
    scope: str,
    limit: int = CONTEXT_LIMIT,
) -> List[Dict[str, str]]:
    """
    Retorna últimas N mensagens (mais recentes) com role e content, em ordem cronológica,
    para conversation_history do analyze_query / parse_request.
    """
    _ensure_table()
    subq = (
        db.query(AgentChatMessage.role, AgentChatMessage.content, AgentChatMessage.created_at)
        .filter(AgentChatMessage.user_id == user_id, AgentChatMessage.scope == scope)
        .order_by(AgentChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(subq))
    return [{"role": r.role, "content": r.content or ""} for r in rows]


def clear(db: Session, user_id: int, scope: str) -> int:
    """Remove todas as mensagens do usuário naquele scope. Retorna quantidade apagada."""
    _ensure_table()
    deleted = (
        db.query(AgentChatMessage)
        .filter(AgentChatMessage.user_id == user_id, AgentChatMessage.scope == scope)
        .delete()
    )
    db.commit()
    return deleted
