"""
Agente de cadastro de contas a pagar e a receber em linguagem natural.
Interpreta pedidos, pede esclarecimentos quando faltam dados e confirma antes de inserir.
Suporta cadastro em massa (ex.: todo dia 8 de cada mês de 2026).
Respeita o histórico: quando o assistente perguntou algo e o usuário respondeu, usa a resposta (evita loop).
"""
import json
import re
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.prompt_config import (
    KEY_ACCOUNTS_AGENT_PARSE,
    PromptConfigManager,
    safe_substitute_prompt,
)
from models.account_payable import AccountPayable
from models.account_receivable import AccountReceivable
from services.ai_service import AIService


# Data de hoje para o prompt (referência)
def _hoje() -> str:
    return date.today().strftime("%d/%m/%Y")


def _parse_ai_response(text: str) -> Dict[str, Any]:
    """Extrai JSON da resposta da IA."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return json.loads(text)


def _expand_bulk_dates(bulk: Dict[str, Any]) -> List[date]:
    """Gera lista de datas a partir de bulk (dia, mes_inicio, mes_fim, ano)."""
    dia = int(bulk.get("dia", 1))
    mes_inicio = int(bulk.get("mes_inicio", 1))
    mes_fim = int(bulk.get("mes_fim", 12))
    ano = int(bulk.get("ano", date.today().year))
    if mes_inicio < 1:
        mes_inicio = 1
    if mes_fim > 12:
        mes_fim = 12
    if mes_inicio > mes_fim:
        mes_inicio, mes_fim = mes_fim, mes_inicio
    datas = []
    for mes in range(mes_inicio, mes_fim + 1):
        ultimo = monthrange(ano, mes)[1]
        d = min(dia, ultimo)
        datas.append(date(ano, mes, d))
    return datas


class AccountsAgentService:
    """
    Agente que interpreta linguagem natural para cadastrar contas a pagar e a receber.
    Retorna need_info (perguntas), confirm (resumo para confirmar) ou done/error.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService(db)

    def is_available(self) -> bool:
        return self.ai_service.is_available()

    def _resolve_baixa(self, tipo: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve dar baixa: busca conta em aberto por fornecedor ou cliente e retorna confirm com baixa info."""
        if tipo not in ("pagar", "receber"):
            return {
                "status": "need_info",
                "message": "Não ficou claro se é **conta a pagar** ou **conta a receber**. Ex.: \"Dar baixa na conta do João\" (receber) ou \"Marcar como paga a conta de energia\" (pagar).",
                "questions": [],
                "records": [],
                "baixa": None,
            }
        term = (parsed.get("fornecedor") or "").strip() if tipo == "pagar" else (parsed.get("cliente") or "").strip()
        if not term:
            return {
                "status": "need_info",
                "message": "Qual conta? Informe o nome do fornecedor (conta a pagar) ou do cliente (conta a receber).",
                "questions": [],
                "records": [],
                "baixa": None,
            }
        term_like = f"%{term}%"
        term_lower = term.lower()
        valor_pedido = None
        try:
            v = parsed.get("valor")
            if v is not None:
                valor_pedido = float(v)
        except (TypeError, ValueError):
            pass

        if tipo == "pagar":
            q = (
                self.db.query(AccountPayable)
                .filter(AccountPayable.data_pagamento.is_(None))
                .filter(func.lower(AccountPayable.fornecedor).like(term_like.lower()))
            )
            contas = q.all()
        else:
            q = (
                self.db.query(AccountReceivable)
                .filter(AccountReceivable.data_recebimento.is_(None))
                .filter(func.lower(AccountReceivable.cliente).like(term_like.lower()))
            )
            contas = q.all()
        if not contas:
            return {
                "status": "error",
                "message": f"Nenhuma conta em aberto encontrada para \"{term}\" (tipo: {'a pagar' if tipo == 'pagar' else 'a receber'}).",
                "questions": [],
                "records": [],
                "baixa": None,
            }

        def score(c):
            nome = (c.fornecedor if tipo == "pagar" else c.cliente).lower()
            s = 0
            if nome == term_lower:
                s += 100
            elif nome.startswith(term_lower) or term_lower.startswith(nome):
                s += 60
            elif term_lower in nome:
                s += 40
            else:
                s += 10
            if valor_pedido is not None and abs(float(c.valor) - valor_pedido) < 0.01:
                s += 50
            return s

        contas_scored = [(score(c), c) for c in contas]
        contas_scored.sort(key=lambda x: (-x[0], x[1].data_vencimento))
        c = contas_scored[0][1]
        c.update_status()
        if tipo == "pagar":
            label = f"{c.fornecedor} — {self._fmt_currency(float(c.valor))} — venc. {c.data_vencimento.strftime('%d/%m/%Y')}"
        else:
            label = f"{c.cliente} — {self._fmt_currency(float(c.valor))} — venc. {c.data_vencimento.strftime('%d/%m/%Y')}"
        n = len(contas)
        if n == 1:
            msg = f"**Dar baixa** na seguinte conta?\n\n{label}\n\n**Confirma?**"
        else:
            msg = f"Encontrei {n} conta(s) em aberto. A **mais próxima** do seu pedido:\n\n{label}\n\n**Confirma?**"
        return {
            "status": "confirm",
            "message": msg,
            "questions": [],
            "records": [],
            "baixa": {"tipo": tipo, "id": c.id, "label": label},
        }

    def _apply_conversation_context_fallback(
        self,
        parsed: Dict[str, Any],
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ) -> None:
        """
        Quando a última mensagem do assistente foi uma pergunta (ex.: "Qual a descrição?")
        e a mensagem atual do usuário é a resposta (ex.: "Conjunto Tati"), preenche o campo
        no parsed para não perguntar de novo (evita loop). Mesma lógica do fallback de contexto
        do agente de relatórios.
        """
        if not conversation_history or len(conversation_history) < 1:
            return
        last = conversation_history[-1]
        if (last.get("role") or "").strip().lower() != "assistant":
            return
        last_content = (last.get("content") or "").lower()
        current = (message or "").strip()
        if not current:
            return
        # Resposta muito longa pode ser novo pedido, não só resposta à pergunta
        if len(current) > 200:
            return

        tipo = (parsed.get("tipo") or "").strip().lower()

        # Assistente perguntou descrição → usar mensagem atual como descricao
        if ("descrição" in last_content or "descricao" in last_content or "qual a descri" in last_content) and not (parsed.get("descricao") or "").strip():
            parsed["descricao"] = current
            if "missing" in parsed and "descricao" in parsed["missing"]:
                parsed["missing"] = [m for m in parsed["missing"] if m != "descricao"]
            if "clarification_questions" in parsed:
                parsed["clarification_questions"] = [q for q in parsed["clarification_questions"] if "descri" not in (q or "").lower()]

        # Assistente perguntou fornecedor
        if ("fornecedor" in last_content or "nome do fornecedor" in last_content) and tipo == "pagar" and not (parsed.get("fornecedor") or "").strip():
            parsed["fornecedor"] = current
            if "missing" in parsed and "fornecedor" in parsed["missing"]:
                parsed["missing"] = [m for m in parsed["missing"] if m != "fornecedor"]
            if "clarification_questions" in parsed:
                parsed["clarification_questions"] = [q for q in parsed["clarification_questions"] if "fornecedor" not in (q or "").lower() and "quem" not in (q or "").lower()]

        # Assistente perguntou cliente
        if ("cliente" in last_content or "nome do cliente" in last_content) and tipo == "receber" and not (parsed.get("cliente") or "").strip():
            parsed["cliente"] = current
            if "missing" in parsed and "cliente" in parsed["missing"]:
                parsed["missing"] = [m for m in parsed["missing"] if m != "cliente"]
            if "clarification_questions" in parsed:
                parsed["clarification_questions"] = [q for q in parsed["clarification_questions"] if "cliente" not in (q or "").lower()]

        # Assistente perguntou valor → tentar extrair número
        if ("valor" in last_content or "quanto" in last_content) and parsed.get("valor") is None:
            try:
                s = re.sub(r"r\$\s*", "", current, flags=re.IGNORECASE).replace(".", "").replace(",", ".").strip()
                s = re.sub(r"[^\d.]", "", s)
                if s:
                    v = float(s)
                    if v > 0:
                        parsed["valor"] = v
                        if "missing" in parsed and "valor" in parsed["missing"]:
                            parsed["missing"] = [m for m in parsed["missing"] if m != "valor"]
                        if "clarification_questions" in parsed:
                            parsed["clarification_questions"] = [q for q in parsed["clarification_questions"] if "valor" not in (q or "").lower() and "quanto" not in (q or "").lower()]
            except (ValueError, TypeError):
                pass

        # Assistente perguntou data/vencimento → tentar extrair data
        if ("data" in last_content or "vencimento" in last_content or "quando" in last_content) and not parsed.get("data_vencimento"):
            data_str = None
            # YYYY-MM-DD
            if re.match(r"\d{4}-\d{2}-\d{2}", current):
                data_str = current[:10]
            # DD/MM/YYYY ou D/M/YYYY
            match_dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", current)
            if match_dm:
                d, m, y = int(match_dm.group(1)), int(match_dm.group(2)), int(match_dm.group(3))
                if 1 <= m <= 12 and 1 <= d <= 31:
                    try:
                        data_str = date(y, m, d).isoformat()
                    except ValueError:
                        pass
            if data_str:
                parsed["data_vencimento"] = data_str
                if "missing" in parsed and "data_vencimento" in parsed["missing"]:
                    parsed["missing"] = [m for m in parsed["missing"] if m != "data_vencimento"]
                if "clarification_questions" in parsed:
                    parsed["clarification_questions"] = [q for q in parsed["clarification_questions"] if "data" not in (q or "").lower() and "vencimento" not in (q or "").lower() and "quando" not in (q or "").lower()]

    def parse_request(
        self,
        message: str,
        context: Dict[str, Any] | None = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Interpreta a mensagem do usuário e retorna:
        - status: "need_info" | "confirm" | "error"
        - questions: lista de perguntas quando need_info
        - records: lista de {tipo, fornecedor?, cliente?, descricao, valor, data_vencimento} quando confirm
        - message: texto para exibir ao usuário
        conversation_history: últimas mensagens (role + content) para manter contexto (mín. 5 conversas).
        """
        context = context or {}
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
                history_block = "\n\n**Histórico recente da conversa (use para manter o contexto até finalizar o cadastro/baixa):**\n" + "\n".join(lines) + "\n\n"

        template = PromptConfigManager.get_or_default(
            self.db, KEY_ACCOUNTS_AGENT_PARSE,
            PromptConfigManager.get_default(KEY_ACCOUNTS_AGENT_PARSE),
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
                "message": "Configure a IA em Administração > Configuração de IA para usar o agente de contas.",
                "questions": [],
                "records": [],
            }

        try:
            client, error = self.ai_service._get_client()
            if error:
                return {"status": "error", "message": error, "questions": [], "records": []}

            config = self.ai_service.config
            provider = config["provider"]
            model = config.get("model", "")

            if provider == "openai":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result_text = r.choices[0].message.content
            elif provider == "gemini":
                r = client.generate_content(prompt)
                result_text = r.text
            elif provider == "groq":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result_text = r.choices[0].message.content
            elif provider == "ollama":
                r = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.2},
                )
                result_text = r.get("message", {}).get("content", "")
            else:
                return {"status": "error", "message": f"Provedor {provider} não suportado.", "questions": [], "records": []}

            parsed = _parse_ai_response(result_text)
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Erro ao interpretar resposta: {str(e)}", "questions": [], "records": []}
        except Exception as e:
            return {"status": "error", "message": str(e), "questions": [], "records": []}

        # Fallback: usar a resposta atual do usuário como preenchimento quando a última mensagem do assistente foi uma pergunta (evita loop)
        self._apply_conversation_context_fallback(parsed, message, conversation_history)

        intent = (parsed.get("intent") or "cadastrar").strip().lower()
        tipo = (parsed.get("tipo") or "").strip().lower()
        # Na página Contas a Pagar, "dar baixa" sem tipo = conta a pagar
        if intent == "dar_baixa" and tipo not in ("pagar", "receber") and context.get("pagina") == "contas_a_pagar":
            tipo = "pagar"
        if intent == "dar_baixa":
            return self._resolve_baixa(tipo, parsed)

        if tipo not in ("pagar", "receber"):
            return {
                "status": "need_info",
                "message": "Não ficou claro se é uma **conta a pagar** (fornecedor) ou **conta a receber** (cliente/fiado). Pode especificar?",
                "questions": ["É conta a pagar ou a receber?"],
                "records": [],
            }

        fornecedor = (parsed.get("fornecedor") or "").strip() or None
        cliente = (parsed.get("cliente") or "").strip() or None
        descricao = (parsed.get("descricao") or "").strip() or None
        try:
            valor = float(parsed.get("valor")) if parsed.get("valor") is not None else None
        except (TypeError, ValueError):
            valor = None
        data_vencimento_str = parsed.get("data_vencimento")
        observacao = (parsed.get("observacao") or "").strip() or None
        bulk = parsed.get("bulk")

        missing = list(parsed.get("missing") or [])
        questions = list(parsed.get("clarification_questions") or [])

        if tipo == "pagar" and not fornecedor:
            if "fornecedor" not in missing:
                missing.append("fornecedor")
            if not any("fornecedor" in (q or "").lower() or "quem" in (q or "").lower() for q in questions):
                questions.append("Qual o nome do fornecedor ou descrição da conta a pagar?")
        if tipo == "receber" and not cliente:
            if "cliente" not in missing:
                missing.append("cliente")
            if not any("cliente" in (q or "").lower() for q in questions):
                questions.append("Qual o nome do cliente (conta a receber)?")
        if not descricao:
            if "descricao" not in missing:
                missing.append("descricao")
            if not any("descri" in (q or "").lower() for q in questions):
                questions.append("Qual a descrição da conta? (ex.: Conjunto Tati, Energia, Aluguel)")
        if valor is None or valor <= 0:
            if "valor" not in missing:
                missing.append("valor")
            if not any("valor" in (q or "").lower() or "quanto" in (q or "").lower() for q in questions):
                questions.append("Qual o valor?")
        if not bulk and not data_vencimento_str:
            if "data_vencimento" not in missing:
                missing.append("data_vencimento")
            if not any("data" in (q or "").lower() or "quando" in (q or "").lower() or "vencimento" in (q or "").lower() for q in questions):
                questions.append("Qual a data de vencimento?")

        if missing and questions:
            return {
                "status": "need_info",
                "message": "Preciso de mais algumas informações:\n\n" + "\n".join(f"- {q}" for q in questions),
                "questions": questions,
                "records": [],
            }

        records = []
        if bulk and isinstance(bulk, dict):
            datas = _expand_bulk_dates(bulk)
            for d in datas:
                records.append({
                    "tipo": tipo,
                    "fornecedor": fornecedor,
                    "cliente": cliente,
                    "descricao": descricao,
                    "valor": valor or 0,
                    "data_vencimento": d.isoformat(),
                    "observacao": observacao,
                })
        else:
            try:
                if data_vencimento_str:
                    dt = date.fromisoformat(data_vencimento_str)
                else:
                    dt = date.today()
            except (ValueError, TypeError):
                dt = date.today()
            records.append({
                "tipo": tipo,
                "fornecedor": fornecedor,
                "cliente": cliente,
                "descricao": descricao,
                "valor": valor or 0,
                "data_vencimento": dt.isoformat(),
                "observacao": observacao,
            })

        # Resumo para confirmação
        n = len(records)
        desc_label = (records[0].get("descricao") or "").strip() or "—"
        if n == 1:
            r = records[0]
            if tipo == "pagar":
                msg = f"**Conta a pagar:** {r['fornecedor']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}"
            else:
                msg = f"**Conta a receber:** {r['cliente']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}"
        else:
            r0 = records[0]
            if tipo == "pagar":
                msg = f"**{n} contas a pagar:** {r0['fornecedor']} — {desc_label} — {self._fmt_currency(r0['valor'])} — vencimentos: {self._fmt_date(records[0]['data_vencimento'])} a {self._fmt_date(records[-1]['data_vencimento'])}"
            else:
                msg = f"**{n} contas a receber:** {r0['cliente']} — {desc_label} — {self._fmt_currency(r0['valor'])} — vencimentos: {self._fmt_date(records[0]['data_vencimento'])} a {self._fmt_date(records[-1]['data_vencimento'])}"
        msg += "\n\n**Confirma o cadastro?**"

        return {
            "status": "confirm",
            "message": msg,
            "questions": [],
            "records": records,
        }

    def _fmt_currency(self, value: float) -> str:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_date(self, iso: str) -> str:
        try:
            d = date.fromisoformat(iso)
            return d.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return iso

    def execute_insert(self, db: Session, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insere os registros no banco. Retorna { "success": bool, "count": int, "message": str }.
        """
        if not records:
            return {"success": False, "count": 0, "message": "Nenhum registro para inserir."}
        try:
            count = 0
            for r in records:
                tipo = (r.get("tipo") or "pagar").strip().lower()
                valor = float(r.get("valor", 0))
                data_venc = r.get("data_vencimento")
                if isinstance(data_venc, str):
                    data_venc = date.fromisoformat(data_venc)
                if tipo == "pagar":
                    fornecedor = (r.get("fornecedor") or "").strip() or "Fornecedor"
                    obj = AccountPayable(
                        fornecedor=fornecedor,
                        descricao=(r.get("descricao") or "").strip() or None,
                        data_vencimento=data_venc,
                        valor=valor,
                        observacao=(r.get("observacao") or "").strip() or None,
                    )
                    obj.update_status()
                    db.add(obj)
                else:
                    cliente = (r.get("cliente") or "").strip() or "Cliente"
                    obj = AccountReceivable(
                        cliente=cliente,
                        descricao=(r.get("descricao") or "").strip() or None,
                        data_vencimento=data_venc,
                        valor=valor,
                        observacao=(r.get("observacao") or "").strip() or None,
                    )
                    obj.update_status()
                    db.add(obj)
                count += 1
            db.commit()
            return {"success": True, "count": count, "message": f"Cadastro realizado: {count} conta(s) criada(s)."}
        except Exception as e:
            db.rollback()
            return {"success": False, "count": 0, "message": f"Erro ao cadastrar: {str(e)}"}

    def execute_baixa(self, db: Session, baixa: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dá baixa em uma conta (marca como paga ou recebida). baixa = { "tipo": "pagar"|"receber", "id": int }.
        Retorna { "success": bool, "message": str }.
        """
        if not baixa or baixa.get("id") is None:
            return {"success": False, "message": "Conta não identificada."}
        tipo = (baixa.get("tipo") or "").strip().lower()
        id_ = int(baixa["id"])
        try:
            if tipo == "pagar":
                obj = db.query(AccountPayable).filter(AccountPayable.id == id_).first()
                if not obj:
                    return {"success": False, "message": "Conta a pagar não encontrada."}
                obj.data_pagamento = date.today()
            else:
                obj = db.query(AccountReceivable).filter(AccountReceivable.id == id_).first()
                if not obj:
                    return {"success": False, "message": "Conta a receber não encontrada."}
                obj.data_recebimento = date.today()
            obj.update_status()
            db.commit()
            return {"success": True, "message": "Baixa realizada com sucesso."}
        except Exception as e:
            db.rollback()
            return {"success": False, "message": f"Erro ao dar baixa: {str(e)}"}
