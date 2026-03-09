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
from mcp import MCPDetector, MCPExtractor, MCPFormatter, MCPValidator
from models.account_payable import AccountPayable
from models.account_receivable import AccountReceivable
from services.ai_service import AIService


# Data de hoje para o prompt (referência)
def _hoje() -> str:
    return date.today().strftime("%d/%m/%Y")

# Prefixo da mensagem de sugestão de descrição (para extrair na resposta do usuário)
SUGESTAO_DESCRICAO_PREFIX = "**Sugestão de descrição:**"


def _suggest_descricao_conta(data: Dict[str, Any], user_message: str) -> str:
    """Sugere descrição com base no contexto (fornecedor, cliente ou texto 'conta de X')."""
    fornecedor = (data.get("fornecedor") or "").strip()
    cliente = (data.get("cliente") or "").strip()
    if fornecedor:
        return fornecedor.strip().title()
    if cliente:
        return cliente.strip().title()
    msg = (user_message or "").strip().lower()
    # "conta de luz 100 reais" → "Conta de luz"; "conta de energia" → "Conta de energia"
    m = re.search(r"conta\s+de\s+([^,\.]+?)(?:\s+\d|\s+reais|\s+dia|$)", msg)
    if m:
        part = m.group(1).strip()
        if len(part) <= 60:
            return f"Conta de {part.strip().title()}" if not part.lower().startswith("conta") else part.strip().title()
    return "Conta"


