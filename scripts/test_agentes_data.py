"""
Dados para testes data-driven dos agentes (Contas a pagar, Contas a receber, Agenda, Relatórios).
Gera 100+ casos por domínio com frases base e variantes com erros de digitação.
"""
import unicodedata
from typing import Any, Dict, List, Tuple


def _remove_accents(s: str) -> str:
    """Remove acentos usando NFD e filtrando combining characters."""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

def _typo_variants(text: str) -> List[str]:
    """Gera variantes com typos comuns (sem duplicatas)."""
    out = [text]
    t = text
    # Sem acentos
    t2 = _remove_accents(t)
    if t2 != t:
        out.append(t2)
    # cadastrar -> cadastra, registrar -> registra
    for a, b in [("cadastrar ", "cadastra "), ("registrar ", "registra "), ("agendar ", "agenda ")]:
        if a in t and t.replace(a, b, 1) not in out:
            out.append(t.replace(a, b, 1))
    # reais -> real (uma vez)
    if " reais " in t and t.replace(" reais ", " real ", 1) not in out:
        out.append(t.replace(" reais ", " real ", 1))
    # R$ -> r$
    if "R$" in t and t.replace("R$", "r$", 1) not in out:
        out.append(t.replace("R$", "r$", 1))
    # descrição -> descricao (já coberto por remove_accents em parte)
    # Espaço duplo
    if "  " not in t and len(t) > 5:
        out.append(t.replace(" ", "  ", 1))
    # vencimento -> venc
    if "vencimento" in t and t.replace("vencimento", "venc", 1) not in out:
        out.append(t.replace("vencimento", "venc", 1))
    return list(dict.fromkeys(out))


# --- Contas a pagar: frases base (INSERT) ---
CONTAS_PAGAR_BASE = [
    "cadastre conta de luz 100 reais dia 15",
    "conta de luz 100 reais dia 15",
    "R$ 250 conta água dia 10",
    "fornecedor Cemig valor R$ 200 vencimento 20/03/2026",
    "dívida de 500, João",
    "conta de 500 para Maria",
    "todo dia 15 conta luz 100 reais",
    "registrar conta de telefone 80 reais dia 8",
    "nova conta fornecedor Energia valor 150 dia 5",
    "conta de internet 90 reais vencimento 12/04/2026",
    "cadastrar conta aluguel 1200 reais dia 10",
    "conta água 80 reais dia 15",
    "conta de gás 60 reais dia 20",
    "fornecedor Telefonia valor 95 reais data 25/03/2026",
    "divida de 300 credor Loja X",
    "conta de 200 reais para Padaria dia 18",
    "registre conta de luz 110 reais dia 15",
    "conta luz 100 reais dia 15",
    "R$ 100 conta de luz dia 15",
    "100 reais conta luz dia 15",
    "conta de luz R$ 100 dia 15",
    "luz 100 reais dia 15",
    "cadastre luz 100 reais dia 15",
    "conta telefone 80 reais dia 8",
    "conta de telefone 80 reais dia 8",
    "água 80 reais dia 10",
    "conta água 80 dia 10",
    "vencimento 15/03/2026 fornecedor Luz valor 100",
    "valor 200 fornecedor Cemig data 20/03/2026",
    "conta de 150 reais dia 25",
    "registrar dívida de 960",
    "conta prestação 500 reais dia 5",
    "aluguel 1200 dia 10",
    "conta de aluguel 1200 reais dia 10",
    "fornecedor João valor 50 reais vencimento amanhã",
    "descrição Conta de luz valor 100 dia 15",
    "conta de luz 100 reais dia 15 descrição Luz",
]

# Gerar 100+ casos contas a pagar (detector: entity=contas_pagar, action=INSERT)
def get_contas_pagar_cases(min_cases: int = 100) -> List[Dict[str, Any]]:
    seen = set()
    cases = []
    for base in CONTAS_PAGAR_BASE:
        for variant in _typo_variants(base):
            if variant.lower() in seen:
                continue
            seen.add(variant.lower())
            cases.append({
                "text": variant,
                "context": {"pagina": "contas_a_pagar"},
                "expected_entity": "contas_pagar",
                "expected_action": "INSERT",
            })
        if len(cases) >= min_cases:
            break
    for base in CONTAS_PAGAR_BASE:
        if len(cases) >= min_cases:
            break
        if base.lower() not in seen:
            seen.add(base.lower())
            cases.append({
                "text": base,
                "context": {"pagina": "contas_a_pagar"},
                "expected_entity": "contas_pagar",
                "expected_action": "INSERT",
            })
    return cases


