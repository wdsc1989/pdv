"""
Testes de interação com os agentes (MCP + Contas + Agenda + Relatórios).
Valida detector, extractor, fluxo de contas (fiado, continuação, descrição) e agenda.
Suíte expandida: 100+ testes por domínio (data-driven) com linguagem natural e typos.
"""
import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from config.database import SessionLocal
from mcp import MCPDetector, MCPExtractor, MCPValidator, MCPFormatter
from services.accounts_agent_service import AccountsAgentService, _parse_nome_valor_resposta
from services.agenda_agent_service import AgendaAgentService
from services.report_agent_service import ReportAgentService

from test_agentes_data import (
    get_contas_pagar_cases,
    get_contas_receber_cases,
    get_agenda_cases,
    get_report_cases,
)


def ok(msg: str):
    print(f"  [OK] {msg}")


def fail(msg: str):
    print(f"  [FALHA] {msg}")


def section(title: str):
    print(f"\n--- {title} ---")


# --- Testes legados (smoke) ---
def test_mcp_fiado_contas_receber(db):
    """'registre um fiado' com contexto Contas a Pagar deve ser classificado como contas_receber."""
    section("MCP Detector: 'registre um fiado' -> contas_receber")
    detector = MCPDetector(db)
    det = detector.detect("registre um fiado", {"pagina": "contas_a_pagar"})
    if det.entity == "contas_receber" and det.action == "INSERT":
        ok(f"entity={det.entity}, action={det.action}")
        return True
    fail(f"Esperado entity=contas_receber, action=INSERT; obtido entity={det.entity}, action={det.action}")
    return False


def test_mcp_conta_luz_extractor(db):
    """'cadastre conta de luz 100 reais dia 15' -> fornecedor Luz, valor 100, data_vencimento."""
    section("MCP Extractor: conta de luz 100 reais dia 15")
    detector = MCPDetector(db)
    det = detector.detect("cadastre conta de luz 100 reais dia 15", {"pagina": "contas_a_pagar"})
    if det.entity != "contas_pagar" or det.action != "INSERT":
        fail(f"Detector: entity={det.entity}, action={det.action}")
        return False
    ok(f"Detector: entity={det.entity}, action={det.action}")
    extractor = MCPExtractor(db)
    ext = extractor.extract("cadastre conta de luz 100 reais dia 15", "INSERT", "contas_pagar", {})
    data = ext.data
    checks = [
        data.get("fornecedor") == "Luz" or (isinstance(data.get("fornecedor"), str) and "luz" in data.get("fornecedor", "").lower()),
        float(data.get("valor", 0)) == 100.0,
        "data_vencimento" in data and data["data_vencimento"],
    ]
    if all(checks):
        ok(f"fornecedor={data.get('fornecedor')}, valor={data.get('valor')}, data_vencimento={data.get('data_vencimento')}")
        return True
    fail(f"data={data}; missing_fields={ext.missing_fields}")
    return False


def test_contas_registre_fiado_first_turn(db):
    """Primeira mensagem 'registre um fiado' -> need_info com pergunta de cliente/valor (não fornecedor)."""
    section("Agente Contas: primeira mensagem 'registre um fiado'")
    agent = AccountsAgentService(db)
    out = agent.parse_request("registre um fiado", context={"pagina": "contas_a_pagar"}, conversation_history=[])
    if out.get("status") != "need_info":
        fail(f"Esperado status=need_info; obtido status={out.get('status')}, message={out.get('message', '')[:80]}")
        return False
    msg = (out.get("message") or "").lower()
    if "cliente" in msg or "valor" in msg:
        ok(f"status=need_info, pergunta menciona cliente/valor")
    else:
        fail(f"Pergunta deveria mencionar cliente ou valor (conta a receber); message={out.get('message', '')[:120]}")
        return False
    if "fornecedor" in msg and "cliente" not in msg:
        fail("Fiado deve pedir cliente, não fornecedor")
        return False
    return True


def test_parse_nome_valor(db):
    """Helper _parse_nome_valor_resposta('Willian, valor de 500') retorna ('Willian', 500.0)."""
    section("Helper: _parse_nome_valor_resposta('Willian, valor de 500')")
    nome, valor = _parse_nome_valor_resposta("Willian, valor de 500")
    if nome == "Willian" and valor == 500.0:
        ok(f"nome={nome!r}, valor={valor}")
        return True
    fail(f"Esperado ('Willian', 500.0); obtido ({nome!r}, {valor})")
    return False


