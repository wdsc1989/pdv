"""
Serviço MCP para extração de dados no PDV.
Extrai dados por entidade: contas_pagar, contas_receber, agenda, relatorio.
Modo híbrido: para INSERT em contas, tenta IA primeiro (melhor clareza); fallback em regex.
"""
import json
import re
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from mcp.schemas import ExtractResponse


class MCPExtractor:
    """
    Extrai dados estruturados do texto conforme action e entity.
    Usa IA para INSERT em contas quando disponível (melhor interpretação e validação).
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

    def extract(
        self,
        text: str,
        action: str,
        entity: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExtractResponse:
        """
        Extrai dados do texto baseado na ação e entidade.
        """
        text_lower = (text or "").lower()
        context = context or {}

        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        confidence = 0.0

        if entity in ("contas_pagar", "contas_receber"):
            data, missing_fields, confidence = self._extract_contas(
                text, text_lower, action, entity
            )
        elif entity == "agenda":
            data, missing_fields, confidence = self._extract_agenda(
                text, text_lower, action
            )
        elif entity == "relatorio":
            data, missing_fields, confidence = self._extract_relatorio(text_lower)
        else:
            data, missing_fields, confidence = self._extract_contas(
                text, text_lower, action, "contas_pagar"
            )

        return ExtractResponse(
            data=data,
            confidence=confidence,
            missing_fields=missing_fields,
        )

    def _extract_contas(
        self,
        text: str,
        text_lower: str,
        action: str,
        entity: str,
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai dados para contas a pagar/receber. INSERT: tenta IA primeiro."""
        if action == "INSERT":
            result = self._extract_contas_insert_with_ai(text.strip(), entity)
            if result is not None:
                return result
            return self._extract_contas_insert(text_lower, entity)
        if action == "UPDATE":
            return self._extract_contas_update(text, text_lower, entity)
        if action == "DELETE":
            return self._extract_contas_delete(text_lower)
        if action == "LIST":
            return self._extract_contas_list_filters(text_lower)
        return {}, [], 0.0

    def _extract_contas_insert_with_ai(
        self, text: str, entity: str
    ) -> Optional[Tuple[Dict[str, Any], List[str], float]]:
        """
        Extrai dados de INSERT contas via IA. Retorna None se IA indisponível ou falha.
        Garante fornecedor/cliente e descrição claros (ex.: "conta de luz 100 reais dia 15"
        → fornecedor "Luz", descricao "Conta de luz", data_vencimento no mês atual).
        """
        ai = self._get_ai_service()
        if not ai.is_available():
            return None
        name_field = "fornecedor" if entity == "contas_pagar" else "cliente"
        hoje = date.today()
        prompt = f"""Extraia do texto do usuário os dados para cadastro de uma conta ({entity}).
Regras:
- valor: número (obrigatório). Ex.: 100, 250.50
- {name_field}: nome do credor/serviço ou cliente, SEM incluir valor nem data. Ex.: "conta de luz 100 reais dia 15" → fornecedor "Luz" (não "Luz 100 Reais Dia 15")
- data_vencimento: data no formato YYYY-MM-DD. Se o usuário disser só "dia 15" ou "dia 8", use o mês e ano atuais (hoje é {hoje.isoformat()}).
- descricao: opcional; pode ser "Conta de [nome]" quando fizer sentido (ex.: "Conta de luz")

Texto do usuário: "{text}"

Responda APENAS com um JSON válido, sem texto antes ou depois, com as chaves: "valor", "{name_field}", "data_vencimento", "descricao" (esta pode ser string vazia ou omitida).
Exemplo: {{"valor": 100, "{name_field}": "Luz", "data_vencimento": "{hoje.year}-{hoje.month:02d}-15", "descricao": "Conta de luz"}}"""
        content, error = ai.complete(
            prompt, temperature=0.2, max_tokens=300, json_mode=True
        )
        if error or not content:
            return None
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
            content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            return None
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []

        try:
            if "valor" in raw and raw["valor"] is not None:
                data["valor"] = float(raw["valor"])
            else:
                missing_fields.append("valor")
        except (ValueError, TypeError):
            missing_fields.append("valor")

        nome = (raw.get(name_field) or "").strip() if isinstance(raw.get(name_field), str) else ""
        if nome:
            if entity == "contas_pagar":
                data["fornecedor"] = nome.title()
            else:
                data["cliente"] = nome.title()
        else:
            missing_fields.append(name_field)

        dvenc = raw.get("data_vencimento")
        if dvenc:
            try:
                if isinstance(dvenc, str):
                    data["data_vencimento"] = date.fromisoformat(dvenc).isoformat()
                else:
                    data["data_vencimento"] = str(dvenc)
            except (ValueError, TypeError):
                missing_fields.append("data_vencimento")
        else:
            missing_fields.append("data_vencimento")

        desc = (raw.get("descricao") or "").strip() if isinstance(raw.get("descricao"), str) else ""
        if desc:
            data["descricao"] = desc

        required = 3
        found = sum(1 for _ in ["valor", name_field, "data_vencimento"] if _ not in missing_fields)
        confidence = found / required if required > 0 else 0.0
        return data, missing_fields, min(1.0, confidence + 0.1)

    def _extract_contas_insert(
        self, text_lower: str, entity: str
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai dados para INSERT de contas."""
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        found = 0
        required = 3

        # Valor (extrair antes do nome para não confundir "de 500 para" com nome)
        valor_patterns = [
            r"valor[:\s]+r\$\s*([\d,\.]+)",
            r"r\$\s*([\d,\.]+)",
            r"(?:divida|d[ií]vida)\s+de\s+([\d,\.]+)",  # "divida de 960"
            r"de\s+([\d,\.]+)\s+para\s+",  # "conta de 500 para Willian"
            r"de\s+([\d,\.]+)\s*,",        # "divida de 960, moto"
            r"([\d,\.]+)\s+para\s+",       # "500 para Willian"
            r"([\d,\.]+)\s*reais",
            r"([\d,\.]+)\s*r\$",
        ]
        for pattern in valor_patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    valor_str = match.group(1).replace(",", ".")
                    data["valor"] = float(valor_str)
                    found += 1
                except (ValueError, TypeError):
                    pass
                break
        if "valor" not in data:
            missing_fields.append("valor")

        # Fornecedor (contas_pagar) ou Cliente (contas_receber)
        # "conta de luz 100 reais dia 15" → só "luz" (parar antes de número/reais/dia N)
        name_patterns = [
            r"[\d,\.]+\s*,\s*([^,\.]+?)\s*,\s*todo\s+dia",  # "960, moto, todo dia 15" → moto
            r"para\s+([^,\.]+?)(?:\s+venc|\s+dia|\s+data|$)",  # "de 500 para Willian" → Willian
            r"conta\s+de\s+([a-záàâãéêíóôõúç\s]+?)(?=\s+\d|\s+reais|\s+r\$|\s+dia\s+\d|$)",  # conta de luz 100... → luz
            r"fornecedor[:\s]+([^,\.]+)",
            r"credor[:\s]+([^,\.]+)",
            r"cliente[:\s]+([^,\.]+)",
            r"receber\s+de\s+([^,\.]+)",
            r"de\s+([^,\.]+)",  # "conta de João" — só usar se não for número (evitar "de 500")
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).strip().title()
                # não usar número como nome (ex.: "de 500" não é fornecedor)
                if re.match(r"^[\d,\.]+$", name.replace(" ", "")):
                    continue
                if entity == "contas_pagar":
                    data["fornecedor"] = name
                else:
                    data["cliente"] = name
                found += 1
                break
        if "fornecedor" not in data and "cliente" not in data:
            missing_fields.append("fornecedor" if entity == "contas_pagar" else "cliente")

        # Bulk: "todo dia 15" (recorrência mensal)
        todo_dia = re.search(r"todo\s+dia\s+(\d{1,2})", text_lower)
        if todo_dia:
            try:
                dia_bulk = int(todo_dia.group(1))
                if 1 <= dia_bulk <= 31:
                    hoje = date.today()
                    data["bulk"] = {"dia": dia_bulk, "mes_inicio": 1, "mes_fim": 12, "ano": hoje.year}
                    data["data_vencimento"] = date(hoje.year, 1, min(dia_bulk, 31)).isoformat()  # placeholder para validação
                    found += 1
            except (ValueError, TypeError):
                pass

        # Data de vencimento (data única, se ainda não tem bulk)
        if "data_vencimento" not in data and "bulk" not in data:
            data_patterns = [
                r"vencimento[:\s]+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
                r"data[:\s]+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
                r"dia\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
                r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
            ]
            for pattern in data_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    try:
                        dia, mes, ano = match.groups()[:3]
                        if len(ano) == 2:
                            ano = "20" + ano
                        data["data_vencimento"] = date(
                            int(ano), int(mes), int(dia)
                        ).isoformat()
                        found += 1
                    except (ValueError, TypeError):
                        pass
                    break
            # "dia 15" ou "dia 8" sem mês/ano: assume mês e ano atuais
            if "data_vencimento" not in data:
                dia_only = re.search(r"dia\s+(\d{1,2})(?:\s|$|,|\.|/)", text_lower)
                if dia_only:
                    try:
                        dia_num = int(dia_only.group(1))
                        if 1 <= dia_num <= 31:
                            hoje = date.today()
                            ultimo = monthrange(hoje.year, hoje.month)[1]
                            dia_final = min(dia_num, ultimo)
                            data["data_vencimento"] = date(hoje.year, hoje.month, dia_final).isoformat()
                            found += 1
                    except (ValueError, TypeError):
                        pass
        if "data_vencimento" not in data and "bulk" not in data:
            missing_fields.append("data_vencimento")

        # Descrição (opcional): "conta de luz 100..." → "Conta de luz"; "960, moto, todo" → moto
        if "descricao" not in data:
            m = re.search(r"[\d,\.]+\s*,\s*([^,\.]+?)\s*,\s*todo\s+dia", text_lower)
            if m:
                data["descricao"] = m.group(1).strip().title()
        if "descricao" not in data:
            # "conta de luz 100 reais dia 15" → só "luz", descricao = "Conta de luz"
            m_conta = re.search(
                r"conta\s+de\s+([a-záàâãéêíóôõúç\s]+?)(?=\s+\d|\s+reais|\s+r\$|\s+dia\s+\d|$)",
                text_lower,
            )
            if m_conta:
                nome_serv = m_conta.group(1).strip().title()
                data["descricao"] = f"Conta de {nome_serv}" if nome_serv else ""
        for pattern in [
            r"descri[çc][ãa]o[:\s]+([^\.]+)",
            r"conta\s+de\s+([a-záàâãéêíóôõúç\s]+?)(?=\s+\d|\s+reais|\s+r\$|\s+dia\s+\d|$)",  # mesmo critério: só nome
            r"([^,\.]+)\s*,\s*(?:r\$|valor)",
        ]:
            match = re.search(pattern, text_lower)
            if match and "descricao" not in data:
                raw = match.group(1).strip().title()
                if "conta de " in text_lower and pattern == r"conta\s+de\s+([a-záàâãéêíóôõúç\s]+?)(?=\s+\d|\s+reais|\s+r\$|\s+dia\s+\d|$)":
                    data["descricao"] = f"Conta de {raw}" if raw else ""
                else:
                    data["descricao"] = raw
                break

        # Observação (opcional)
        obs_match = re.search(r"obs[:\s]+([^\.]+)", text_lower)
        if obs_match:
            data["observacao"] = obs_match.group(1).strip()

        confidence = found / required if required > 0 else 0.0
        return data, missing_fields, confidence

    def _extract_contas_update(
        self, text: str, text_lower: str, entity: str
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai dados para UPDATE (incl. dar baixa)."""
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        # ID ou nome para baixa
        id_match = re.search(r"id\s*[:=]?\s*(\d+)", text_lower)
        if id_match:
            data["id"] = int(id_match.group(1))
        else:
            # Dar baixa por nome: extrair fornecedor/cliente
            insert_data, _, _ = self._extract_contas_insert(text_lower, entity)
            data.update(insert_data)
            if "fornecedor" not in data and "cliente" not in data:
                missing_fields.append("fornecedor" if entity == "contas_pagar" else "cliente")
        confidence = 0.8 if data else 0.0
        return data, missing_fields, confidence

    def _extract_contas_delete(self, text_lower: str) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai dados para DELETE."""
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        id_match = re.search(r"id\s*[:=]?\s*(\d+)", text_lower)
        if id_match:
            data["id"] = int(id_match.group(1))
            return data, [], 0.9
        missing_fields.append("id")
        return data, missing_fields, 0.0

    def _extract_contas_list_filters(
        self, text_lower: str
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai filtros para LIST de contas."""
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        confidence = 0.5
        pattern = re.compile(
            r"de\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\s+at[ée]\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})"
        )
        match = pattern.search(text_lower)
        if match:
            try:
                dia1, mes1, ano1, dia2, mes2, ano2 = match.groups()
                if len(ano1) == 2:
                    ano1 = "20" + ano1
                if len(ano2) == 2:
                    ano2 = "20" + ano2
                data["data_inicial"] = date(
                    int(ano1), int(mes1), int(dia1)
                ).isoformat()
                data["data_final"] = date(
                    int(ano2), int(mes2), int(dia2)
                ).isoformat()
                confidence = 0.8
            except (ValueError, TypeError):
                pass
        if "pendente" in text_lower or "aberta" in text_lower:
            data["status"] = "aberta"
        elif "pago" in text_lower or "pagas" in text_lower:
            data["status"] = "paga"
        elif "vencido" in text_lower or "vencidas" in text_lower:
            data["status"] = "atrasada"
        return data, missing_fields, confidence

    def _extract_agenda(
        self, text: str, text_lower: str, action: str
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai dados para agenda."""
        if action != "INSERT":
            return {}, [], 0.0
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        found = 0
        required = 2  # titulo e data

        # Título curto: "cadastre X para amanhã" → X = título (nunca incluir "para" no título)
        title_patterns = [
            r"cadastr(?:e|ar)\s+(.+?)\s+para\s+",  # captura só até " para " (ex.: "dentista" em "dentista para amanhã")
            r"agendar\s+(.+?)\s+para\s+",
            r"cadastr(?:e|ar)\s+([^\s,\.]+)\s+(?:dia|amanh)",
            r"agendar\s+([^\s,\.]+(?:\s+[^\s,\.]+)?)\s+(?:dia|amanh|segunda|terça|quarta|quinta|sexta|sábado|domingo)?",
            r"(?:marca|marcar)\s+([^\s,\.]+(?:\s+[^\s,\.]+)?)\s+(?:para|amanh|dia|\d|às?\s*\d)?",
            r"reuni[ãa]o\s+[:\s]*([^,\.]+?)(?:\s+para|\s+dia|\s+amanh|\s+às?\s*\d|$)",
            r"compromisso\s+[:\s]*([^,\.]+?)(?:\s+para|\s+dia|\s+amanh|$)",
            r"evento\s+[:\s]*([^,\.]+)",
            r"lembrete\s+[:\s]*([^,\.]+)",
            r"titulo[:\s]+([^,\.]+)",
            r"(?:dentista|consulta|entrega|reunião)\s*[:\s]*([^,\.]+?)(?:\s+para|\s+dia|\s+amanh|\s+às?\s*\d|$)",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                tit = match.group(1).strip()
                # não usar "para", "dia", "amanhã" etc. como título
                if len(tit) > 2 and tit.lower() not in ("para", "dia", "amanhã", "amanha", "o", "a"):
                    data["titulo"] = tit.title()
                    found += 1
                    break
        if "titulo" not in data:
            # Fallback: remover verbos de comando e usar o trecho até "para"/"dia"/hora como título
            first = (text or "").strip()
            for prefix in ("cadastre ", "cadastrar ", "agendar ", "marcar ", "marca "):
                if first.lower().startswith(prefix):
                    first = first[len(prefix):].strip()
                    break
            for sep in (" para ", " para amanhã", " para dia", " amanhã", " às ", " as ", " dia "):
                if sep in first.lower():
                    first = first.split(sep)[0].strip()
                    break
            for sep in (",", ".", "\n"):
                if sep in first:
                    first = first.split(sep)[0].strip()
                    break
            if len(first) > 50:
                first = first[:50].strip()
            if len(first) > 2:
                data["titulo"] = first.title() or "Compromisso"
                found += 1
            else:
                missing_fields.append("titulo")

        # Data
        today = date.today()
        from datetime import timedelta
        if "amanh" in text_lower:
            d = today + timedelta(days=1)
            data["data"] = d.isoformat()
            found += 1
        elif "hoje" in text_lower:
            data["data"] = today.isoformat()
            found += 1
        else:
            data_patterns = [
                r"dia\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
                r"data[:\s]+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
                r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
            ]
            for pattern in data_patterns:
                match = re.search(pattern, text_lower)
                if match and match.groups():
                    try:
                        dia, mes, ano = match.groups()[:3]
                        if len(ano) == 2:
                            ano = "20" + ano
                        data["data"] = date(
                            int(ano), int(mes), int(dia)
                        ).isoformat()
                        found += 1
                    except (ValueError, TypeError):
                        pass
                    break
        if "data" not in data:
            missing_fields.append("data")

        # Hora (opcional)
        hora_match = re.search(r"(\d{1,2})[h:](\d{0,2})", text_lower)
        if hora_match:
            h, m = hora_match.groups()
            data["hora"] = f"{int(h):02d}:{int(m or 0):02d}"

        # Descrição (opcional): só quando o usuário informar explicitamente "descrição: ..."
        # Caso contrário não preencher; o agente perguntará se deseja adicionar.
        desc_match = re.search(r"descri[çc][ãa]o[:\s]+([^\.]+)", text_lower)
        if desc_match:
            data["descricao"] = desc_match.group(1).strip()

        confidence = found / required if required > 0 else 0.0
        return data, missing_fields, confidence

    def _extract_relatorio(
        self, text_lower: str
    ) -> Tuple[Dict[str, Any], List[str], float]:
        """Extrai período e tipo para relatório."""
        data: Dict[str, Any] = {}
        missing_fields: List[str] = []
        confidence = 0.5
        today = date.today()

        # data_type
        if "venda" in text_lower or "vendas" in text_lower:
            data["data_type"] = "vendas"
        elif "estoque" in text_lower:
            data["data_type"] = "estoque"
        elif "conta" in text_lower and "pagar" in text_lower:
            data["data_type"] = "contas_pagar"
        elif "conta" in text_lower and "receber" in text_lower:
            data["data_type"] = "contas_receber"
        elif "agenda" in text_lower or "compromisso" in text_lower or "agendamento" in text_lower:
            data["data_type"] = "agenda"
        else:
            data["data_type"] = "vendas"

        # Período: mês, semana, hoje, ontem, datas
        from datetime import timedelta
        if "hoje" in text_lower:
            data["data_inicial"] = today.isoformat()
            data["data_final"] = today.isoformat()
            confidence = 0.8
        elif "ontem" in text_lower:
            d = today - timedelta(days=1)
            data["data_inicial"] = d.isoformat()
            data["data_final"] = d.isoformat()
            confidence = 0.8
        elif "semana" in text_lower:
            start = today - timedelta(days=today.weekday())
            data["data_inicial"] = start.isoformat()
            data["data_final"] = today.isoformat()
            confidence = 0.75
        elif "mês" in text_lower or "mes" in text_lower:
            start = today.replace(day=1)
            data["data_inicial"] = start.isoformat()
            data["data_final"] = today.isoformat()
            confidence = 0.8
        else:
            pattern = re.compile(
                r"(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\s+at[ée]\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})"
            )
            match = pattern.search(text_lower)
            if match:
                try:
                    dia1, mes1, ano1, dia2, mes2, ano2 = match.groups()
                    if len(ano1) == 2:
                        ano1 = "20" + ano1
                    if len(ano2) == 2:
                        ano2 = "20" + ano2
                    data["data_inicial"] = date(
                        int(ano1), int(mes1), int(dia1)
                    ).isoformat()
                    data["data_final"] = date(
                        int(ano2), int(mes2), int(dia2)
                    ).isoformat()
                    confidence = 0.85
                except (ValueError, TypeError):
                    pass

        return data, missing_fields, confidence
