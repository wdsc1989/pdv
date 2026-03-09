"""
Serviço MCP para detecção de intenção no PDV.

Propósito do sistema: PDV com módulos de vendas, estoque, caixa, contas a pagar,
contas a receber, agenda pessoal e relatórios. O detector classifica a intenção
(action + entity) para que cada agente (Contas, Agenda, Relatórios) processe corretamente.

Retorna action (INSERT, UPDATE, DELETE, LIST, REPORT, OTHER) e entity
(contas_pagar, contas_receber, agenda, relatorio).
Modo híbrido: regras primeiro; se confiança baixa ou OTHER, tenta classificação por IA.
"""
import json
import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from mcp.schemas import DetectResponse

# Abaixo deste limiar ou quando action == OTHER, o detector tenta classificação por IA
CONFIDENCE_LLM_THRESHOLD = 0.8
VALID_ENTITIES = frozenset({"contas_pagar", "contas_receber", "agenda", "relatorio"})
VALID_ACTIONS = frozenset({"INSERT", "UPDATE", "DELETE", "LIST", "REPORT", "OTHER"})

# Padrões por entidade para classificação por conteúdo (página ausente ou desambiguação)
KEYWORDS_AGENDA = re.compile(
    r"(agendamento|agendar|cadastrar\s+compromisso|marcar\s+reuni[ãa]o|compromisso|"
    r"reuni[ãa]o|evento|lembrete|dentista|consulta\s+m[eé]dica|às\s+\d|amanh[ãa]|dia\s+\d)"
)
KEYWORDS_REPORT = re.compile(
    r"(quanto\s+vendi|faturamento|venda\s+da\s+semana|vendas\s+do\s+m[eê]s|lucro\s+do\s+m[eê]s|"
    r"ticket\s+m[eé]dio|produtos\s+mais\s+vendidos|valor\s+estoque|entradas\s+estoque|"
    r"sess[oõ]es\s+caixa|tenho\s+agendamento|meus\s+compromissos|o\s+que\s+tenho\s+na\s+agenda|"
    r"resumo|relat[oó]rio|per[íi]odo|mês|mes|semana|hoje|ontem|an[aá]lise|previs[aã]o|"
    r"tend[eê]ncia|sazonalidade)"
)
KEYWORDS_CONTAS_PAGAR = re.compile(
    r"(conta\s+a\s+pagar|divida|d[ií]vida|registrar\s+conta|cadastrar\s+conta|"
    r"conta\s+de\s+luz|aluguel|fornecedor|pagar\s+[aà]|conta\s+de\s+[^\s,]+)"
)
# "de 500 para Nome" = conta a receber; "conta de 500 para Nome" = conta a pagar (não usar só 'para Nome')
# "Nome valor de N" no início = conta a receber (ex.: "Willian valor de 500", "Lucia valor de 250")
KEYWORDS_CONTAS_RECEBER = re.compile(
    r"(conta\s+a\s+receber|receber\s+de|fiado|a\s+receber|cliente\s+deve|quem\s+me\s+deve|"
    r"cliente\s+[^\s,\.]+|(?<!conta\s)de\s+[\d,\.]+\s+para\s+[^\s,\.\d]|"
    r"^\s*[A-Za-zà-úÀ-Ú][a-zà-ú]*\s+valor\s+de\s+[\d,\.])"
)