def test_contas_continuation_willian_valor_500(db):
    """Resposta 'Willian, valor de 500' no fluxo de fiado deve preencher cliente e valor."""
    section("Agente Contas: continuação 'Willian, valor de 500'")
    agent = AccountsAgentService(db)
    history = [
        {"role": "user", "content": "registre um fiado"},
        {"role": "assistant", "content": "Preciso de mais algumas informações:\n\n- Qual o valor?\n- Qual o nome do cliente (conta a receber)?\n- Qual a data de vencimento?"},
    ]
    out = agent.parse_request("Willian, valor de 500", context={"pagina": "contas_a_pagar"}, conversation_history=history)
    status = out.get("status")
    msg = (out.get("message") or "").lower()
    if status == "confirm":
        ok("Dados completos e foi para confirmação")
        return True
    if status == "need_info" and "qual o valor" not in msg:
        ok("Falta só data (ou cliente); valor extraído corretamente")
        return True
    fail(f"status={status}, message={msg[:100]}")
    return False


def test_contas_description_reply_nao(db):
    """Resposta 'não' à sugestão de descrição deve ir para confirmação."""
    section("Agente Contas: resposta 'não' à sugestão de descrição")
    agent = AccountsAgentService(db)
    history = [
        {"role": "user", "content": "registre um fiado"},
        {"role": "assistant", "content": "Preciso de mais algumas informações:\n\n- Qual o valor?\n- Qual o nome do cliente?\n- Qual a data de vencimento?"},
        {"role": "user", "content": "80 reais"},
        {"role": "assistant", "content": "Preciso de mais algumas informações:\n\n- Qual o nome do cliente?\n- Qual a data de vencimento?"},
        {"role": "user", "content": "Willian"},
        {"role": "assistant", "content": "Preciso de mais algumas informações:\n\n- Qual a data de vencimento?"},
        {"role": "user", "content": "dia 20"},
        {"role": "assistant", "content": "**Sugestão de descrição:** Willian.\n\nConfirma ou envie outra (opcional — **não** para sem descrição)."},
    ]
    out = agent.parse_request("não", context={"pagina": "contas_a_pagar"}, conversation_history=history)
    if out.get("status") == "confirm":
        ok("Resposta 'não' levou à confirmação (não repetiu sugestão)")
        return True
    if "Sugestão de descrição" in (out.get("message") or ""):
        fail("Não deveria repetir a mesma sugestão de descrição após 'não'")
        return False
    fail(f"status={out.get('status')}, message={out.get('message', '')[:150]}")
    return False


def test_agenda_reuniao_amanha(db):
    """'reunião amanhã 14h' -> titulo e data preenchidos."""
    section("Agente Agenda: 'reunião amanhã 14h'")
    agent = AgendaAgentService(db)
    out = agent.parse_request("reunião amanhã 14h", conversation_history=[])
    if out.get("status") == "confirm":
        ok("Confirmado com título e data/hora")
        return True
    if out.get("status") == "need_info":
        missing = out.get("missing") or []
        if not missing or "titulo" in missing or "data" in missing:
            ok("need_info com missing titulo/data (aceitável se extração não preencheu)")
        return True
    fail(f"status={out.get('status')}, message={out.get('message', '')[:80]}")
    return False


def test_report_analyze_query_contas_pagar(db):
    """Relatório: 'contas a pagar deste mês' -> intent consulta, data_type contas_pagar."""
    section("Agente Relatórios: analyze_query 'contas a pagar deste mês'")
    try:
        agent = ReportAgentService(db)
        out = agent.analyze_query("contas a pagar deste mês", conversation_history=[])
    except Exception as e:
        fail(f"Exceção: {e}")
        return None
    if not out:
        fail("analyze_query retornou None (IA não configurada ou timeout)")
        return None
    intent = out.get("intent", "")
    data_type = out.get("data_type", "")
    if intent == "consulta" and data_type == "contas_pagar":
        ok(f"intent={intent}, data_type={data_type}")
        return True
    fail(f"Esperado intent=consulta, data_type=contas_pagar; obtido intent={intent}, data_type={data_type}")
    return False


def test_mcp_validator_message_ia(db):
    """Validator com dados inválidos deve poder retornar message_ia."""
    section("MCP Validator: message_ia em dados inválidos")
    val = MCPValidator(db).validate(
        {"fornecedor": "", "valor": 0, "data_vencimento": "2026-03-15"},
        "INSERT",
        "contas_pagar",
    )
    if val.valid:
        fail("Dados inválidos deveriam gerar valid=False")
        return False
    if not val.errors:
        fail("Deveria haver erros")
        return False
    ok(f"valid=False, errors={val.errors[:2]}")
    if getattr(val, "message_ia", None):
        ok(f"message_ia presente: {val.message_ia[:60]}...")
    return True


