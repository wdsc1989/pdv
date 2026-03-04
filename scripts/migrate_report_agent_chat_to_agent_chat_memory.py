"""
Migração única: copia dados de report_agent_chat para agent_chat_memory (scope=report_agent).
Execute uma vez após deploy da Opção B, se a tabela report_agent_chat ainda existir:
  python -m scripts.migrate_report_agent_chat_to_agent_chat_memory
Usa SQL bruto para ler report_agent_chat (modelo já removido); não depende do modelo antigo.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from config.database import engine, SessionLocal
from models.agent_chat_memory import AgentChatMessage

SCOPE_REPORT_AGENT = "report_agent"


def main():
    # Verificar se a tabela report_agent_chat existe
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            r = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='report_agent_chat'")
            ).fetchone()
        else:
            r = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'report_agent_chat'"
                )
            ).fetchone()
        if not r:
            print("Tabela report_agent_chat não existe. Nada a migrar.")
            return

        rows = conn.execute(
            text(
                "SELECT id, user_id, role, content, table_data_json, created_at "
                "FROM report_agent_chat ORDER BY created_at ASC"
            )
        ).fetchall()

    if not rows:
        print("Nenhum registro em report_agent_chat. Nada a migrar.")
        return

    db = SessionLocal()
    try:
        for row in rows:
            msg = AgentChatMessage(
                user_id=row.user_id,
                scope=SCOPE_REPORT_AGENT,
                role=row.role,
                content=row.content or "",
                extra_json=row.table_data_json,
                created_at=row.created_at,
            )
            db.add(msg)
        db.commit()
        print(f"Migrados {len(rows)} registros de report_agent_chat para agent_chat_memory (scope={SCOPE_REPORT_AGENT}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