def _parse_ai_response(text: str) -> Dict[str, Any]:
    """Extrai JSON da resposta da IA."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return json.loads(text)


def _parse_data_vencimento_resposta(texto: str) -> tuple:
    """
    Interpreta resposta sobre data de vencimento.
    'todo dia 10' → (None, bulk); 'dia 10' ou '10' → (data_iso, None).
    """
    texto = (texto or "").strip().lower()
    hoje = date.today()
    # "todo dia N" → recorrência mensal (bulk)
    m = re.match(r"todo\s+dia\s+(\d{1,2})", texto)
    if m:
        dia = int(m.group(1))
        if 1 <= dia <= 31:
            return None, {"dia": dia, "mes_inicio": 1, "mes_fim": 12, "ano": hoje.year}
    # "dia N" ou "dia N do mês" ou só "N" (1-31) → data única
    m = re.search(r"(?:dia\s+)?(\d{1,2})(?:\s+do\s+m[eê]s)?", texto)
    if m:
        dia = int(m.group(1))
        if 1 <= dia <= 31:
            try:
                ultimo = monthrange(hoje.year, hoje.month)[1]
                d = date(hoje.year, hoje.month, min(dia, ultimo))
                if d < hoje:
                    if hoje.month == 12:
                        d = date(hoje.year + 1, 1, min(dia, monthrange(hoje.year + 1, 1)[1]))
                    else:
                        d = date(hoje.year, hoje.month + 1, min(dia, monthrange(hoje.year, hoje.month + 1)[1]))
                return d.isoformat(), None
            except (ValueError, TypeError):
                pass
    return None, None


def _parse_nome_valor_resposta(texto: str) -> tuple:
    """
    Extrai nome e valor de uma única resposta tipo "Willian, valor de 500" ou "Maria 80 reais".
    Retorna (nome, valor): nome pode ser None se não houver resto; valor pode ser None.
    """
    texto = (texto or "").strip()
    if not texto:
        return None, None
    valor = None
    for pattern in [
        r"valor\s+de\s+([\d,\.]+)",
        r"([\d,\.]+)\s*reais",
        r"r\$\s*([\d,\.]+)",
    ]:
        m = re.search(pattern, texto, re.IGNORECASE)
        if m:
            try:
                s = m.group(1).replace(",", ".").strip()
                s = re.sub(r"[^\d.]", "", s)
                if s:
                    valor = float(s)
                    # Nome = texto sem a parte do valor (e vírgula/espaço ao redor)
                    nome = texto[: m.start()].strip()
                    nome = re.sub(r",\s*$", "", nome).strip()
                    if nome:
                        return nome, valor
                    return None, valor
            except (ValueError, TypeError):
                pass
    return texto, None


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

        # Assistente perguntou data/vencimento → tentar extrair data (incl. "todo dia 10" e "dia 10")
        if ("data" in last_content or "vencimento" in last_content or "quando" in last_content) and not parsed.get("data_vencimento"):
            data_str = None
            bulk = None
            # "todo dia N" ou "dia N"
            data_str, bulk = _parse_data_vencimento_resposta(current)
            if bulk:
                parsed["bulk"] = bulk
                data_str = None
            # YYYY-MM-DD
            if not data_str and re.match(r"\d{4}-\d{2}-\d{2}", current):
                data_str = current[:10]
            # DD/MM/YYYY ou D/M/YYYY
            if not data_str:
                match_dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", current)
                if match_dm:
                    d, m, y = int(match_dm.group(1)), int(match_dm.group(2)), int(match_dm.group(3))
                    if 1 <= m <= 12 and 1 <= d <= 31:
                        try:
                            data_str = date(y, m, d).isoformat()
                        except ValueError:
                            pass
            if data_str or bulk:
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

        # --- Resposta às perguntas "Preciso de mais algumas informações": manter contexto (registre fiado → 80 reais → Willian) ---
        if conversation_history and len(conversation_history) >= 2 and (message or "").strip():
            # Última mensagem do assistente que pediu "Preciso de mais" (pode não ser a última do histórico se o usuário já respondeu)
            idx_assistant = -1
            for i in range(len(conversation_history) - 1, -1, -1):
                r = (conversation_history[i].get("role") or "").strip().lower()
                c = (conversation_history[i].get("content") or "")
                if r == "assistant" and "preciso de mais" in c.lower():
                    idx_assistant = i
                    break
            if idx_assistant >= 0:
                # Intent = última mensagem do usuário ANTES desse "Preciso de mais"
                intent_msg = None
                for i in range(idx_assistant - 1, -1, -1):
                    if (conversation_history[i].get("role") or "").strip().lower() == "user":
                        intent_msg = (conversation_history[i].get("content") or "").strip()
                        break
                if intent_msg and len(intent_msg) > 2:
                    # Respostas: todas as mensagens do usuário depois do "Preciso de mais" no histórico + a mensagem atual
                    answers_so_far = []
                    for j in range(idx_assistant + 1, len(conversation_history)):
                        if (conversation_history[j].get("role") or "").strip().lower() == "user":
                            answers_so_far.append((conversation_history[j].get("content") or "").strip())
                    current_ans = (message or "").strip()
                    last_in_history = conversation_history[-1] if conversation_history else {}
                    # Incluir mensagem atual só se ainda não estiver no histórico (evitar duplicata)
                    if current_ans and ((last_in_history.get("role") or "").strip().lower() != "user" or (last_in_history.get("content") or "").strip() != current_ans):
                        answers_so_far.append(current_ans)
                    if not answers_so_far:
                        pass
                    else:
                        ctx = context or {}
                        detector = MCPDetector(self.db)
                        det = detector.detect(intent_msg, ctx)
                        if det.entity in ("contas_pagar", "contas_receber") and det.action == "INSERT":
                            extractor = MCPExtractor(self.db)
                            ext = extractor.extract(intent_msg, "INSERT", det.entity, ctx)
                            data = dict(ext.data)
                            data["tipo"] = "pagar" if det.entity == "contas_pagar" else "receber"
                            missing_order = list(ext.missing_fields)
                            _questions_map = {
                                "fornecedor": "Qual o nome do fornecedor ou descrição da conta a pagar?",
                                "cliente": "Qual o nome do cliente (conta a receber)?",
                                "valor": "Qual o valor?",
                                "data_vencimento": "Qual a data de vencimento?",
                                "descricao": "Qual a descrição da conta?",
                            }
                            for idx, ans in enumerate(answers_so_far):
                                if idx >= len(missing_order):
                                    break
                                field = missing_order[idx]
                                if field == "valor":
                                    # Tentar "Nome, valor de N" primeiro (ex.: "Willian, valor de 500" -> valor=500, nome=Willian)
                                    nome_part, valor_part = _parse_nome_valor_resposta(ans)
                                    if valor_part is not None:
                                        data["valor"] = valor_part
                                        if nome_part and idx + 1 < len(missing_order) and missing_order[idx + 1] in ("cliente", "fornecedor"):
                                            data[missing_order[idx + 1]] = nome_part.strip().title()
                                    else:
                                        # Evitar extrair número do texto inteiro (ex.: "Willian, valor de 500" -> ",." vira ".500" -> 0.5)
                                        # Primeiro tentar padrões explícitos "valor de N" / "N reais"
                                        for fallback_pat in [r"valor\s+de\s+([\d,\.]+)", r"([\d,\.]+)\s*reais"]:
                                            m = re.search(fallback_pat, ans, re.IGNORECASE)
                                            if m:
                                                try:
                                                    t = m.group(1).replace(",", ".").strip()
                                                    t = re.sub(r"[^\d.]", "", t)
                                                    if t and t != ".":
                                                        if t.startswith(".") and len(t) > 1:
                                                            t = "0" + t
                                                        v = float(t)
                                                        if v > 0:
                                                            data["valor"] = v
                                                            if fallback_pat == r"valor\s+de\s+([\d,\.]+)" and idx + 1 < len(missing_order) and missing_order[idx + 1] in ("cliente", "fornecedor"):
                                                                nome_antes = ans[: m.start()].strip()
                                                                nome_antes = re.sub(r",\s*$", "", nome_antes).strip()
                                                                if nome_antes:
                                                                    data[missing_order[idx + 1]] = nome_antes.title()
                                                            break
                                                except (ValueError, TypeError):
                                                    pass
                                        if not (data.get("valor") or 0) or float(data.get("valor") or 0) <= 0:
                                            try:
                                                s = re.sub(r"r\$\s*", "", ans, flags=re.IGNORECASE).replace(",", ".").strip()
                                                s = re.sub(r"[^\d.]", "", s)
                                                if s and s != ".":
                                                    if s.startswith(".") and len(s) > 1:
                                                        s = "0" + s
                                                    v = float(s)
                                                    if v > 0:
                                                        data["valor"] = v
                                            except (ValueError, TypeError):
                                                pass
                                elif field == "data_vencimento":
                                    data_venc, bulk = _parse_data_vencimento_resposta(ans)
                                    if data_venc:
                                        data["data_vencimento"] = data_venc
                                    if bulk:
                                        data["bulk"] = bulk
                                        data["data_vencimento"] = date.today().isoformat()
                                elif field == "fornecedor":
                                    nome_part, valor_part = _parse_nome_valor_resposta(ans)
                                    if valor_part is not None:
                                        data["valor"] = valor_part
                                    data["fornecedor"] = (nome_part if nome_part is not None else ans or "").strip().title()
                                elif field == "cliente":
                                    nome_part, valor_part = _parse_nome_valor_resposta(ans)
                                    if valor_part is not None:
                                        data["valor"] = valor_part
                                    data["cliente"] = (nome_part if nome_part is not None else ans or "").strip().title()
                                elif field == "descricao":
                                    data["descricao"] = ans.strip() if ans else ""
                            # Último recurso: se valor ainda faltando, procurar "valor de N" / "N reais" em qualquer resposta
                            if not (data.get("valor") or 0) or float(data.get("valor") or 0) <= 0:
                                for ans in answers_so_far:
                                    for fallback_pat in [r"valor\s+de\s+([\d,\.]+)", r"([\d,\.]+)\s*reais"]:
                                        m = re.search(fallback_pat, ans, re.IGNORECASE)
                                        if m:
                                            try:
                                                t = m.group(1).replace(",", ".").strip()
                                                t = re.sub(r"[^\d.]", "", t)
                                                if t and t != ".":
                                                    if t.startswith(".") and len(t) > 1:
                                                        t = "0" + t
                                                    v = float(t)
                                                    if v > 0:
                                                        data["valor"] = v
                                                        if fallback_pat == r"valor\s+de\s+([\d,\.]+)" and det.entity == "contas_receber" and not (data.get("cliente") or "").strip():
                                                            nome_antes = ans[: m.start()].strip()
                                                            nome_antes = re.sub(r",\s*$", "", nome_antes).strip()
                                                            if nome_antes:
                                                                data["cliente"] = nome_antes.title()
                                                        elif fallback_pat == r"valor\s+de\s+([\d,\.]+)" and det.entity == "contas_pagar" and not (data.get("fornecedor") or "").strip():
                                                            nome_antes = ans[: m.start()].strip()
                                                            nome_antes = re.sub(r",\s*$", "", nome_antes).strip()
                                                            if nome_antes:
                                                                data["fornecedor"] = nome_antes.title()
                                                        break
                                            except (ValueError, TypeError):
                                                pass
                                    if (data.get("valor") or 0) and float(data.get("valor") or 0) > 0:
                                        break
                            missing_after = []
                            if det.entity == "contas_pagar" and not (data.get("fornecedor") or "").strip():
                                missing_after.append("fornecedor")
                            if det.entity == "contas_receber" and not (data.get("cliente") or "").strip():
                                missing_after.append("cliente")
                            if not (data.get("valor") or 0) or float(data.get("valor") or 0) <= 0:
                                missing_after.append("valor")
                            if not data.get("data_vencimento") and not data.get("bulk"):
                                missing_after.append("data_vencimento")
                            if missing_after:
                                questions_after = [_questions_map.get(m, f"Informe {m}.") for m in missing_after]
                                return {
                                    "status": "need_info",
                                    "message": "Preciso de mais algumas informações:\n\n" + "\n".join(f"- {q}" for q in questions_after),
                                    "questions": questions_after,
                                    "records": [],
                                }
                            # Dados completos: sugerir descrição se vazio ou ir para confirmação
                            descricao_pre = (data.get("descricao") or "").strip() or None
                            if not descricao_pre:
                                sugestao = _suggest_descricao_conta(data, intent_msg)
                                return {
                                    "status": "need_info",
                                    "message": f"{SUGESTAO_DESCRICAO_PREFIX} {sugestao}.\n\nConfirma ou envie outra (opcional — **não** para sem descrição).",
                                    "questions": [],
                                    "records": [],
                                }
                            val = MCPValidator(self.db).validate(
                                {
                                    "fornecedor": (data.get("fornecedor") or "").strip(),
                                    "cliente": (data.get("cliente") or "").strip(),
                                    "valor": data.get("valor"),
                                    "data_vencimento": data.get("data_vencimento"),
                                    "descricao": (data.get("descricao") or "").strip(),
                                },
                                "INSERT",
                                det.entity,
                            )
                            if not val.valid:
                                msg = getattr(val, "message_ia", None) or "\n".join(val.errors)
                                return {"status": "error", "message": msg, "questions": [], "records": []}
                            tipo = data["tipo"]
                            fornecedor = (data.get("fornecedor") or "").strip() or ""
                            cliente = (data.get("cliente") or "").strip() or ""
                            descricao = (data.get("descricao") or "").strip() or None
                            valor = float(data.get("valor", 0))
                            data_venc = data.get("data_vencimento") or date.today().isoformat()
                            if data.get("bulk"):
                                datas = _expand_bulk_dates(data["bulk"])
                                records = [{"tipo": tipo, "fornecedor": fornecedor, "cliente": cliente, "descricao": descricao, "valor": valor, "data_vencimento": d.isoformat(), "observacao": (data.get("observacao") or "").strip() or None} for d in datas]
                            else:
                                records = [{"tipo": tipo, "fornecedor": fornecedor, "cliente": cliente, "descricao": descricao, "valor": valor, "data_vencimento": data_venc, "observacao": (data.get("observacao") or "").strip() or None}]
                            desc_label = descricao or "—"
                            if len(records) == 1:
                                r = records[0]
                                msg = f"**Conta a receber:** {r['cliente']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}" if tipo == "receber" else f"**Conta a pagar:** {r['fornecedor']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}"
                            else:
                                r0 = records[0]
                                msg = f"**{len(records)} contas a receber:** {r0['cliente']} — {desc_label} — ..." if tipo == "receber" else f"**{len(records)} contas a pagar:** {r0['fornecedor']} — {desc_label} — ..."
                            msg += "\n\n**Confirma o cadastro?**"
                            return {"status": "confirm", "message": msg, "questions": [], "records": records}

        # --- Resposta à pergunta de data de vencimento: manter contexto (ex.: "todo dia 10") ---
        if conversation_history and len(conversation_history) >= 1:
            last = conversation_history[-1]
            if (last.get("role") or "").strip().lower() == "assistant":
                last_content = (last.get("content") or "")
                if "data de vencimento" in last_content.lower() or "qual a data" in last_content.lower():
                    prev_user = None
                    for m in reversed(conversation_history[:-1]):
                        if (m.get("role") or "").strip().lower() == "user":
                            prev_user = (m.get("content") or "").strip()
                            break
                    if prev_user and len(prev_user) > 10:
                        ctx = context or {}
                        detector = MCPDetector(self.db)
                        det = detector.detect(prev_user, ctx)
                        if det.entity in ("contas_pagar", "contas_receber") and det.action == "INSERT":
                            extractor = MCPExtractor(self.db)
                            ext = extractor.extract(prev_user, "INSERT", det.entity, ctx)
                            data = dict(ext.data)
                            if (data.get("fornecedor") or data.get("cliente")) and (data.get("valor") or 0):
                                data_venc, bulk = _parse_data_vencimento_resposta(message)
                                if data_venc or bulk:
                                    data["tipo"] = "pagar" if det.entity == "contas_pagar" else "receber"
                                    tipo = data["tipo"]
                                    fornecedor = (data.get("fornecedor") or "").strip() or ""
                                    cliente = (data.get("cliente") or "").strip() or ""
                                    descricao = (data.get("descricao") or "").strip() or fornecedor or cliente or "Conta"
                                    valor = float(data.get("valor") or 0)
                                    if bulk:
                                        datas = _expand_bulk_dates(bulk)
                                        records = [
                                            {
                                                "tipo": tipo,
                                                "fornecedor": fornecedor,
                                                "cliente": cliente,
                                                "descricao": descricao,
                                                "valor": valor,
                                                "data_vencimento": d.isoformat(),
                                                "observacao": (data.get("observacao") or "").strip() or None,
                                            }
                                            for d in datas
                                        ]
                                    else:
                                        records = [{
                                            "tipo": tipo,
                                            "fornecedor": fornecedor,
                                            "cliente": cliente,
                                            "descricao": descricao,
                                            "valor": valor,
                                            "data_vencimento": data_venc or date.today().isoformat(),
                                            "observacao": (data.get("observacao") or "").strip() or None,
                                        }]
                                    val = MCPValidator(self.db).validate(
                                        {"fornecedor": fornecedor, "cliente": cliente, "valor": valor, "data_vencimento": records[0]["data_vencimento"], "descricao": descricao},
                                        "INSERT", det.entity,
                                    )
                                    if val.valid:
                                        # Se o usuário não informou descrição, perguntar (opcional) antes de confirmar
                                        if not (data.get("descricao") or "").strip():
                                            return {
                                                "status": "need_info",
                                                "message": "**Deseja adicionar alguma descrição à conta?** (opcional — responda **não** ou envie o texto)",
                                                "questions": [],
                                                "records": [],
                                            }
                                        n = len(records)
                                        desc_label = descricao or "—"
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
                                        return {"status": "confirm", "message": msg, "questions": [], "records": records}

        # --- Resposta à pergunta de descrição opcional: manter contexto (intent como no "Preciso de mais") ---
        if conversation_history and len(conversation_history) >= 2 and (message or "").strip():
            last = conversation_history[-1]
            last_role = (last.get("role") or "").strip().lower()
            last_content = (last.get("content") or "")
            # Caso 1: último é assistant com Sugestão; resposta do usuário = message
            # Caso 2: último é user (resposta já no histórico); Sugestão é o penúltimo; resposta = last content
            is_sugestao_last = last_role == "assistant" and (
                "deseja adicionar alguma descrição" in last_content.lower()
                or "descrição à conta" in last_content.lower()
                or SUGESTAO_DESCRICAO_PREFIX.lower() in last_content.lower()
            )
            is_user_replied = last_role == "user" and len(conversation_history) >= 2
            prev_content = (conversation_history[-2].get("content") or "") if len(conversation_history) >= 2 else ""
            is_sugestao_prev = is_user_replied and (
                "deseja adicionar alguma descrição" in prev_content.lower()
                or "descrição à conta" in prev_content.lower()
                or SUGESTAO_DESCRICAO_PREFIX.lower() in prev_content.lower()
            )
            if is_sugestao_last or is_sugestao_prev:
                user_desc = (message or "").strip() if is_sugestao_last else (last.get("content") or "").strip()
                content_sugestao = last_content if is_sugestao_last else prev_content
                # Intent = último user antes do último "Preciso de mais" (mesma lógica do bloco de continuação)
                idx_preciso = -1
                for i in range(len(conversation_history) - 1, -1, -1):
                    r = (conversation_history[i].get("role") or "").strip().lower()
                    c = (conversation_history[i].get("content") or "")
                    if r == "assistant" and "preciso de mais" in c.lower():
                        idx_preciso = i
                        break
                intent_msg = None
                if idx_preciso >= 0:
                    for i in range(idx_preciso - 1, -1, -1):
                        if (conversation_history[i].get("role") or "").strip().lower() == "user":
                            intent_msg = (conversation_history[i].get("content") or "").strip()
                            break
                if not intent_msg or len(intent_msg) < 3:
                    intent_msg = None
                # Respostas que preencheram o formulário = todas as mensagens user entre "Preciso de mais" e a mensagem "Sugestão"
                idx_sugestao = len(conversation_history) - 1 if is_sugestao_last else len(conversation_history) - 2
                answers_so_far = []
                if idx_preciso >= 0:
                    for j in range(idx_preciso + 1, idx_sugestao):
                        if (conversation_history[j].get("role") or "").strip().lower() == "user":
                            answers_so_far.append((conversation_history[j].get("content") or "").strip())
                if intent_msg and len(intent_msg) > 2:
                    ctx = context or {}
                    detector = MCPDetector(self.db)
                    det = detector.detect(intent_msg, ctx)
                    if det.entity in ("contas_pagar", "contas_receber") and det.action == "INSERT":
                        extractor = MCPExtractor(self.db)
                        ext = extractor.extract(intent_msg, "INSERT", det.entity, ctx)
                        data = dict(ext.data)
                        data["tipo"] = "pagar" if det.entity == "contas_pagar" else "receber"
                        missing_order = list(ext.missing_fields)
                        for idx, ans in enumerate(answers_so_far):
                            if idx >= len(missing_order):
                                break
                            field = missing_order[idx]
                            if field == "valor":
                                try:
                                    s = re.sub(r"r\$\s*", "", ans, flags=re.IGNORECASE).replace(",", ".").strip()
                                    s = re.sub(r"[^\d.]", "", s)
                                    if s:
                                        data["valor"] = float(s)
                                except (ValueError, TypeError):
                                    pass
                            elif field == "data_vencimento":
                                data_venc, bulk = _parse_data_vencimento_resposta(ans)
                                if data_venc:
                                    data["data_vencimento"] = data_venc
                                if bulk:
                                    data["bulk"] = bulk
                                    data["data_vencimento"] = date.today().isoformat()
                            elif field == "fornecedor":
                                nome_part, valor_part = _parse_nome_valor_resposta(ans)
                                if valor_part is not None:
                                    data["valor"] = valor_part
                                data["fornecedor"] = (nome_part if nome_part is not None else ans or "").strip().title()
                            elif field == "cliente":
                                nome_part, valor_part = _parse_nome_valor_resposta(ans)
                                if valor_part is not None:
                                    data["valor"] = valor_part
                                data["cliente"] = (nome_part if nome_part is not None else ans or "").strip().title()
                            elif field == "descricao":
                                data["descricao"] = ans.strip() if ans else ""
                        tipo = data["tipo"]
                        fornecedor = (data.get("fornecedor") or "").strip() or ""
                        cliente = (data.get("cliente") or "").strip() or ""
                        valor = float(data.get("valor") or 0)
                        data_venc = data.get("data_vencimento") or date.today().isoformat()
                        # Interpretar resposta à sugestão: sim → sugestão; não → sem descrição; outro → usar texto
                        confirmar_desc = user_desc.lower() in ("sim", "confirmar", "confirmo", "ok", "okay", "pode ser", "isso", "quero", "confirmar cadastro", "pode cadastrar")
                        rejeitar_desc = not user_desc or user_desc.lower() in ("não", "nao", "nada", "não quero", "nao quero", "pular", "sem descrição", "sem descricao", "opcional", "n")
                        if confirmar_desc and SUGESTAO_DESCRICAO_PREFIX in content_sugestao:
                            m_sug = re.search(r"\*\*Sugestão de descrição:\*\*\s*([^.\n]+)", content_sugestao)
                            descricao = (m_sug.group(1).strip() if m_sug else None) or fornecedor or cliente or "Conta"
                        elif rejeitar_desc:
                            descricao = fornecedor or cliente or "Conta"
                        else:
                            descricao = user_desc
                        if data.get("bulk"):
                            datas = _expand_bulk_dates(data["bulk"])
                            records = [{"tipo": tipo, "fornecedor": fornecedor, "cliente": cliente, "descricao": descricao, "valor": valor, "data_vencimento": d.isoformat(), "observacao": (data.get("observacao") or "").strip() or None} for d in datas]
                        else:
                            records = [{"tipo": tipo, "fornecedor": fornecedor, "cliente": cliente, "descricao": descricao, "valor": valor, "data_vencimento": data_venc, "observacao": (data.get("observacao") or "").strip() or None}]
                        val = MCPValidator(self.db).validate({"fornecedor": fornecedor, "cliente": cliente, "valor": valor, "data_vencimento": records[0]["data_vencimento"], "descricao": descricao}, "INSERT", det.entity)
                        if val.valid:
                            n = len(records)
                            desc_label = descricao or "—"
                            if n == 1:
                                r = records[0]
                                msg = f"**Conta a pagar:** {r['fornecedor']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}" if tipo == "pagar" else f"**Conta a receber:** {r['cliente']} — {desc_label} — {self._fmt_currency(r['valor'])} — venc. {self._fmt_date(r['data_vencimento'])}"
                            else:
                                r0 = records[0]
                                msg = f"**{n} contas a pagar:** {r0['fornecedor']} — {desc_label} — ..." if tipo == "pagar" else f"**{n} contas a receber:** {r0['cliente']} — {desc_label} — ..."
                            msg += "\n\n**Confirma o cadastro?**"
                            return {"status": "confirm", "message": msg, "questions": [], "records": records}

        # --- MCP: tentar detect + extract + validate + format primeiro ---
        try:
            detector = MCPDetector(self.db)
            det = detector.detect(message, context)
            entity = det.entity
            action = det.action

            # Dar baixa (UPDATE com subtype baixa)
            if (
                action == "UPDATE"
                and entity in ("contas_pagar", "contas_receber")
                and (det.extracted_info or {}).get("subtype") == "baixa"
            ):
                extractor = MCPExtractor(self.db)
                ext = extractor.extract(message, "UPDATE", entity, context)
                parsed_baixa = dict(ext.data)
                parsed_baixa["tipo"] = "pagar" if entity == "contas_pagar" else "receber"
                self._apply_conversation_context_fallback(
                    parsed_baixa, message, conversation_history
                )
                return self._resolve_baixa(
                    parsed_baixa["tipo"], parsed_baixa
                )

            # INSERT contas com confiança suficiente
            if (
                action == "INSERT"
                and entity in ("contas_pagar", "contas_receber")
                and det.confidence >= 0.5
            ):
                extractor = MCPExtractor(self.db)
                ext = extractor.extract(message, "INSERT", entity, context)
                data = dict(ext.data)
                data["tipo"] = "pagar" if entity == "contas_pagar" else "receber"
                data["missing"] = list(ext.missing_fields)
                _questions = {
                    "fornecedor": "Qual o nome do fornecedor ou descrição da conta a pagar?",
                    "cliente": "Qual o nome do cliente (conta a receber)?",
                    "valor": "Qual o valor?",
                    "data_vencimento": "Qual a data de vencimento?",
                    "descricao": "Qual a descrição da conta?",
                }
                data["clarification_questions"] = [
                    _questions.get(m, f"Informe {m}.") for m in ext.missing_fields
                ]
                self._apply_conversation_context_fallback(
                    data, message, conversation_history
                )
                # Reavaliar missing após fallback
                missing_after: List[str] = []
                if entity == "contas_pagar" and not (data.get("fornecedor") or "").strip():
                    missing_after.append("fornecedor")
                if entity == "contas_receber" and not (data.get("cliente") or "").strip():
                    missing_after.append("cliente")
                if not (data.get("valor") or 0) or float(data.get("valor") or 0) <= 0:
                    missing_after.append("valor")
                if not data.get("data_vencimento") and not data.get("bulk"):
                    missing_after.append("data_vencimento")
                if missing_after:
                    questions_after = [
                        _questions.get(m, f"Informe {m}.") for m in missing_after
                    ]
                    return {
                        "status": "need_info",
                        "message": "Preciso de mais algumas informações:\n\n"
                        + "\n".join(f"- {q}" for q in questions_after),
                        "questions": questions_after,
                        "records": [],
                    }
                # Descrição é opcional: sugerir com base no contexto e perguntar se aprova ou quer outra
                descricao_pre = (data.get("descricao") or "").strip() or None
                if not descricao_pre:
                    sugestao = _suggest_descricao_conta(data, message)
                    return {
                        "status": "need_info",
                        "message": f"{SUGESTAO_DESCRICAO_PREFIX} {sugestao}.\n\nConfirma ou envie outra (opcional — **não** para sem descrição).",
                        "questions": [],
                        "records": [],
                    }
                val = MCPValidator(self.db).validate(data, "INSERT", entity)
                if not val.valid:
                    msg = getattr(val, "message_ia", None) or "\n".join(val.errors)
                    return {
                        "status": "error",
                        "message": msg,
                        "questions": [],
                        "records": [],
                    }
                tipo = "pagar" if entity == "contas_pagar" else "receber"
                fornecedor = (data.get("fornecedor") or "").strip() or ""
                cliente = (data.get("cliente") or "").strip() or ""
                descricao = (data.get("descricao") or "").strip() or None
                valor = float(data.get("valor", 0))
                observacao = (data.get("observacao") or "").strip() or None
                if data.get("bulk") and isinstance(data["bulk"], dict):
                    datas = _expand_bulk_dates(data["bulk"])
                    records = [
                        {
                            "tipo": tipo,
                            "fornecedor": fornecedor,
                            "cliente": cliente,
                            "descricao": descricao,
                            "valor": valor,
                            "data_vencimento": d.isoformat(),
                            "observacao": observacao,
                        }
                        for d in datas
                    ]
                    n = len(records)
                    desc_label = descricao or "—"
                    r0 = records[0]
                    msg = f"**{n} contas a pagar:** {r0['fornecedor']} — {desc_label} — {self._fmt_currency(r0['valor'])} — vencimentos: {self._fmt_date(records[0]['data_vencimento'])} a {self._fmt_date(records[-1]['data_vencimento'])}" if tipo == "pagar" else f"**{n} contas a receber:** {r0['cliente']} — {desc_label} — {self._fmt_currency(r0['valor'])} — vencimentos: {self._fmt_date(records[0]['data_vencimento'])} a {self._fmt_date(records[-1]['data_vencimento'])}"
                    msg += "\n\n**Confirma o cadastro?**"
                    return {"status": "confirm", "message": msg, "questions": [], "records": records}
                fmt = MCPFormatter(self.db).format("INSERT", data, None, entity)
                data_venc_str = data.get("data_vencimento") or date.today().isoformat()
                if not isinstance(data_venc_str, str):
                    data_venc_str = date.today().isoformat()
                record = {
                    "tipo": tipo,
                    "fornecedor": fornecedor,
                    "cliente": cliente,
                    "descricao": descricao,
                    "valor": valor,
                    "data_vencimento": data_venc_str,
                    "observacao": observacao,
                }
                return {
                    "status": "confirm",
                    "message": fmt.message,
                    "questions": [],
                    "records": [record],
                }
        except Exception:
            pass  # fallback para IA

        # --- Fallback: fluxo original com IA ---
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
        # Descrição não é obrigatória; será perguntada como opcional no fluxo MCP
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

        # Descrição opcional: sugerir com base no contexto e perguntar se aprova ou quer outra
        if not descricao:
            sugestao = _suggest_descricao_conta(
                {"fornecedor": fornecedor, "cliente": cliente},
                message,
            )
            return {
                "status": "need_info",
                "message": f"{SUGESTAO_DESCRICAO_PREFIX} {sugestao}.\n\nConfirma ou envie outra (opcional — **não** para sem descrição).",
                "questions": [],
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