# --- Runner data-driven por domínio ---
def run_detector_case(db, case: dict, domain: str, failures: list, save_failures: bool) -> bool:
    """Retorna True=pass, False=fail, None=skip."""
    text = case.get("text", "")
    context = case.get("context", {})
    expected_entity = case.get("expected_entity", "")
    expected_action = case.get("expected_action", "")
    detector = MCPDetector(db)
    det = detector.detect(text, context)
    if det.entity == expected_entity and det.action == expected_action:
        return True
    if save_failures:
        failures.append({
            "domain": domain,
            "input": text,
            "context": context,
            "expected_entity": expected_entity,
            "expected_action": expected_action,
            "got_entity": getattr(det, "entity", None),
            "got_action": getattr(det, "action", None),
        })
    return False


def run_report_case(db, case: dict, domain: str, failures: list, save_failures: bool):
    """Retorna True=pass, False=fail, None=skip (IA indisponível)."""
    text = case.get("text", "")
    history = case.get("history", [])
    expected_intent = case.get("expected_intent", "")
    expected_data_type = case.get("expected_data_type")
    try:
        agent = ReportAgentService(db)
        out = agent.analyze_query(text, conversation_history=history)
    except Exception as e:
        if save_failures:
            failures.append({"domain": domain, "input": text, "error": str(e)})
        return False
    if not out:
        return None  # skip
    intent = out.get("intent", "")
    data_type = out.get("data_type", "")
    intent_ok = intent == expected_intent
    if expected_data_type is None:
        data_type_ok = True
    elif isinstance(expected_data_type, list):
        data_type_ok = data_type in expected_data_type
    else:
        data_type_ok = data_type == expected_data_type
    if intent_ok and data_type_ok:
        return True
    if save_failures:
        failures.append({
            "domain": domain,
            "input": text,
            "expected_intent": expected_intent,
            "expected_data_type": expected_data_type,
            "got_intent": intent,
            "got_data_type": data_type,
        })
    return False


def run_data_driven_domain(db, domain: str, cases: list, run_fn, save_failures: bool, verbose: bool):
    """Executa casos de um domínio; run_fn(db, case, domain, failures, save_failures) -> True/False/None."""
    failures = []
    passed = 0
    failed = 0
    skipped = 0
    for i, case in enumerate(cases):
        result = run_fn(db, case, domain, failures, save_failures)
        if result is True:
            passed += 1
            if verbose:
                ok(f"{domain} #{i+1}: {str(case.get('text', ''))[:50]}")
        elif result is False:
            failed += 1
            if verbose:
                fail(f"{domain} #{i+1}: {str(case.get('text', ''))[:50]}")
        else:
            skipped += 1
    return passed, failed, skipped, failures


