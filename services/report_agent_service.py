"""
Serviço do agente de relatórios: interpreta perguntas em linguagem natural,
executa consultas ao banco via ORM e formata respostas.
Inclui análises avançadas: tendências, previsões, sazonalidade (dados + mercado) e notícias.
"""
import copy
import json
import re
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models.account_payable import AccountPayable
from models.account_receivable import AccountReceivable
from models.cash_session import CashSession
from models.product import Product
from models.sale import Sale, SaleItem
from models.stock_entry import StockEntry
from models.personal_agenda import PersonalAgenda
from config.prompt_config import (
    DEFAULTS,
    KEY_ANALYZE_QUERY,
    KEY_FORMAT_RESPONSE_ANALISE_AVANCADA,
    KEY_FORMAT_RESPONSE_GENERIC,
    KEY_INITIAL_ANALYSIS,
    PromptConfigManager,
    safe_substitute_prompt,
)
from services.ai_service import AIService
from utils.formatters import format_currency, format_date

# Sazonalidade típica do varejo no Brasil por mês (contexto para a IA)
SAZONALIDADE_MERCADO = {
    1: "Janeiro: pós-Natal, liquidação de fim de ano, férias; consumo tende a normalizar.",
    2: "Fevereiro: volta às aulas, Carnaval, pré-páscoa; demanda por roupas e acessórios de festa.",
    3: "Março: Dia da Mulher, volta à rotina; campanhas promocionais no varejo.",
    4: "Abril: Páscoa, dias mais frios no Sul/Sudeste; aquecimento em chocolates e vestuário.",
    5: "Maio: Dia das Mães, um dos picos de vendas do primeiro semestre.",
    6: "Junho: Festas Juninas, Dia dos Namorados; forte movimento em vestuário e presentes.",
    7: "Julho: férias escolares, liquidação de meio de ano; demanda variável por região.",
    8: "Agosto: Dia dos Pais, preparação para primavera; segundo pico do semestre.",
    9: "Setembro: volta às aulas, Dia da Independência; recuperação de estoques.",
    10: "Outubro: Dia das Crianças, pré-Black Friday; aquecimento para fim de ano.",
    11: "Novembro: Black Friday e campanhas; um dos maiores meses de vendas do ano.",
    12: "Dezembro: Natal e Réveillon; pico de consumo no varejo.",
}

# Contexto específico para roupas femininas (mês)
SAZONALIDADE_ROUPAS_FEMININAS = {
    1: "Liquidação de verão; peças de festa pós-Réveillon; moda praia em promoção.",
    2: "Carnaval: vestidos, looks festa, acessórios. Volta às aulas: uniforme e casual.",
    3: "Dia da Mulher: pico em moda feminina, promoções e presentes. Entrada outono.",
    4: "Páscoa: looks leves, casacos leves no Sul. Transição outono/inverno.",
    5: "Dia das Mães: um dos melhores meses; presentes, moda festa e casual.",
    6: "Festas juninas: moda casual e térmica. Dia dos Namorados: vestidos e lingerie.",
    7: "Liquidação de inverno; segunda semestre. Férias: moda casual e conforto.",
    8: "Dia dos Pais (presentes). Pré-primavera: novidades e cores.",
    9: "Volta às aulas: moda jovem e casual. Dia da Independência; primavera.",
    10: "Primavera/verão: vestidos, shorts, moda praia. Dia das Crianças (maternidade).",
    11: "Black Friday: um dos picos do ano em moda feminina. Réveillon e festas.",
    12: "Natal e Réveillon: vestidos de festa, moda noite; pico de vendas.",
}

# Schema do banco para o agente gerar consultas SQL quando necessário (apenas leitura)
DB_SCHEMA = """
Tabelas e colunas (use exatamente estes nomes em SQL):
- sales: id, cash_session_id, data_venda (DATE), total_vendido, total_lucro, total_pecas, tipo_pagamento, status ('concluida'|'cancelada'), created_at
- sale_items: id, sale_id (FK sales.id), product_id (FK products.id), quantidade, preco_unitario, preco_custo_unitario, subtotal, lucro_item
- products: id, codigo, nome, categoria, marca, preco_custo, preco_venda, estoque_atual, estoque_minimo, imagem_path, ativo, categoria_id (FK product_categories.id), created_at, updated_at
- product_categories: id, nome, descricao, ativo, created_at, updated_at
- cash_sessions: id, data_abertura (DATETIME), data_fechamento, valor_abertura, valor_fechamento, status ('aberta'|'fechada'), observacao, created_at
- accounts_payable: id, fornecedor, descricao, data_vencimento (DATE), data_pagamento, valor, status ('aberta'|'paga'|'atrasada'), observacao, created_at, updated_at
- accounts_receivable: id, cliente, descricao, data_vencimento (DATE), data_recebimento, valor, status ('aberta'|'recebida'|'atrasada'), observacao, created_at, updated_at
- stock_entries: id, product_id (FK products.id), quantity, data_entrada (DATE), observacao, created_at
- users: id, username, name, role ('admin'|'gerente'|'vendedor'), active, created_at
- accessory_stock: id, preco, quantidade
- accessory_sales: id, data_venda (DATE), preco, quantidade, repasse_feito
- accessory_stock_entries: id, data_entrada (DATE), preco, quantidade
Relacionamentos: sales.cash_session_id -> cash_sessions.id; sale_items.sale_id -> sales.id, sale_items.product_id -> products.id; products.categoria_id -> product_categories.id; stock_entries.product_id -> products.id.
"""

ALLOWED_SQL_TABLES = frozenset({
    "sales", "sale_items", "products", "product_categories", "cash_sessions",
    "accounts_payable", "accounts_receivable", "stock_entries", "users",
    "accessory_stock", "accessory_sales", "accessory_stock_entries",
})