# --- Contas a receber: frases base (INSERT / fiado) ---
CONTAS_RECEBER_BASE = [
    "registre um fiado",
    "receber de Maria 80 reais dia 20",
    "fiado Willian valor de 500",
    "conta a receber de João 150 reais vencimento 25/03",
    "cliente Pedro 200 reais dia 15",
    "de 500 para Willian venc dia 10",
    "registrar fiado",
    "conta a receber Maria 80 reais dia 20",
    "fiado valor de 300 cliente João",
    "receber de Willian 500 reais",
    "cliente Ana 150 reais dia 25",
    "conta a receber de Pedro 200 vencimento 15/04/2026",
    "registre fiado Willian valor de 500",
    "fiado Maria 80 reais dia 20",
    "receber de João 150 reais dia 25",
    "cliente Willian valor de 500 dia 15",
    "de 300 para Ana vencimento 20/03",
    "registrar conta a receber Maria 80 reais dia 20",
    "conta receber João 150 dia 25",
    "fiado Pedro 200 reais",
    "receber de Carlos 100 reais dia 10",
    "cliente Carlos 100 reais dia 10",
    "valor de 250 cliente Lucia",
    "Lucia valor de 250 reais dia 30",
    "registre um fiado",
    "registra um fiado",
    "cadastre fiado",
    "cadastrar fiado",
    "conta a receber 80 reais dia 20 cliente Maria",
    "Maria 80 reais dia 20 conta a receber",
    "Willian valor de 500",
    "fiado 500 reais Willian dia 15",
    "receber de Bruno 120 reais venc 18",
    "cliente Bruno 120 reais venc 18",
    "conta a receber Bruno 120 reais dia 18",
    "de 400 para Lucia venc dia 25",
    "registre receber de Maria 80 reais dia 20",
    "fiado Ana 150 reais vencimento 25/03",
    "conta receber Pedro 200 dia 15",
]

def get_contas_receber_cases(min_cases: int = 100) -> List[Dict[str, Any]]:
    seen = set()
    cases = []
    for base in CONTAS_RECEBER_BASE:
        for variant in _typo_variants(base):
            if variant.lower() in seen:
                continue
            seen.add(variant.lower())
            cases.append({
                "text": variant,
                "context": {"pagina": "contas_a_pagar"},
                "expected_entity": "contas_receber",
                "expected_action": "INSERT",
            })
        if len(cases) >= min_cases:
            break
    for base in CONTAS_RECEBER_BASE:
        if len(cases) >= min_cases:
            break
        if base.lower() not in seen:
            seen.add(base.lower())
            cases.append({
                "text": base,
                "context": {"pagina": "contas_a_pagar"},
                "expected_entity": "contas_receber",
                "expected_action": "INSERT",
            })
    return cases


# --- Agenda: frases base (INSERT) ---
AGENDA_BASE = [
    "reunião amanhã 14h",
    "agendar dentista para amanhã",
    "cadastre reunião com João dia 15/03 14h",
    "marcar compromisso reunião equipe amanhã às 10h",
    "lembrete pagar conta amanhã",
    "evento aniversário dia 20/03/2026 18h",
    "reuniao amanha 14h",
    "cadastrar consulta médica para dia 10",
    "agendar reunião amanhã 14h",
    "marcar reunião amanhã",
    "reunião com João amanhã 14h",
    "compromisso dentista amanhã 10h",
    "cadastre dentista para amanhã 9h",
    "evento reunião equipe dia 15/03 14h",
    "lembrete ligar para cliente amanhã",
    "agendar consulta médica dia 20/03 8h",
    "marcar dentista amanhã",
    "reunião amanhã às 14h",
    "reuniao amanha 14h30",
    "reunião amanhã 14:30",
    "cadastrar reunião amanhã 14h",
    "agenda reunião amanhã 14h",
    "compromisso amanhã 10h",
    "evento aniversário amanhã 18h",
    "titulo Dentista amanhã 9h",
    "cadastre evento reunião dia 15/03",
    "marcar lembrete pagar contas amanhã",
    "reunião equipe amanhã 15h",
    "consulta médica dia 10/03 8h",
    "agendar compromisso dia 25/03 14h",
    "reunião amanhã 14h descrição Reunião semanal",
    "cadastrar reunião com Maria amanhã 10h",
    "marca dentista para amanhã",
    "evento reunião amanhã",
    "lembrete amanhã 8h",
    "reuniao equipe amanha 14h",
    "compromisso reunião dia 15 14h",
    "agendar dentista dia 10 9h",
    "cadastra reunião amanhã 14h",
    "reunião amanhã às 14",
    "reunião 14h amanhã",
    "amanhã 14h reunião",
    "amanha 14h reuniao",
]

def get_agenda_cases(min_cases: int = 100) -> List[Dict[str, Any]]:
    seen = set()
    cases = []
    for base in AGENDA_BASE:
        for variant in _typo_variants(base):
            if variant.lower() in seen:
                continue
            seen.add(variant.lower())
            cases.append({
                "text": variant,
                "context": {"pagina": "agenda"},
                "expected_entity": "agenda",
                "expected_action": "INSERT",
            })
        if len(cases) >= min_cases:
            break
    for base in AGENDA_BASE:
        if len(cases) >= min_cases:
            break
        if base.lower() not in seen:
            seen.add(base.lower())
            cases.append({
                "text": base,
                "context": {"pagina": "agenda"},
                "expected_entity": "agenda",
                "expected_action": "INSERT",
            })
    return cases