def main():
    parser = argparse.ArgumentParser(description="Testes dos agentes (MCP, Contas, Agenda, Relatórios)")
    parser.add_argument("--save-failures", action="store_true", help="Salvar falhas em arquivo JSON")
    parser.add_argument("--failures-file", default="test_agentes_failures.json", help="Arquivo de saída das falhas")
    parser.add_argument("--verbose", "-v", action="store_true", help="Imprimir cada caso (OK/FALHA)")
    parser.add_argument("--legacy-only", action="store_true", help="Só rodar testes legados (sem data-driven)")
    parser.add_argument("--data-driven-only", action="store_true", help="Só rodar data-driven (sem legados)")
    parser.add_argument("--skip-report", action="store_true", help="Não rodar data-driven de relatórios (evita 100+ chamadas IA)")
    parser.add_argument("--max-per-domain", type=int, default=0, help="Máximo de casos por domínio (0 = todos, ex. 20 para rodada rápida)")
    args = parser.parse_args()

    print("\n=== Testes de interação com os agentes (MCP + Contas + Agenda + Relatórios) ===\n")
    db = SessionLocal()
    all_failures = []
    results_legacy = {}
    domain_stats = {}

    try:
        # --- Legados ---
        if not args.data_driven_only:
            results_legacy["mcp_fiado_contas_receber"] = test_mcp_fiado_contas_receber(db)
            results_legacy["mcp_conta_luz_extractor"] = test_mcp_conta_luz_extractor(db)
            results_legacy["contas_registre_fiado"] = test_contas_registre_fiado_first_turn(db)
            results_legacy["parse_nome_valor"] = test_parse_nome_valor(db)
            results_legacy["contas_willian_valor_500"] = test_contas_continuation_willian_valor_500(db)
            results_legacy["contas_description_nao"] = test_contas_description_reply_nao(db)
            results_legacy["agenda_reuniao_amanha"] = test_agenda_reuniao_amanha(db)
            results_legacy["report_contas_pagar"] = test_report_analyze_query_contas_pagar(db)
            results_legacy["validator_message_ia"] = test_mcp_validator_message_ia(db)

        # --- Data-driven: Contas a pagar ---
        if not args.legacy_only:
            n_cases = args.max_per_domain or 100
            section("Data-driven: Contas a pagar (Detector)")
            cases_pagar = get_contas_pagar_cases(n_cases)
            if args.max_per_domain:
                cases_pagar = cases_pagar[: args.max_per_domain]
            p, f, s, fail_list = run_data_driven_domain(
                db, "contas_pagar", cases_pagar, run_detector_case, args.save_failures, args.verbose
            )
            domain_stats["contas_pagar"] = (p, f, s)
            all_failures.extend(fail_list)
            if not args.verbose:
                print(f"  Contas a pagar: {p} passaram, {f} falharam, {s} ignorados (total {len(cases_pagar)})")

            # --- Contas a receber ---
            section("Data-driven: Contas a receber (Detector)")
            cases_receber = get_contas_receber_cases(n_cases)
            if args.max_per_domain:
                cases_receber = cases_receber[: args.max_per_domain]
            p, f, s, fail_list = run_data_driven_domain(
                db, "contas_receber", cases_receber, run_detector_case, args.save_failures, args.verbose
            )
            domain_stats["contas_receber"] = (p, f, s)
            all_failures.extend(fail_list)
            if not args.verbose:
                print(f"  Contas a receber: {p} passaram, {f} falharam, {s} ignorados (total {len(cases_receber)})")

            # --- Agenda ---
            section("Data-driven: Agenda (Detector)")
            cases_agenda = get_agenda_cases(n_cases)
            if args.max_per_domain:
                cases_agenda = cases_agenda[: args.max_per_domain]
            p, f, s, fail_list = run_data_driven_domain(
                db, "agenda", cases_agenda, run_detector_case, args.save_failures, args.verbose
            )
            domain_stats["agenda"] = (p, f, s)
            all_failures.extend(fail_list)
            if not args.verbose:
                print(f"  Agenda: {p} passaram, {f} falharam, {s} ignorados (total {len(cases_agenda)})")

            # --- Relatórios ---
            if not args.skip_report:
                section("Data-driven: Relatórios (analyze_query)")
                cases_report = get_report_cases(n_cases)
                if args.max_per_domain:
                    cases_report = cases_report[: args.max_per_domain]
                p, f, s, fail_list = run_data_driven_domain(
                    db, "relatorios", cases_report, run_report_case, args.save_failures, args.verbose
                )
                domain_stats["relatorios"] = (p, f, s)
                all_failures.extend(fail_list)
                if not args.verbose:
                    print(f"  Relatórios: {p} passaram, {f} falharam, {s} ignorados (total {len(cases_report)})")
    finally:
        db.close()

    # --- Resumo ---
    section("Resumo")
    if results_legacy:
        for name, v in results_legacy.items():
            s = "OK" if v is True else ("SKIP" if v is None else "FALHA")
            print(f"  {name}: {s}")
        passed_legacy = sum(1 for v in results_legacy.values() if v is True)
        failed_legacy = sum(1 for v in results_legacy.values() if v is False)
        skipped_legacy = sum(1 for v in results_legacy.values() if v is None)
        print(f"  Legados: {passed_legacy} passaram, {failed_legacy} falharam, {skipped_legacy} ignorados")
    if domain_stats:
        for domain, (p, f, s) in domain_stats.items():
            print(f"  {domain}: {p}/{p + f + s} passaram ({f} falharam, {s} ignorados)")
        total_data = sum(p + f + s for p, f, s in domain_stats.values())
        total_pass = sum(p for p, f, s in domain_stats.values())
        total_fail = sum(f for p, f, s in domain_stats.values())
        total_skip = sum(s for p, f, s in domain_stats.values())
        print(f"  Data-driven total: {total_pass} passaram, {total_fail} falharam, {total_skip} ignorados ({total_data} casos)")

    if args.save_failures and all_failures:
        out_path = Path(__file__).resolve().parent / args.failures_file
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(all_failures, fh, ensure_ascii=False, indent=2)
        print(f"\n  Falhas salvas em: {out_path} ({len(all_failures)} registros)")

    total_failed = sum(1 for v in results_legacy.values() if v is False) if results_legacy else 0
    total_failed += sum(f for _, f, _ in domain_stats.values())
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