class ReportAgentService:
    """
    Agente de relatórios: analisa pergunta (IA), executa consulta (ORM) e formata resposta.
    Todas as consultas usam SQLAlchemy ORM; nenhum SQL gerado pela IA.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService(db)

    def analyze_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        return_debug: bool = False,
    ):
        """
        Analisa a pergunta em linguagem natural e retorna intent, data_type, period, etc.
        conversation_history: últimas mensagens (role + content) para manter contexto (mín. 5 conversas).
        return_debug: se True, retorna {"analysis": ..., "debug": {"raw_json", "path", "final_json"}}.
        """
        if not self.ai_service.is_available():
            return {
                "intent": "error",
                "error": "Serviço de IA não disponível. Configure em Administração > Configuração de IA.",
            }

        data_hoje = date.today().strftime("%d/%m/%Y")
        history_block = ""
        if conversation_history:
            recent = conversation_history[-20:]
            lines = []
            for m in recent:
                role = (m.get("role") or "user").strip().lower()
                content = (m.get("content") or "").strip()
                if not content:
                    continue
                label = "Usuário" if role == "user" else "Assistente"
                lines.append(f"{label}: {content[:500]}{'...' if len(content) > 500 else ''}")
            if lines:
                history_block = "\n\n**Histórico recente da conversa (use para manter o contexto do assunto):**\n" + "\n".join(lines) + "\n\n"

        template = PromptConfigManager.get_or_default(
            self.db, KEY_ANALYZE_QUERY, DEFAULTS[KEY_ANALYZE_QUERY]
        )
        prompt = safe_substitute_prompt(
            template,
            DB_SCHEMA=DB_SCHEMA,
            data_hoje=data_hoje,
            history_block=history_block,
            query=query,
        )

        try:
            client, error = self.ai_service._get_client()
            if error:
                return {"intent": "error", "error": error}

            config = self.ai_service.config
            provider = config["provider"]
            model = config.get("model", "")

            if provider == "openai":
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                result_text = response.choices[0].message.content
            elif provider == "gemini":
                response = client.generate_content(prompt)
                result_text = response.text
            elif provider == "groq":
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                result_text = response.choices[0].message.content
            elif provider == "ollama":
                response = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.3},
                )
                result_text = response["message"]["content"]
            else:
                return {"intent": "error", "error": f"Provedor {provider} não suportado"}

            result_text = result_text.strip()
            if result_text.startswith("```"):
                result_text = re.sub(r"^```(?:json)?\s*", "", result_text, flags=re.MULTILINE)
                result_text = re.sub(r"```\s*$", "", result_text, flags=re.MULTILINE)
            analysis = json.loads(result_text)
            raw_analysis = copy.deepcopy(analysis) if return_debug else None
            # Fallback: se a IA insistir em "esclarecer_periodo" mas o usuário já respondeu com o período (ex.: "do ano de 2026"), forçar consulta
            analysis, period_applied = self._apply_period_clarification_fallback(analysis, query, conversation_history)
            # Fallback: perguntas de continuação ("quais são?", "as contas a pagar") devem usar o assunto do histórico, não resposta_direta genérica
            analysis, ref_applied = self._apply_referential_query_fallback(analysis, query, conversation_history)
            # Fallback: quando o usuário responde ao "De qual período?" (ex.: "este mes") mas a IA retornou data_type errado (ex.: resumo_periodo em vez de contas_receber para "fiados"), corrigir
            analysis, dt_override_applied = self._apply_period_reply_data_type_override(analysis, query, conversation_history)
            period_raw = analysis.get("period")
            analysis["period"] = self._process_period(period_raw if isinstance(period_raw, dict) else {})
            if return_debug and raw_analysis is not None:
                path_parts = ["Resposta da IA (JSON bruto)"]
                if period_applied:
                    path_parts.append("→ Fallback de período aplicado")
                if ref_applied:
                    path_parts.append("→ Fallback referencial aplicado")
                if dt_override_applied:
                    path_parts.append("→ Data_type corrigido por resposta de período")
                return {
                    "analysis": analysis,
                    "debug": {
                        "raw_json": raw_analysis,
                        "path": " ".join(path_parts),
                        "final_json": copy.deepcopy(analysis),
                    },
                }
            return analysis
        except json.JSONDecodeError as e:
            return {"intent": "error", "error": f"Erro ao interpretar resposta da IA: {str(e)}"}
        except Exception as e:
            return {"intent": "error", "error": f"Erro ao analisar pergunta: {str(e)}"}

    def _apply_period_clarification_fallback(
        self,
        analysis: Dict[str, Any],
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ):
        """
        Se a IA retornou esclarecer_periodo mas o histórico mostra que o assistente
        perguntou o período e o usuário acabou de responder (ex.: "do ano de 2026"),
        forçar intent consulta com data_type inferido da pergunta anterior e period preenchido.
        Retorna (analysis, applied: bool).
        """
        if analysis.get("intent") != "esclarecer_periodo":
            return analysis, False
        if not conversation_history or len(conversation_history) < 1:
            return analysis, False

        last_msg = conversation_history[-1]
        last_role = (last_msg.get("role") or "").strip().lower()
        last_content = (last_msg.get("content") or "").strip()
        if last_role != "assistant" or "de qual período" not in last_content.lower():
            return analysis, False

        query_lower = (query or "").strip().lower()
        if len(query_lower) > 120:
            return analysis, False

        # Parece resposta de período? (ano, 2026, hoje, este mês, etc.)
        year_match = re.search(r"\b(19|20)\d{2}\b", query)
        has_year = bool(year_match)
        period_keywords = (
            "ano atual" in query_lower or "este ano" in query_lower or "ano de " in query_lower
            or "do ano" in query_lower or "o ano todo" in query_lower or "ano completo" in query_lower
            or "hoje" in query_lower or "este mês" in query_lower or "esta semana" in query_lower
            or query_lower.strip() in ("2026", "2025", "2024")
        )
        if not (has_year or period_keywords):
            return analysis, False

        # Inferir data_type da última pergunta do usuário no histórico
        data_type = "resumo_periodo"
        for m in reversed(conversation_history):
            if (m.get("role") or "").strip().lower() != "user":
                continue
            prev = (m.get("content") or "").lower()
            if "fiado" in prev or "contas a receber" in prev or "a receber" in prev:
                data_type = "contas_receber"
                break
            if "contas a pagar" in prev:
                data_type = "contas_pagar"
                break
            if "produtos mais vendidos" in prev or "mais vendidos" in prev:
                data_type = "produtos_mais_vendidos"
                break
            if "entradas" in prev and "estoque" in prev:
                data_type = "entradas_estoque"
                break
            if "sessões" in prev or "caixa" in prev:
                data_type = "sessoes_caixa"
                break
            if "faturamento" in prev or "quanto vendi" in prev or "vendas" in prev or "resumo" in prev:
                data_type = "resumo_periodo"
                break
            break

        today = date.today()
        year = today.year
        if year_match:
            try:
                year = int(year_match.group(0))
            except (ValueError, TypeError):
                pass

        if "hoje" in query_lower and "ano" not in query_lower and "mês" not in query_lower:
            analysis["intent"] = "consulta"
            analysis["data_type"] = data_type
            analysis["period"] = {"start": today.isoformat(), "end": today.isoformat(), "type": "hoje"}
            analysis["clarification_message"] = None
            return analysis, True
        if "este mês" in query_lower or "mes atual" in query_lower:
            start = today.replace(day=1)
            analysis["intent"] = "consulta"
            analysis["data_type"] = data_type
            analysis["period"] = {"start": start.isoformat(), "end": today.isoformat(), "type": "mes_atual"}
            analysis["clarification_message"] = None
            return analysis, True
        if "esta semana" in query_lower:
            start = today - relativedelta(days=6)
            analysis["intent"] = "consulta"
            analysis["data_type"] = data_type
            analysis["period"] = {"start": start.isoformat(), "end": today.isoformat(), "type": "semanal"}
            analysis["clarification_message"] = None
            return analysis, True

        # Ano (completo): "do ano de 2026", "2026", "ano atual", etc.
        analysis["intent"] = "consulta"
        analysis["data_type"] = data_type
        analysis["period"] = {
            "start": f"{year}-01-01",
            "end": f"{year}-12-31",
            "type": "anual",
            "year": str(year),
        }
        analysis["clarification_message"] = None
        return analysis, True

    def _apply_period_reply_data_type_override(
        self,
        analysis: Dict[str, Any],
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ):
        """
        Quando o usuário responde ao "De qual período?" (ex.: "este mes") e a IA retornou
        intent "consulta" mas com data_type errado (ex.: resumo_periodo em vez de contas_receber
        quando o usuário tinha pedido "fiados"), corrigir data_type a partir da pergunta anterior.
        Retorna (analysis, applied: bool).
        """
        if analysis.get("intent") != "consulta":
            return analysis, False
        if not conversation_history or len(conversation_history) < 1:
            return analysis, False

        last_msg = conversation_history[-1]
        last_role = (last_msg.get("role") or "").strip().lower()
        last_content = (last_msg.get("content") or "").strip()
        if last_role != "assistant" or "de qual período" not in last_content.lower():
            return analysis, False

        query_lower = (query or "").strip().lower()
        period_reply = (
            "este mês" in query_lower or "este mes" in query_lower
            or "esta semana" in query_lower or "hoje" in query_lower
            or "ano atual" in query_lower or "este ano" in query_lower
            or "o ano todo" in query_lower or re.search(r"\b(19|20)\d{2}\b", query)
        )
        if not period_reply:
            return analysis, False

        # Inferir data_type da última pergunta do usuário no histórico (antes da pergunta do assistente)
        inferred_data_type = None
        for m in reversed(conversation_history):
            if (m.get("role") or "").strip().lower() != "user":
                continue
            prev = (m.get("content") or "").lower()
            if "fiado" in prev or "contas a receber" in prev or "a receber" in prev:
                inferred_data_type = "contas_receber"
                break
            if "contas a pagar" in prev:
                inferred_data_type = "contas_pagar"
                break
            if "produtos mais vendidos" in prev or "mais vendidos" in prev:
                inferred_data_type = "produtos_mais_vendidos"
                break
            if "entradas" in prev and "estoque" in prev:
                inferred_data_type = "entradas_estoque"
                break
            if "sessões" in prev or "sessoes" in prev or "caixa" in prev:
                inferred_data_type = "sessoes_caixa"
                break
            if "faturamento" in prev or "quanto vendi" in prev or "vendas" in prev or "resumo" in prev:
                inferred_data_type = "resumo_periodo"
                break
            break

        if inferred_data_type is None:
            return analysis, False
        current_data_type = analysis.get("data_type") or ""
        if current_data_type == inferred_data_type:
            return analysis, False

        analysis["data_type"] = inferred_data_type
        return analysis, True

    def _apply_referential_query_fallback(
        self,
        analysis: Dict[str, Any],
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]],
    ):
        """
        Quando o usuário faz uma pergunta de continuação ("quais são?", "as contas a pagar", "lista", "mostre")
        e a IA retornou resposta_direta genérica (ex.: "Você pode perguntar sobre..."), forçar intent consulta
        com data_type inferido do histórico, para que o agente liste os dados em vez de dar dica de perguntas.
        Retorna (analysis, applied: bool).
        """
        intent = analysis.get("intent", "")
        query_stripped = (query or "").strip()
        query_lower = query_stripped.lower()
        if len(query_stripped) > 80:
            return analysis, False

        # Frases que indicam continuação do assunto (pedir lista/relatório do que já foi mencionado)
        referential_phrases = (
            "quais são",
            "quais sao",
            "quais?",
            "lista",
            "listar",
            "mostre",
            "mostra",
            "me mostra",
            "quero ver",
            "e as contas",
            "as contas a pagar",
            "a contas a pagar",
            "contas a pagar",
            "contas a receber",
            "dessa lista",
            "desse relatório",
            "desse relatorio",
        )
        is_referential = any(p in query_lower for p in referential_phrases) or query_lower in (
            "quais são",
            "quais",
            "lista",
            "mostre",
            "mostra",
        )
        if not is_referential:
            return analysis, False

        # Só aplicar se a IA devolveu resposta_direta com texto genérico (ex.: "Você pode perguntar sobre...")
        resposta = (analysis.get("resposta_direta") or "").strip().lower()
        is_generic_reply = (
            intent == "resposta_direta"
            and (
                "você pode perguntar" in resposta
                or "pode perguntar sobre" in resposta
                or "exemplos:" in resposta
                or "faturamento de hoje" in resposta
                or "produtos mais vendidos" in resposta
            )
        )
        if not is_generic_reply and intent != "resposta_direta":
            return analysis, False
        if not conversation_history or len(conversation_history) < 1:
            return analysis, False

        # Inferir data_type do histórico (última pergunta do usuário ou última resposta do assistente)
        data_type = None
        for m in reversed(conversation_history):
            content = (m.get("content") or "").lower()
            role = (m.get("role") or "").strip().lower()
            if "contas a pagar" in content or "quem devo pagar" in content or "contas a pagar" in query_lower:
                data_type = "contas_pagar"
                break
            if "contas a receber" in content or "quem me deve" in content or "quem te deve" in content:
                data_type = "contas_receber"
                break
            if "produtos mais vendidos" in content or "mais vendidos" in content:
                data_type = "produtos_mais_vendidos"
                break
            if "entradas" in content and "estoque" in content:
                data_type = "entradas_estoque"
                break
            if "sessões" in content or "sessoes" in content or "caixa" in content:
                data_type = "sessoes_caixa"
                break
            if "faturamento" in content or "quanto vendi" in content or "vendas" in content or "resumo" in content:
                data_type = "resumo_periodo"
                break
            if role == "assistant" and ("conta a pagar" in content or "contas a pagar" in content):
                data_type = "contas_pagar"
                break
            if role == "assistant" and ("conta a receber" in content or "contas a receber" in content):
                data_type = "contas_receber"
                break

        if not data_type:
            return analysis, False

        today = date.today()
        # Forçar consulta com data_type do histórico. Para "quais são?" / "as contas a pagar" usar período sensível.
        analysis["intent"] = "consulta"
        analysis["data_type"] = data_type
        analysis["resposta_direta"] = None
        analysis["clarification_message"] = None
        # Contas a pagar/receber: listar em aberto do mês atual; se o usuário quiser outro período, pode pedir depois
        if data_type in ("contas_pagar", "contas_receber"):
            start = today.replace(day=1)
            analysis["period"] = {"start": start.isoformat(), "end": today.isoformat(), "type": "mes_atual", "month": None, "year": str(today.year)}
        else:
            analysis["period"] = {"start": today.isoformat(), "end": today.isoformat(), "type": "mes_atual", "month": None, "year": str(today.year)}
        return analysis, True

    def _process_period(self, period_info: Dict) -> Dict[str, Any]:
        """Converte período em datas start/end."""
        if period_info is None or not isinstance(period_info, dict):
            period_info = {}

        def _empty(val: Any) -> bool:
            """True se o valor for None, string vazia ou a string 'null' (IA às vezes retorna 'null' como texto)."""
            if val is None:
                return True
            s = str(val).strip().lower()
            return s in ("", "null")

        period_type = period_info.get("type", "ultimo_mes")
        start_str = period_info.get("start")
        end_str = period_info.get("end")
        month_name = period_info.get("month")
        year_str = period_info.get("year")
        today = date.today()

        # Tipos que sempre calculamos a partir da data de hoje (ignorar start/end da IA)
        if period_type == "hoje":
            return {"start": today, "end": today, "type": "hoje"}
        if period_type == "mes_atual":
            start = today.replace(day=1)
            return {"start": start, "end": today, "type": "mes_atual"}
        if period_type == "proximo_mes":
            primeiro_proximo = (today.replace(day=1) + relativedelta(months=1))
            ultimo_proximo = primeiro_proximo.replace(day=monthrange(primeiro_proximo.year, primeiro_proximo.month)[1])
            return {"start": primeiro_proximo, "end": ultimo_proximo, "type": "proximo_mes"}
        if period_type == "semanal":
            start = today - relativedelta(days=6)
            return {"start": start, "end": today, "type": "semanal"}
        if period_type == "geral":
            return {"start": date(2000, 1, 1), "end": today, "type": "geral"}

        # Ano completo: type "anual" com year (ex.: "ano completo", "este ano 2026")
        if period_type == "anual" and not _empty(year_str):
            try:
                year = int(year_str)
                return {
                    "start": date(year, 1, 1),
                    "end": date(year, 12, 31),
                    "type": "anual",
                }
            except (ValueError, TypeError):
                pass

        if not _empty(month_name) and not _empty(year_str):
            month_map = {
                "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
                "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
            }
            month_num = month_map.get(str(month_name).lower(), today.month)
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                year = today.year
            try:
                start = date(year, month_num, 1)
                end = date(year, month_num, monthrange(year, month_num)[1])
                return {"start": start, "end": end, "type": "mes_especifico"}
            except (ValueError, KeyError):
                pass

        if start_str and str(start_str).strip().lower() not in ("null", ""):
            try:
                start_date = datetime.strptime(str(start_str).strip()[:10], "%Y-%m-%d").date()
                if end_str and str(end_str).strip().lower() not in ("null", ""):
                    end_date = datetime.strptime(str(end_str).strip()[:10], "%Y-%m-%d").date()
                else:
                    end_date = start_date
                if end_date < start_date:
                    end_date = start_date
                return {"start": start_date, "end": end_date, "type": "personalizado"}
            except ValueError:
                pass

        if period_type in ("ultimo_mes", "mensal"):
            start = (today - relativedelta(months=1)).replace(day=1)
            return {"start": start, "end": today, "type": "ultimo_mes"}
        # default: último mês
        start = (today - relativedelta(months=1)).replace(day=1)
        return {"start": start, "end": today, "type": "ultimo_mes"}

    def _execute_sql_query(self, db: Session, sql_query: str) -> Dict[str, Any]:
        """Executa uma única instrução SELECT após validar (apenas tabelas permitidas, só leitura)."""
        if not sql_query or not isinstance(sql_query, str):
            return {"type": "error", "error": "Consulta SQL não fornecida."}
        sql = sql_query.strip()
        if not sql.upper().startswith("SELECT"):
            return {"type": "error", "error": "Apenas consultas SELECT são permitidas."}
        if ";" in sql:
            return {"type": "error", "error": "Use apenas uma instrução SELECT (sem ponto e vírgula)."}
        # Extrai nomes de tabelas (FROM e JOIN)
        from_match = re.findall(r"\bFROM\s+(\w+)\b", sql, re.IGNORECASE)
        join_match = re.findall(r"\bJOIN\s+(\w+)\b", sql, re.IGNORECASE)
        tables = [t.lower() for t in from_match + join_match]
        invalid = [t for t in tables if t not in ALLOWED_SQL_TABLES]
        if invalid:
            return {"type": "error", "error": f"Tabela(s) não permitida(s): {', '.join(invalid)}."}
        try:
            result = db.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())
            # Converte linhas em listas (valores serializáveis para JSON/DataFrame)
            data_rows = []
            for row in rows:
                data_rows.append([self._serialize_cell(c) for c in row])
            return {
                "type": "sql_result",
                "data": {"columns": columns, "rows": data_rows},
            }
        except Exception as e:
            return {"type": "error", "error": f"Erro ao executar consulta: {str(e)}"}

    @staticmethod
    def _serialize_cell(val: Any) -> Any:
        """Serializa célula para JSON/DataFrame (date/datetime -> str)."""
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return val

    def execute_query(self, db: Session, query_analysis: Dict) -> Dict[str, Any]:
        """Executa a consulta ao banco conforme a análise da pergunta."""
        data_type = query_analysis.get("data_type")
        period = query_analysis.get("period") or {}
        if not isinstance(period, dict):
            period = {}
        default_start = date.today() - relativedelta(months=1)
        default_end = date.today()
        start_date = period.get("start") or default_start
        end_date = period.get("end") or default_end
        if not isinstance(start_date, date):
            start_date = default_start
        if not isinstance(end_date, date):
            end_date = default_end

        try:
            if data_type == "sql":
                sql_query = query_analysis.get("sql_query") or ""
                return self._execute_sql_query(db, sql_query)
            if data_type in ("vendas", "resumo_periodo"):
                return self._query_resumo_periodo(db, start_date, end_date)
            if data_type == "produtos_mais_vendidos":
                return self._query_produtos_mais_vendidos(db, start_date, end_date)
            if data_type == "valor_estoque":
                return self._query_valor_estoque(db)
            if data_type == "entradas_estoque":
                return self._query_entradas_estoque(db, start_date, end_date)
            if data_type == "sessoes_caixa":
                return self._query_sessoes_caixa(db, start_date, end_date)
            if data_type == "contas_pagar":
                return self._query_contas_pagar(db, start_date, end_date)
            if data_type == "contas_receber":
                return self._query_contas_receber(db, start_date, end_date)
            if data_type == "analise_avancada":
                return self._query_analise_avancada(db, start_date, end_date)
            # default
            return self._query_resumo_periodo(db, start_date, end_date)
        except Exception as e:
            return {"type": "error", "error": str(e)}

    def _query_resumo_periodo(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Totais de vendas no período (resumo do período)."""
        vendas_query = (
            db.query(
                func.coalesce(func.sum(Sale.total_vendido), 0.0),
                func.coalesce(func.sum(Sale.total_lucro), 0.0),
                func.coalesce(func.sum(Sale.total_pecas), 0),
            )
            .filter(Sale.data_venda >= start_date)
            .filter(Sale.data_venda <= end_date)
            .filter(Sale.status != "cancelada")
        )
        row = vendas_query.one()
        total_vendido = float(row[0])
        total_lucro = float(row[1])
        total_pecas = int(row[2] or 0)
        num_vendas = (
            db.query(func.count(Sale.id))
            .filter(Sale.data_venda >= start_date)
            .filter(Sale.data_venda <= end_date)
            .filter(Sale.status != "cancelada")
            .scalar()
        ) or 0
        margem = (total_lucro / total_vendido * 100) if total_vendido > 0 else 0.0
        ticket_medio = (total_vendido / num_vendas) if num_vendas > 0 else 0.0
        return {
            "type": "resumo_periodo",
            "data": {
                "total_vendido": total_vendido,
                "total_lucro": total_lucro,
                "total_pecas": total_pecas,
                "num_vendas": num_vendas,
                "margem": margem,
                "ticket_medio": ticket_medio,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _query_produtos_mais_vendidos(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Top produtos mais vendidos no período."""
        top_itens = (
            db.query(
                Product.codigo,
                Product.nome,
                func.coalesce(func.sum(SaleItem.quantidade), 0.0).label("qtd"),
                func.coalesce(
                    func.sum(SaleItem.quantidade * SaleItem.preco_unitario), 0.0
                ).label("receita"),
                func.coalesce(func.sum(SaleItem.lucro_item), 0.0).label("lucro"),
            )
            .join(Product, Product.id == SaleItem.product_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(Sale.data_venda >= start_date)
            .filter(Sale.data_venda <= end_date)
            .filter(Sale.status != "cancelada")
            .group_by(Product.codigo, Product.nome)
            .order_by(func.sum(SaleItem.quantidade).desc())
            .limit(10)
            .all()
        )
        items = [
            {
                "codigo": cod,
                "nome": nome,
                "quantidade": float(qtd),
                "receita": float(receita),
                "lucro": float(lucro),
            }
            for cod, nome, qtd, receita, lucro in top_itens
        ]
        return {
            "type": "produtos_mais_vendidos",
            "data": {
                "items": items,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _query_valor_estoque(self, db: Session) -> Dict[str, Any]:
        """Valor atual do estoque (custo e venda)."""
        produtos = db.query(Product).all()
        valor_custo = sum((p.preco_custo or 0) * (p.estoque_atual or 0) for p in produtos)
        valor_venda = sum((p.preco_venda or 0) * (p.estoque_atual or 0) for p in produtos)
        return {
            "type": "valor_estoque",
            "data": {
                "valor_estoque_custo": float(valor_custo),
                "valor_estoque_venda": float(valor_venda),
            },
        }

    def _query_entradas_estoque(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Entradas de estoque no período."""
        entradas = (
            db.query(StockEntry, Product.codigo, Product.nome)
            .join(Product, Product.id == StockEntry.product_id)
            .filter(StockEntry.data_entrada >= start_date)
            .filter(StockEntry.data_entrada <= end_date)
            .order_by(StockEntry.data_entrada.desc(), StockEntry.id.desc())
            .all()
        )
        rows = [
            {
                "data_entrada": e[0].data_entrada.isoformat(),
                "codigo": e[1],
                "nome": e[2],
                "quantidade": e[0].quantity,
                "observacao": (e[0].observacao or ""),
            }
            for e in entradas
        ]
        total_units = sum(e[0].quantity for e in entradas)
        return {
            "type": "entradas_estoque",
            "data": {
                "entradas": rows,
                "total_unidades": total_units,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _query_sessoes_caixa(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Sessões de caixa no período."""
        sessoes = (
            db.query(CashSession)
            .filter(func.date(CashSession.data_abertura) >= start_date)
            .filter(func.date(CashSession.data_abertura) <= end_date)
            .order_by(CashSession.data_abertura)
            .all()
        )
        rows = []
        for s in sessoes:
            total_s = (
                db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
                .filter(Sale.cash_session_id == s.id)
                .filter(Sale.status != "cancelada")
                .scalar()
            )
            rows.append({
                "id": s.id,
                "data_abertura": format_date(s.data_abertura),
                "data_fechamento": format_date(s.data_fechamento) if s.data_fechamento else "-",
                "valor_abertura": float(s.valor_abertura),
                "valor_fechamento": float(s.valor_fechamento) if s.valor_fechamento is not None else None,
                "status": s.status,
                "total_vendas_sessao": float(total_s or 0),
            })
        return {
            "type": "sessoes_caixa",
            "data": {
                "sessoes": rows,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _query_contas_pagar(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Contas a pagar com vencimento no período."""
        contas = (
            db.query(AccountPayable)
            .filter(AccountPayable.data_vencimento >= start_date)
            .filter(AccountPayable.data_vencimento <= end_date)
            .order_by(AccountPayable.data_vencimento)
            .all()
        )
        total_abertas = 0.0
        total_pagas = 0.0
        rows = []
        for c in contas:
            c.update_status()
            if c.status == "paga":
                total_pagas += c.valor
            else:
                total_abertas += c.valor
            rows.append({
                "fornecedor": c.fornecedor,
                "data_vencimento": c.data_vencimento.isoformat(),
                "data_pagamento": c.data_pagamento.isoformat() if c.data_pagamento else None,
                "valor": float(c.valor),
                "status": c.status,
            })
        return {
            "type": "contas_pagar",
            "data": {
                "contas": rows,
                "total_abertas": total_abertas,
                "total_pagas": total_pagas,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _query_contas_receber(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Contas a receber (fiado) com vencimento no período."""
        contas = (
            db.query(AccountReceivable)
            .filter(AccountReceivable.data_vencimento >= start_date)
            .filter(AccountReceivable.data_vencimento <= end_date)
            .order_by(AccountReceivable.data_vencimento)
            .all()
        )
        total_abertas = 0.0
        total_recebidas = 0.0
        rows = []
        for c in contas:
            c.update_status()
            if c.status == "recebida":
                total_recebidas += c.valor
            else:
                total_abertas += c.valor
            rows.append({
                "cliente": c.cliente,
                "data_vencimento": c.data_vencimento.isoformat(),
                "data_recebimento": c.data_recebimento.isoformat() if c.data_recebimento else None,
                "valor": float(c.valor),
                "status": c.status,
            })
        return {
            "type": "contas_receber",
            "data": {
                "contas": rows,
                "total_abertas": total_abertas,
                "total_recebidas": total_recebidas,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

    def _fetch_news_headlines(self, limit: int = 5) -> List[Dict[str, str]]:
        """Busca manchetes de economia/varejo em RSS para contexto da análise."""
        urls = [
            "https://rss.uol.com.br/feed/economia.xml",
            "https://feeds.folha.uol.com.br/mercado/rss091.xml",
        ]
        headers = {"User-Agent": "Mozilla/5.0 (compatible; PDV-Bot/1.0)"}
        for url in urls:
            try:
                req = Request(url, headers=headers)
                with urlopen(req, timeout=8) as resp:
                    xml = resp.read().decode("utf-8", errors="replace")
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml)
                item_elems = root.findall(".//item") or root.findall(".//{*}item")
                items = []
                for item in item_elems[:limit]:
                    title = item.find("title")
                    link = item.find("link")
                    if title is not None and title.text:
                        items.append({
                            "title": title.text.strip(),
                            "link": link.text.strip() if link is not None and link.text else "",
                        })
                if items:
                    return items
            except Exception:
                continue
        return []

    def _query_analise_avancada(
        self, db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """Análise avançada: histórico mensal, tendência, previsão, sazonalidade (dados + mercado), notícias."""
        today = date.today()
        twelve_months_ago = today - relativedelta(months=12)
        sales = (
            db.query(Sale.data_venda, Sale.total_vendido, Sale.total_lucro)
            .filter(Sale.data_venda >= twelve_months_ago)
            .filter(Sale.data_venda <= today)
            .filter(Sale.status != "cancelada")
            .all()
        )
        by_month = defaultdict(lambda: {"total": 0.0, "lucro": 0.0, "qtd": 0})
        by_weekday = defaultdict(lambda: {"total": 0.0, "qtd": 0})
        for d, total, lucro in sales:
            key = (d.year, d.month)
            by_month[key]["total"] += float(total)
            by_month[key]["lucro"] += float(lucro)
            by_month[key]["qtd"] += 1
            wd = d.weekday()
            by_weekday[wd]["total"] += float(total)
            by_weekday[wd]["qtd"] += 1
        meses_nomes = [
            "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez",
        ]
        historico_mensal = []
        for (y, m), v in sorted(by_month.items()):
            historico_mensal.append({
                "mes_ano": f"{meses_nomes[m - 1]}/{y}",
                "total_vendido": round(v["total"], 2),
                "lucro": round(v["lucro"], 2),
                "num_vendas": v["qtd"],
            })
        if len(historico_mensal) >= 2:
            primeiro = historico_mensal[0]["total_vendido"]
            ultimo = historico_mensal[-1]["total_vendido"]
            variacao_pct = ((ultimo - primeiro) / primeiro * 100) if primeiro > 0 else 0.0
        else:
            variacao_pct = 0.0
        if len(historico_mensal) >= 3:
            media_ultimos_3 = sum(h["total_vendido"] for h in historico_mensal[-3:]) / 3
            previsao_proximo_mes = round(media_ultimos_3, 2)
        else:
            previsao_proximo_mes = historico_mensal[-1]["total_vendido"] if historico_mensal else 0.0
        dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        sazonalidade_dia = [
            {"dia": dias_semana[wd], "total": round(by_weekday[wd]["total"], 2), "vendas": by_weekday[wd]["qtd"]}
            for wd in range(7)
        ]
        mes_ref = start_date.month if start_date else today.month
        sazonalidade_mercado = SAZONALIDADE_MERCADO.get(mes_ref, "Período típico de vendas no varejo.")
        noticias = self._fetch_news_headlines(5)
        return {
            "type": "analise_avancada",
            "data": {
                "periodo_consulta": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "historico_mensal": historico_mensal,
                "tendencia_variacao_pct": round(variacao_pct, 2),
                "previsao_proximo_mes": previsao_proximo_mes,
                "sazonalidade_por_dia_semana": sazonalidade_dia,
                "sazonalidade_mercado_periodo": sazonalidade_mercado,
                "noticias_recentes": noticias,
            },
        }

    def get_initial_analysis(self, db: Session, user_id: Optional[int] = None) -> str:
        """
        Gera a primeira análise ao abrir o Agente de Relatórios: tendência do dia,
        sazonalidade do mês (mercado de roupas femininas), pontos fortes e fracos.
        Trata como especialista em vendas de roupas femininas.
        """
        today = date.today()
        weekday = today.weekday()
        dias_nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        nome_hoje = dias_nomes[weekday]
        oito_semanas_atras = today - relativedelta(weeks=8)
        sales = (
            db.query(Sale.data_venda, Sale.total_vendido)
            .filter(Sale.data_venda >= oito_semanas_atras)
            .filter(Sale.data_venda <= today)
            .filter(Sale.status != "cancelada")
            .all()
        )
        by_weekday = defaultdict(lambda: {"total": 0.0, "qtd": 0})
        for d, total in sales:
            by_weekday[d.weekday()]["total"] += float(total)
            by_weekday[d.weekday()]["qtd"] += 1
        vendas_por_dia = [
            {"dia": dias_nomes[wd], "total": round(by_weekday[wd]["total"], 2), "vendas": by_weekday[wd]["qtd"]}
            for wd in range(7)
        ]
        total_hoje_historico = by_weekday[weekday]["total"]
        media_geral = sum(by_weekday[w]["total"] for w in range(7)) / 7 if any(by_weekday[w]["total"] for w in range(7)) else 0
        inicio_semana = today - relativedelta(days=weekday)
        fim_semana = inicio_semana + relativedelta(days=6)
        contas_semana = (
            db.query(AccountPayable)
            .filter(AccountPayable.data_vencimento >= inicio_semana)
            .filter(AccountPayable.data_vencimento <= fim_semana)
            .filter(AccountPayable.status != "paga")
            .all()
        )
        total_contas_semana = sum(c.valor for c in contas_semana)
        contas_receber_semana = (
            db.query(AccountReceivable)
            .filter(AccountReceivable.data_vencimento >= inicio_semana)
            .filter(AccountReceivable.data_vencimento <= fim_semana)
            .filter(AccountReceivable.status != "recebida")
            .all()
        )
        total_contas_receber_semana = sum(c.valor for c in contas_receber_semana)
        # Contas a pagar em aberto (não pagas) para listar na análise; atualiza status para identificar atrasadas
        contas_pagar_abertas = (
            db.query(AccountPayable)
            .filter(AccountPayable.data_pagamento.is_(None))
            .order_by(AccountPayable.data_vencimento)
            .limit(50)
            .all()
        )
        contas_pagar_abertas_lista = []
        contas_atrasadas_lista = []
        for c in contas_pagar_abertas:
            c.update_status()
            item = {
                "fornecedor": c.fornecedor,
                "valor": round(float(c.valor), 2),
                "data_vencimento": c.data_vencimento.strftime("%d/%m/%Y"),
                "status": c.status,
            }
            contas_pagar_abertas_lista.append(item)
            if c.status == "atrasada":
                contas_atrasadas_lista.append(item)
        # Contas a receber: somente atrasadas e que vencem nos próximos 15 dias
        limite_proximas = today + relativedelta(days=15)
        contas_receber_abertas = (
            db.query(AccountReceivable)
            .filter(AccountReceivable.data_recebimento.is_(None))
            .filter(AccountReceivable.data_vencimento <= limite_proximas)
            .order_by(AccountReceivable.data_vencimento)
            .all()
        )
        contas_receber_atrasadas_lista = []
        contas_receber_proximas_lista = []
        for c in contas_receber_abertas:
            c.update_status()
            item = {
                "cliente": c.cliente,
                "valor": round(float(c.valor), 2),
                "data_vencimento": c.data_vencimento.strftime("%d/%m/%Y"),
                "status": c.status,
            }
            if c.status == "atrasada":
                contas_receber_atrasadas_lista.append(item)
            else:
                contas_receber_proximas_lista.append(item)
        mes_atual = today.month
        dia_do_mes = today.day
        proximo_virada_mes = dia_do_mes >= 25
        proxima_semana_inicio = today + relativedelta(days=1)
        proxima_semana_fim = today + relativedelta(days=7)
        mes_proximo = (today.replace(day=1) + relativedelta(months=1)).month
        sazonalidade_geral = SAZONALIDADE_MERCADO.get(mes_atual, "")
        sazonalidade_moda = SAZONALIDADE_ROUPAS_FEMININAS.get(mes_atual, "")
        sazonalidade_proximo_mes = ""
        if proximo_virada_mes:
            sazonalidade_proximo_mes = SAZONALIDADE_ROUPAS_FEMININAS.get(
                mes_proximo, SAZONALIDADE_MERCADO.get(mes_proximo, "")
            )

        # Agenda pessoal: compromissos de hoje e próximos 7 dias
        agenda_hoje_lista: List[Dict[str, Any]] = []
        agenda_proximos_lista: List[Dict[str, Any]] = []
        try:
            limite_agenda = today + relativedelta(days=7)
            q = db.query(PersonalAgenda).filter(
                PersonalAgenda.data >= today, PersonalAgenda.data <= limite_agenda
            )
            if user_id is not None:
                q = q.filter(PersonalAgenda.user_id == user_id)
            compromissos = q.order_by(PersonalAgenda.data, PersonalAgenda.hora).limit(100).all()
            for c in compromissos:
                item = {
                    "titulo": c.titulo,
                    "descricao": c.descricao or "",
                    "data": c.data.strftime("%d/%m/%Y"),
                    "hora": c.hora or "",
                }
                if c.data == today:
                    agenda_hoje_lista.append(item)
                else:
                    agenda_proximos_lista.append(item)
        except Exception:
            # Em caso de erro na agenda, apenas não incluir no payload
            agenda_hoje_lista = []
            agenda_proximos_lista = []
        payload = {
            "data_hoje": today.strftime("%d/%m/%Y"),
            "dia_do_mes": dia_do_mes,
            "mes_atual_numero": mes_atual,
            "dia_semana_hoje": nome_hoje,
            "proximo_virada_mes": proximo_virada_mes,
            "proxima_semana_inicio": proxima_semana_inicio.strftime("%d/%m/%Y"),
            "proxima_semana_fim": proxima_semana_fim.strftime("%d/%m/%Y"),
            "sazonalidade_proximo_mes": sazonalidade_proximo_mes,
            "vendas_por_dia_semana_ultimas_8_semanas": vendas_por_dia,
            "total_historico_no_mesmo_dia_semana": round(total_hoje_historico, 2),
            "media_diaria_historico": round(media_geral, 2),
            "contas_a_pagar_esta_semana": round(total_contas_semana, 2),
            "quantidade_contas_semana": len(contas_semana),
            "contas_a_receber_esta_semana": round(total_contas_receber_semana, 2),
            "quantidade_contas_receber_semana": len(contas_receber_semana),
            "sazonalidade_mercado_mes": sazonalidade_geral,
            "sazonalidade_moda_feminina_mes": sazonalidade_moda,
            "inicio_semana": inicio_semana.strftime("%d/%m"),
            "fim_semana": fim_semana.strftime("%d/%m"),
            "contas_a_pagar_abertas": contas_pagar_abertas_lista,
            "contas_a_pagar_em_atraso": contas_atrasadas_lista,
            "contas_a_receber_em_atraso": contas_receber_atrasadas_lista,
            "contas_a_receber_proximas_15_dias": contas_receber_proximas_lista,
            "agenda_hoje": agenda_hoje_lista,
            "agenda_proximos_7_dias": agenda_proximos_lista,
            "link_contas_pagar": "/5_Contas_a_Pagar".strip(),
            "link_contas_pagar_atraso": "/5_Contas_a_Pagar?filtro=atraso".strip(),
            "link_contas_receber_atraso": "/5_Contas_a_Pagar?tab=receber&filtro=atraso".strip(),
            "link_contas_receber_proximas": "/5_Contas_a_Pagar?tab=receber".strip(),
            "link_agenda": "/12_Agenda?aba=compromissos".strip(),
        }
        if not self.ai_service.is_available():
            return self._initial_analysis_fallback(payload)
        template = PromptConfigManager.get_or_default(
            self.db, KEY_INITIAL_ANALYSIS, DEFAULTS[KEY_INITIAL_ANALYSIS]
        )
        payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        prompt = safe_substitute_prompt(
            template,
            nome_hoje=nome_hoje,
            payload=payload_json,
        )
        try:
            client, error = self.ai_service._get_client()
            if error:
                return self._initial_analysis_fallback(payload)
            config = self.ai_service.config
            provider = config["provider"]
            model = config.get("model", "")
            result = ""
            if provider == "openai":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.6,
                    max_tokens=900,
                )
                result = (r.choices[0].message.content or "").strip()
            elif provider == "gemini":
                r = client.generate_content(prompt)
                result = (r.text or "").strip()
            elif provider == "groq":
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.6,
                    max_tokens=900,
                )
                result = (r.choices[0].message.content or "").strip()
            elif provider == "ollama":
                r = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.6, "num_predict": 900},
                )
                result = (r.get("message", {}).get("content") or "").strip()
            if result:
                result = re.sub(r"\]\(\s+", "](", result)
                agenda_block = self._format_agenda_block(
                    agenda_hoje_lista, agenda_proximos_lista
                )
                if agenda_block and "Compromissos pessoais" not in result:
                    result = result + "\n\n" + agenda_block
                return result
        except Exception:
            pass
        return self._initial_analysis_fallback(payload)

    def _format_agenda_block(
        self,
        agenda_hoje_lista: List[Dict[str, Any]],
        agenda_proximos_lista: List[Dict[str, Any]],
    ) -> str:
        """Retorna o bloco markdown dos compromissos da agenda (ou string vazia se não houver)."""
        if not agenda_hoje_lista and not agenda_proximos_lista:
            return ""
        parts = ["**Compromissos pessoais (agenda):**\n\n"]
        if agenda_hoje_lista:
            parts.append("*Hoje:*\n")
            for a in agenda_hoje_lista:
                hora = a.get("hora") or ""
                hora_txt = f" às {hora}" if hora else ""
                parts.append(f"- {a.get('titulo', '')}{hora_txt} — {a.get('descricao', '')}\n")
            parts.append("\n")
        if agenda_proximos_lista:
            parts.append("*Próximos 7 dias:*\n")
            for a in agenda_proximos_lista:
                hora = a.get("hora") or ""
                hora_txt = f" às {hora}" if hora else ""
                parts.append(f"- {a.get('data', '')} — {a.get('titulo', '')}{hora_txt} — {a.get('descricao', '')}\n")
        return "".join(parts)

    def _initial_analysis_fallback(self, payload: Dict[str, Any]) -> str:
        """Fallback quando a IA não está disponível."""
        bloco = (
            f"## Análise do dia – {payload.get('data_hoje', '')} ({payload.get('dia_semana_hoje', '')})\n\n"
            f"**Tendência (últimas 8 semanas):** No mesmo dia da semana o histórico de vendas soma "
            f"{format_currency(payload.get('total_historico_no_mesmo_dia_semana', 0))}; "
            f"média diária {format_currency(payload.get('media_diaria_historico', 0))}.\n\n"
            f"**Sazonalidade do mês:** {payload.get('sazonalidade_moda_feminina_mes', payload.get('sazonalidade_mercado_mes', ''))}\n\n"
            f"**Contas a pagar esta semana** ({payload.get('inicio_semana', '')} a {payload.get('fim_semana', '')}): "
            f"{format_currency(payload.get('contas_a_pagar_esta_semana', 0))} ({payload.get('quantidade_contas_semana', 0)} títulos).\n\n"
            f"**Contas a receber (fiado) esta semana:** "
            f"{format_currency(payload.get('contas_a_receber_esta_semana', 0))} ({payload.get('quantidade_contas_receber_semana', 0)} títulos).\n\n"
        )
        contas_abertas = payload.get("contas_a_pagar_abertas") or []
        contas_atrasadas = payload.get("contas_a_pagar_em_atraso") or []
        if contas_atrasadas:
            bloco += "**⚠️ Em atraso:**\n\n"
            for i, c in enumerate(contas_atrasadas, 1):
                bloco += f"{i}. **{c.get('fornecedor', '')}** — {format_currency(c.get('valor', 0))} — Vencimento: {c.get('data_vencimento', '')}\n"
            bloco += "\n"
        if contas_abertas:
            bloco += "**Contas a pagar (em aberto):**\n\n"
            for i, c in enumerate(contas_abertas, 1):
                atraso = " — *atrasada*" if c.get("status") == "atrasada" else ""
                bloco += f"{i}. **{c.get('fornecedor', '')}** — {format_currency(c.get('valor', 0))} — Vencimento: {c.get('data_vencimento', '')}{atraso}\n"
            bloco += "\n"
        contas_rec_atrasadas = payload.get("contas_a_receber_em_atraso") or []
        contas_rec_proximas = payload.get("contas_a_receber_proximas_15_dias") or []
        if contas_rec_atrasadas:
            bloco += "**⚠️ Contas a receber em atraso (a cobrar):**\n\n"
            for i, c in enumerate(contas_rec_atrasadas, 1):
                bloco += f"{i}. **{c.get('cliente', '')}** — {format_currency(c.get('valor', 0))} — Vencimento: {c.get('data_vencimento', '')}\n"
            bloco += "\n"
        if contas_rec_proximas:
            bloco += "**Contas a receber (próximos 15 dias):**\n\n"
            for i, c in enumerate(contas_rec_proximas, 1):
                bloco += f"{i}. **{c.get('cliente', '')}** — {format_currency(c.get('valor', 0))} — Vencimento: {c.get('data_vencimento', '')}\n"
            bloco += "\n"
        agenda_hoje = payload.get("agenda_hoje") or []
        agenda_proximos = payload.get("agenda_proximos_7_dias") or []
        if agenda_hoje or agenda_proximos:
            bloco += "**Compromissos pessoais (agenda):**\n\n"
            if agenda_hoje:
                bloco += "*Hoje:*\n"
                for a in agenda_hoje:
                    hora = a.get("hora") or ""
                    hora_txt = f" às {hora}" if hora else ""
                    bloco += f"- **{a.get('titulo', '')}**{hora_txt} — {a.get('descricao', '')}\n"
                bloco += "\n"
            if agenda_proximos:
                bloco += "*Próximos 7 dias:*\n"
                for a in agenda_proximos:
                    hora = a.get("hora") or ""
                    hora_txt = f" às {hora}" if hora else ""
                    bloco += f"- **{a.get('data', '')}** — {a.get('titulo', '')}{hora_txt} — {a.get('descricao', '')}\n"
                bloco += "\n"
        if payload.get("proximo_virada_mes") and payload.get("sazonalidade_proximo_mes"):
            bloco += (
                f"**Próxima semana** ({payload.get('proxima_semana_inicio', '')} a {payload.get('proxima_semana_fim', '')}): "
                f"{payload.get('sazonalidade_proximo_mes', '')}\n\n"
            )
        bloco += "*Configure a IA em Administração para uma análise completa com pontos fortes e fracos.*"
        return re.sub(r"\]\(\s+", "](", bloco)

    def format_response(
        self, query_result: Dict, query_analysis: Dict, original_query: str
    ) -> str:
        """Formata a resposta em markdown (com IA ou fallback simples)."""
        if query_result.get("type") == "error":
            return f"**Erro:** {query_result.get('error', 'Erro desconhecido')}"

        query_type = query_result.get("type", "")
        # Resumo/faturamento: sempre formatação fixa para resposta clara e consistente
        if query_type == "resumo_periodo":
            return self._format_response_simple(query_result, query_analysis)

        # Resultado de consulta SQL customizada: texto curto + tabela exibida abaixo
        if query_type == "sql_result":
            data = query_result.get("data", {})
            n = len(data.get("rows") or [])
            return f"**Resultado da consulta** ({n} linha{'s' if n != 1 else ''}). Os dados são exibidos na tabela abaixo."

        if not self.ai_service.is_available():
            return self._format_response_simple(query_result, query_analysis)

        data = query_result.get("data", {})

        data_json = json.dumps(data, default=str, ensure_ascii=False)
        if query_type == "analise_avancada":
            template = PromptConfigManager.get_or_default(
                self.db,
                KEY_FORMAT_RESPONSE_ANALISE_AVANCADA,
                DEFAULTS[KEY_FORMAT_RESPONSE_ANALISE_AVANCADA],
            )
            prompt = safe_substitute_prompt(
                template,
                original_query=original_query,
                data=data_json,
            )
        else:
            template = PromptConfigManager.get_or_default(
                self.db,
                KEY_FORMAT_RESPONSE_GENERIC,
                DEFAULTS[KEY_FORMAT_RESPONSE_GENERIC],
            )
            prompt = safe_substitute_prompt(
                template,
                original_query=original_query,
                query_type=query_type,
                data=data_json,
            )

        try:
            client, error = self.ai_service._get_client()
            if error:
                return self._format_response_simple(query_result, query_analysis)

            config = self.ai_service.config
            provider = config["provider"]
            model = config.get("model", "")

            if provider == "openai":
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                return response.choices[0].message.content
            if provider == "gemini":
                response = client.generate_content(prompt)
                return response.text
            if provider == "groq":
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                return response.choices[0].message.content
            if provider == "ollama":
                response = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.7},
                )
                return response["message"]["content"]
            return self._format_response_simple(query_result, query_analysis)
        except Exception:
            return self._format_response_simple(query_result, query_analysis)

    def _format_response_simple(self, query_result: Dict, query_analysis: Dict) -> str:
        """Formatação simples sem IA (templates por tipo)."""
        query_type = query_result.get("type", "")
        data = query_result.get("data", {})

        if query_type == "resumo_periodo":
            start_iso = data.get("start_date", "")
            end_iso = data.get("end_date", "")
            try:
                start_br = date.fromisoformat(start_iso).strftime("%d/%m/%Y") if start_iso else start_iso
                end_br = date.fromisoformat(end_iso).strftime("%d/%m/%Y") if end_iso else end_iso
            except (ValueError, TypeError):
                start_br, end_br = start_iso, end_iso
            is_single_day = start_iso and end_iso and start_iso == end_iso
            total = data.get("total_vendido", 0) or 0
            lucro = data.get("total_lucro", 0) or 0
            margem = data.get("margem", 0) or 0
            pecas = data.get("total_pecas", 0) or 0
            num_v = data.get("num_vendas", 0) or 0
            ticket = data.get("ticket_medio", 0) or 0
            if is_single_day:
                return (
                    f"### Faturamento do dia ({start_br})\n\n"
                    f"**Faturamento:** {format_currency(total)}\n\n"
                    f"**Lucro:** {format_currency(lucro)}  \n"
                    f"**Margem:** {margem:.1f}%\n\n"
                    f"**Peças vendidas:** {pecas:.0f}  \n"
                    f"**Número de vendas:** {num_v}  \n"
                    f"**Ticket médio:** {format_currency(ticket)}"
                )
            return (
                f"### Resumo do período ({start_br} a {end_br})\n\n"
                f"**Faturamento:** {format_currency(total)}\n\n"
                f"**Lucro:** {format_currency(lucro)}  \n"
                f"**Margem:** {margem:.1f}%\n\n"
                f"**Peças vendidas:** {pecas:.0f}  \n"
                f"**Número de vendas:** {num_v}  \n"
                f"**Ticket médio:** {format_currency(ticket)}"
            )
        if query_type == "produtos_mais_vendidos":
            items = data.get("items", [])
            lines = [
                f"- {i.get('nome', '')} (cód. {i.get('codigo', '')}): {i.get('quantidade', 0):.0f} un., "
                f"receita {format_currency(i.get('receita', 0))}, lucro {format_currency(i.get('lucro', 0))}"
                for i in items[:10]
            ]
            period = f"{data.get('start_date', '')} a {data.get('end_date', '')}"
            return f"**Produtos mais vendidos** ({period})\n\n" + "\n".join(lines or ["Nenhuma venda no período."])
        if query_type == "valor_estoque":
            return (
                "**Valor do estoque (atual)**\n\n"
                f"- **Estoque a custo:** {format_currency(data.get('valor_estoque_custo', 0))}\n"
                f"- **Estoque a venda:** {format_currency(data.get('valor_estoque_venda', 0))}"
            )
        if query_type == "entradas_estoque":
            entradas = data.get("entradas", [])
            lines = [
                f"- {e.get('data_entrada', '')} | {e.get('codigo', '')} {e.get('nome', '')} | {e.get('quantidade', 0):.0f} un."
                for e in entradas[:20]
            ]
            return (
                f"**Entradas de estoque** ({data.get('start_date', '')} a {data.get('end_date', '')})\n\n"
                f"Total de unidades: {data.get('total_unidades', 0):.0f}\n\n"
                + "\n".join(lines or ["Nenhuma entrada no período."])
            )
        if query_type == "sessoes_caixa":
            sessoes = data.get("sessoes", [])
            lines = [
                f"- Sessão {s.get('id')}: abertura {s.get('data_abertura')}, "
                f"total vendas {format_currency(s.get('total_vendas_sessao', 0))}"
                for s in sessoes
            ]
            return (
                f"**Sessões de caixa** ({data.get('start_date', '')} a {data.get('end_date', '')})\n\n"
                + "\n".join(lines or ["Nenhuma sessão no período."])
            )
        if query_type == "contas_pagar":
            contas = data.get("contas", [])
            lines = [
                f"- {c.get('fornecedor')}: venc. {c.get('data_vencimento')}, {format_currency(c.get('valor', 0))} ({c.get('status')})"
                for c in contas
            ]
            return (
                f"**Contas a pagar** ({data.get('start_date', '')} a {data.get('end_date', '')})\n\n"
                f"Total em aberto: {format_currency(data.get('total_abertas', 0))} | "
                f"Total pagas: {format_currency(data.get('total_pagas', 0))}\n\n"
                + "\n".join(lines or ["Nenhuma conta no período."])
            )
        if query_type == "contas_receber":
            contas = data.get("contas", [])
            lines = [
                f"- {c.get('cliente')}: venc. {c.get('data_vencimento')}, {format_currency(c.get('valor', 0))} ({c.get('status')})"
                for c in contas
            ]
            return (
                f"**Contas a receber (fiado)** ({data.get('start_date', '')} a {data.get('end_date', '')})\n\n"
                f"Total em aberto: {format_currency(data.get('total_abertas', 0))} | "
                f"Total recebidas: {format_currency(data.get('total_recebidas', 0))}\n\n"
                + "\n".join(lines or ["Nenhuma conta no período."])
            )
        if query_type == "analise_avancada":
            per = data.get("periodo_consulta", {})
            start = per.get("start", "")
            end = per.get("end", "")
            hist = data.get("historico_mensal", [])
            tend = data.get("tendencia_variacao_pct", 0)
            prev = data.get("previsao_proximo_mes", 0)
            saz_mercado = data.get("sazonalidade_mercado_periodo", "")
            noticias = data.get("noticias_recentes", [])
            lines_hist = [f"- {h.get('mes_ano', '')}: {format_currency(h.get('total_vendido', 0))} ({h.get('num_vendas', 0)} vendas)" for h in hist[-6:]]
            lines_news = [f"- {n.get('title', '')}" for n in noticias[:3]]
            return (
                f"**Análise avançada** ({start} a {end})\n\n"
                f"**Tendência (últimos 12 meses):** {tend:+.1f}%\n\n"
                f"**Previsão próximo mês (média recente):** {format_currency(prev)}\n\n"
                f"**Histórico mensal (últimos meses):**\n" + "\n".join(lines_hist or ["Sem dados."]) + "\n\n"
                f"**Sazonalidade do mercado (período):** {saz_mercado}\n\n"
                + ("**Notícias recentes (economia):**\n" + "\n".join(lines_news) + "\n" if lines_news else "")
            )
        return f"**Resultado:** {query_type}\n\nDados disponíveis."