# --- Relatórios: frases base (analyze_query) ---
# Formato: (pergunta, intent_esperado, data_type_esperado) - data_type pode ser lista de aceitáveis
REPORT_BASE: List[Tuple[str, str, Any]] = [
    ("contas a pagar deste mês", "consulta", "contas_pagar"),
    ("contas a pagar deste mes", "consulta", "contas_pagar"),
    ("contas a receber", "consulta", "contas_receber"),
    ("quanto vendi este mês", "consulta", "resumo_periodo"),
    ("faturamento de hoje", "consulta", "resumo_periodo"),
    ("produtos mais vendidos", "consulta", "produtos_mais_vendidos"),
    ("valor do estoque", "consulta", "valor_estoque"),
    ("entradas de estoque", "consulta", "entradas_estoque"),
    ("sessões de caixa", "consulta", "sessoes_caixa"),
    ("meus compromissos", "consulta", "agenda"),
    ("agenda de hoje", "consulta", "agenda"),
    ("previsão de vendas", "consulta", "analise_avancada"),
    ("tendência", "consulta", "analise_avancada"),
    ("resumo do período", "consulta", "resumo_periodo"),
    ("que dia é hoje", "resposta_direta", None),
    ("relatório", "consulta", None),  # pode ser esclarecer_periodo ou consulta
    ("contas a pagar", "consulta", "contas_pagar"),
    ("contas a receber deste mês", "consulta", "contas_receber"),
    ("quanto faturou este mês", "consulta", "resumo_periodo"),
    ("lucro do mês", "consulta", "resumo_periodo"),
    ("vendas do mês", "consulta", "resumo_periodo"),
    ("o que mais vendeu", "consulta", "produtos_mais_vendidos"),
    ("quanto tenho em estoque", "consulta", "valor_estoque"),
    ("sessões caixa", "consulta", "sessoes_caixa"),
    ("o que tenho na agenda", "consulta", "agenda"),
    ("compromissos de hoje", "consulta", "agenda"),
    ("relatorio de vendas", "consulta", "resumo_periodo"),
    ("contas do mês", "consulta", ["contas_pagar", "contas_receber"]),
    ("o que vence esse mês", "consulta", "contas_pagar"),
    ("faturamento deste mês", "consulta", "resumo_periodo"),
    ("resumo período", "consulta", "resumo_periodo"),
    ("previsao vendas", "consulta", "analise_avancada"),
    ("tendencia vendas", "consulta", "analise_avancada"),
    ("análise avançada", "consulta", "analise_avancada"),
    ("relatório contas a pagar", "consulta", "contas_pagar"),
    ("listar contas a pagar", "consulta", "contas_pagar"),
    ("mostrar contas a receber", "consulta", "contas_receber"),
    ("vendas hoje", "consulta", "resumo_periodo"),
    ("caixa do dia", "consulta", "sessoes_caixa"),
    ("estoque atual", "consulta", "valor_estoque"),
    ("top vendas", "consulta", "produtos_mais_vendidos"),
    ("mais vendidos", "consulta", "produtos_mais_vendidos"),
    ("quanto vendi", "consulta", "resumo_periodo"),
    ("faturamento", "consulta", "resumo_periodo"),
    ("lucro", "consulta", "resumo_periodo"),
    ("contas pagar este mes", "consulta", "contas_pagar"),
    ("contas receber este mes", "consulta", "contas_receber"),
    ("agenda hoje", "consulta", "agenda"),
    ("compromissos", "consulta", "agenda"),
    ("relatorio", "consulta", None),
    ("mes de vendas", "consulta", "resumo_periodo"),
    ("periodo vendas", "consulta", "resumo_periodo"),
]

def get_report_cases(min_cases: int = 100) -> List[Dict[str, Any]]:
    seen = set()
    cases = []
    for pergunta, intent, data_type in REPORT_BASE:
        for variant in _typo_variants(pergunta):
            if variant.lower() in seen:
                continue
            seen.add(variant.lower())
            cases.append({
                "text": variant,
                "history": [],
                "expected_intent": intent,
                "expected_data_type": data_type,
            })
        if len(cases) >= min_cases:
            break
    for pergunta, intent, data_type in REPORT_BASE:
        if len(cases) >= min_cases:
            break
        if pergunta.lower() not in seen:
            seen.add(pergunta.lower())
            cases.append({
                "text": pergunta,
                "history": [],
                "expected_intent": intent,
                "expected_data_type": data_type,
            })
    return cases