class MCPDetector:
    """
    Detecta a intenção do usuário a partir do texto, alinhado ao propósito do sistema
    (vendas, estoque, caixa, contas a pagar/receber, agenda, relatórios).
    Usado por Contas, Agenda e Relatórios; classifica por conteúdo quando a página
    é ausente ou para desambiguar (ex.: "tenho agendamento?" na página Início).
    Em modo híbrido, usa IA quando as regras têm confiança baixa ou retornam OTHER.
    """

    def __init__(self, db: Session):
        self.db = db
        self._ai_service = None

    def _get_ai_service(self):
        """AIService lazy (usa mesma config dos agentes)."""
        if self._ai_service is None:
            from services.ai_service import AIService
            self._ai_service = AIService(self.db)
        return self._ai_service

    def _detect_with_llm(
        self, text: str, context: Dict[str, Any]
    ) -> Optional[DetectResponse]:
        """
        Classifica intenção via IA. Retorna DetectResponse válido ou None em falha.
        """
        ai = self._get_ai_service()
        if not ai.is_available():
            return None
        pagina = (context.get("pagina") or "").strip()
        system_desc = (
            "Sistema PDV: vendas, estoque, caixa, contas a pagar, contas a receber, "
            "agenda pessoal e relatórios. Classifique a intenção do usuário."
        )
        prompt = f"""{system_desc}

Entidades válidas: contas_pagar, contas_receber, agenda, relatorio.
Ações válidas: INSERT, UPDATE, DELETE, LIST, REPORT, OTHER.

Texto do usuário: "{text}"
Contexto (página atual): "{pagina}"

Responda apenas com um JSON válido no formato: {{"entity": "...", "action": "...", "confidence": 0.0-1.0}}
Sem texto antes ou depois do JSON."""
        content, error = ai.complete(
            prompt, temperature=0.2, max_tokens=150, json_mode=True
        )
        if error or not content:
            return None
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
            content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        entity = (data.get("entity") or "").strip().lower()
        action = (data.get("action") or "").strip().upper()
        confidence = data.get("confidence")
        if entity not in VALID_ENTITIES or action not in VALID_ACTIONS:
            return None
        if isinstance(confidence, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence)))
        else:
            confidence = 0.8
        return DetectResponse(
            action=action,
            entity=entity,
            confidence=confidence,
            extracted_info=None,
        )

    def _detect_by_content(
        self, text_lower: str, context: Optional[Dict[str, Any]]
    ) -> Optional[Tuple[str, str, float]]:
        """
        Classificação por conteúdo: retorna (entity, action, confidence) ou None.
        Ordem: agenda e relatório primeiro; depois contas_receber vs contas_pagar.
        """
        if not text_lower or len(text_lower) < 2:
            return None
        # Consulta à agenda (no Início = relatório que devolve agenda)
        if re.search(
            r"(tenho\s+agendamento|meus\s+compromissos|o\s+que\s+tenho\s+na\s+agenda|"
            r"agenda|o\s+que\s+est[aá]\s+agendado)",
            text_lower,
        ):
            return ("relatorio", "REPORT", 0.85)
        if KEYWORDS_AGENDA.search(text_lower):
            action = "INSERT" if re.search(r"(agendar|cadastrar|marcar|compromisso)", text_lower) else "LIST"
            return ("agenda", action, 0.85)
        if KEYWORDS_REPORT.search(text_lower):
            return ("relatorio", "REPORT", 0.85)
        if KEYWORDS_CONTAS_RECEBER.search(text_lower) and not KEYWORDS_CONTAS_PAGAR.search(text_lower):
            return ("contas_receber", "INSERT", 0.8)
        if KEYWORDS_CONTAS_PAGAR.search(text_lower):
            return ("contas_pagar", "INSERT", 0.8)
        return None

    def detect(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> DetectResponse:
        """
        Detecta a intenção do usuário e retorna action e entity.
        Usa contexto (página) quando presente; senão classifica por conteúdo.
        Se a confiança das regras for baixa ou action for OTHER, tenta classificação por IA.
        Para saber se a interpretação veio da IA, use detect_with_source().
        """
        result, _ = self._detect_result_and_source(text, context)
        return result

    def detect_with_source(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> Tuple[DetectResponse, str]:
        """
        Retorna (DetectResponse, origem) onde origem é "ia" ou "regras",
        indicando se a classificação foi feita pela IA ou pelas regras/padrões.
        """
        result, used_llm = self._detect_result_and_source(text, context)
        return result, "ia" if used_llm else "regras"

    def _detect_result_and_source(
        self, text: str, context: Optional[Dict[str, Any]]
    ) -> Tuple[DetectResponse, bool]:
        """Retorna (DetectResponse, used_llm: bool). Qualquer entrada é detectada por IA quando disponível; fallback para regras."""
        text_lower = (text or "").lower().strip()
        if not text_lower:
            return DetectResponse(
                action="OTHER",
                entity="contas_pagar",
                confidence=0.0,
                extracted_info=None,
            ), False

        context = context or {}
        # Sempre tentar IA primeiro; se retornar resultado válido, usar
        llm_result = self._detect_with_llm(text, context)
        if llm_result is not None:
            # Pós-IA: "fiado" e termos de conta a receber sempre → contas_receber
            # Exceto "conta de N para Nome" = conta a pagar (pagar para alguém)
            if (
                llm_result.entity == "contas_pagar"
                and KEYWORDS_CONTAS_RECEBER.search(text_lower)
                and not re.search(r"conta\s+de\s+[\d,\.]+\s+para\s+", text_lower)
            ):
                # "de N para Nome" = cadastro (INSERT), não atualização
                action_override = llm_result.action
                if re.search(r"de\s+[\d,\.]+\s+para\s+", text_lower):
                    action_override = "INSERT"
                llm_result = DetectResponse(
                    action=action_override,
                    entity="contas_receber",
                    confidence=llm_result.confidence,
                    extracted_info=llm_result.extracted_info,
                )
            return llm_result, True

        # Fallback: regras/padrões quando IA não está configurada ou falhou
        pagina = (context.get("pagina") or "").strip().lower()
        if pagina == "agenda":
            result = self._detect_agenda(text_lower, context)
        elif pagina in ("relatorios", "inicio", "início"):
            content_hint = self._detect_by_content(text_lower, context)
            if content_hint and content_hint[0] == "agenda":
                result = self._detect_agenda(text_lower, context)
            elif content_hint and content_hint[0] == "relatorio":
                result = self._detect_report(text_lower, context)
            elif self._is_report_intent(text_lower):
                result = self._detect_report(text_lower, context)
            else:
                result = self._detect_contas(text_lower, context)
        else:
            content_hint = self._detect_by_content(text_lower, context)
            if content_hint:
                entity, _action, _conf = content_hint
                if entity == "agenda":
                    result = self._detect_agenda(text_lower, context)
                elif entity == "relatorio":
                    result = self._detect_report(text_lower, context)
                else:
                    result = self._detect_contas(text_lower, context)
            else:
                result = self._detect_contas(text_lower, context)
        return result, False

    def _detect_contas(
        self, text_lower: str, context: Optional[Dict[str, Any]]
    ) -> DetectResponse:
        """Detecta intenção para contas a pagar/receber."""
        extracted_info: Dict[str, Any] = {}

        # Dar baixa (marcar como paga/recebida)
        baixa_pagar = re.search(
            r"(marcar\s+como\s+paga?|dar\s+baixa\s+em\s+conta\s+a\s+pagar|paguei|pagar\s+conta)",
            text_lower,
        )
        baixa_receber = re.search(
            r"(marcar\s+como\s+recebida?|dar\s+baixa\s+em\s+conta\s+a\s+receber|recebi\s+de|recebimento)",
            text_lower,
        )
        if baixa_pagar:
            return DetectResponse(
                action="UPDATE",
                entity="contas_pagar",
                confidence=0.9,
                extracted_info={"subtype": "baixa"},
            )
        if baixa_receber:
            return DetectResponse(
                action="UPDATE",
                entity="contas_receber",
                confidence=0.9,
                extracted_info={"subtype": "baixa"},
            )
        # Na página contas_a_pagar, "dar baixa" sem tipo = conta a pagar
        if context.get("pagina") == "contas_a_pagar" and re.search(
            r"dar\s+baixa|marcar\s+como\s+paga", text_lower
        ):
            return DetectResponse(
                action="UPDATE",
                entity="contas_pagar",
                confidence=0.85,
                extracted_info={"subtype": "baixa"},
            )

        # Conta a pagar vs a receber (cadastro)
        conta_receber = re.search(
            r"(conta\s+a\s+receber|receber\s+de\s+[^\s,]+|cliente\s+[^\s,]+|fiado|a\s+receber)",
            text_lower,
        )
        conta_pagar = re.search(
            r"(conta\s+a\s+pagar|pagar\s+[aà]|fornecedor|conta\s+de\s+luz|conta\s+de\s+[^\s,]+|"
            r"divida|d[ií]vida|aluguel|parcela|presta[cç][aã]o|registrar\s+conta|"
            r"cadastrar\s+conta|conta\s+de\s+)",
            text_lower,
        )

        entity = "contas_pagar"
        if conta_receber and not conta_pagar:
            entity = "contas_receber"
        elif conta_pagar:
            entity = "contas_pagar"

        # INSERT
        if re.search(
            r"(adicionar|registrar|criar|cadastrar|inserir|nova?\s+conta|conta\s+de\s+|"
            r"pagar\s+[rR]\$|receber\s+de)",
            text_lower,
        ):
            return DetectResponse(
                action="INSERT",
                entity=entity,
                confidence=0.9,
                extracted_info=extracted_info or None,
            )
        # LIST
        if re.search(
            r"(mostrar|listar|ver|minhas?\s+contas|contas\s+(de|do|pendentes|vencidas|pagas)|quais\s+contas)",
            text_lower,
        ):
            return DetectResponse(
                action="LIST",
                entity=entity,
                confidence=0.85,
                extracted_info=None,
            )
        # UPDATE (editar conta por ID)
        if re.search(
            r"(atualizar|editar|alterar|modificar)\s+(conta\s+)?(id\s*)?\d*",
            text_lower,
        ):
            id_match = re.search(r"id\s*[:=]?\s*(\d+)", text_lower)
            if id_match:
                extracted_info["id"] = int(id_match.group(1))
            return DetectResponse(
                action="UPDATE",
                entity=entity,
                confidence=0.85,
                extracted_info=extracted_info or None,
            )
        # DELETE
        if re.search(
            r"(deletar|excluir|remover|apagar)\s+(conta\s+)?(id\s*)?\d*",
            text_lower,
        ):
            id_match = re.search(r"id\s*[:=]?\s*(\d+)", text_lower)
            if id_match:
                extracted_info["id"] = int(id_match.group(1))
            return DetectResponse(
                action="DELETE",
                entity=entity,
                confidence=0.85,
                extracted_info=extracted_info or None,
            )

        # Texto que parece cadastro (tem valor, data, nome)
        if re.search(r"r\$\s*[\d,\.]+|[\d,\.]+\s*reais", text_lower) or re.search(
            r"\d{1,2}/\d{1,2}/\d{2,4}", text_lower
        ):
            return DetectResponse(
                action="INSERT",
                entity=entity,
                confidence=0.7,
                extracted_info=None,
            )

        return DetectResponse(
            action="OTHER",
            entity=entity,
            confidence=0.3,
            extracted_info=None,
        )

    def _detect_agenda(
        self, text_lower: str, context: Optional[Dict[str, Any]]
    ) -> DetectResponse:
        """Detecta intenção para agenda (compromissos)."""
        if re.search(
            r"(agendamento|agendar|cadastrar\s+compromisso|marcar\s+reuni[ãa]o|marcar\s+"
            r"compromisso|compromisso|reuni[ãa]o|evento|lembrete|dentista|consulta\s+m[eé]dica|"
            r"dia\s+\d|amanh[ãa]|às\s+\d{1,2}h?\d{0,2})",
            text_lower,
        ):
            return DetectResponse(
                action="INSERT",
                entity="agenda",
                confidence=0.9,
                extracted_info=None,
            )
        if re.search(r"(listar|ver|mostrar)\s+(compromissos|agenda|eventos)?", text_lower):
            return DetectResponse(
                action="LIST",
                entity="agenda",
                confidence=0.85,
                extracted_info=None,
            )
        # Texto com data/hora sugere INSERT
        if re.search(r"\d{1,2}/\d{1,2}|\d{1,2}h\d{0,2}|às\s+\d", text_lower):
            return DetectResponse(
                action="INSERT",
                entity="agenda",
                confidence=0.75,
                extracted_info=None,
            )
        return DetectResponse(
            action="OTHER",
            entity="agenda",
            confidence=0.4,
            extracted_info=None,
        )

    def _is_report_intent(self, text_lower: str) -> bool:
        """Verifica se o texto indica pedido de relatório."""
        return bool(
            re.search(
                r"(relat[oó]rio|resumo|vendas\s+de|vendas\s+do|total\s+de\s+vendas|"
                r"faturamento|quanto\s+vendi|venda\s+da\s+semana|lucro\s+do\s+m[eê]s|"
                r"ticket\s+m[eé]dio|produtos\s+mais\s+vendidos|valor\s+estoque|"
                r"entradas\s+estoque|sess[oõ]es\s+caixa|"
                r"tenho\s+agendamento|meus\s+compromissos|agenda\s+hoje|"
                r"estoque|contas\s+a\s+pagar|contas\s+a\s+receber|"
                r"per[íi]odo|mês|mes|semana|hoje|ontem|an[aá]lise|"
                r"previs[aã]o|tend[eê]ncia|sazonalidade)",
                text_lower,
            )
        )

    def _detect_report(
        self, text_lower: str, context: Optional[Dict[str, Any]]
    ) -> DetectResponse:
        """Detecta intenção de relatório."""
        return DetectResponse(
            action="REPORT",
            entity="relatorio",
            confidence=0.85,
            extracted_info=None,
        )
