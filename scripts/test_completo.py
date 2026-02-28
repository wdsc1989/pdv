"""
Script de teste completo do sistema PDV.
Testa todas as funcionalidades desde abertura de caixa até relatórios.
"""
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Adiciona o diretório raiz ao path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func

from config.database import SessionLocal, init_db, DATABASE_URL
from models.cash_session import CashSession
from models.product import Product
from models.sale import Sale, SaleItem
from services.auth_service import ensure_default_admin


def print_header(text: str):
    """Imprime um cabeçalho formatado."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_success(text: str):
    """Imprime mensagem de sucesso."""
    print(f"[OK] {text}")


def print_error(text: str):
    """Imprime mensagem de erro."""
    print(f"[ERRO] {text}")


def print_info(text: str):
    """Imprime informacao."""
    print(f"  -> {text}")


def format_currency(value: float) -> str:
    """Formata valor como moeda."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def test_1_inicializacao():
    """Teste 1: Inicialização do banco de dados."""
    print_header("TESTE 1: Inicializacao do Banco de Dados")
    try:
        # Recria todas as tabelas (drop_all + create_all)
        from config.database import Base, engine
        print_info("Recriando estrutura do banco de dados...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print_success("Estrutura do banco recriada")
        
        ensure_default_admin()
        print_success("Banco de dados inicializado com sucesso")
        print_success("Usuario admin padrao garantido")
        return True
    except Exception as e:
        print_error(f"Falha na inicializacao: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_2_produtos(db):
    """Teste 2: Verificação/Criação de produtos."""
    print_header("TESTE 2: Verificacao de Produtos")
    try:
        produtos = db.query(Product).filter(Product.ativo.is_(True)).all()
        if not produtos:
            print_info("Nenhum produto encontrado. Executando seed de produtos...")
            # Executa o seed de produtos
            try:
                from scripts.seed_products import main as seed_main
                seed_main()
                print_success("Seed de produtos executado com sucesso")
                # Recarrega produtos
                produtos = db.query(Product).filter(Product.ativo.is_(True)).all()
            except Exception as seed_err:
                print_error(f"Falha ao executar seed: {seed_err}")
                return False
        
        if not produtos:
            print_error("Ainda nao ha produtos apos seed")
            return False
        
        print_success(f"Encontrados {len(produtos)} produtos ativos")
        print_info("Primeiros 3 produtos:")
        for p in produtos[:3]:
            margem = ((p.preco_venda - p.preco_custo) / p.preco_custo * 100) if p.preco_custo > 0 else 0
            print(f"    - {p.codigo}: {p.nome} | Estoque: {p.estoque_atual} | "
                  f"Preco: {format_currency(p.preco_venda)} | Margem: {margem:.1f}%")
        return True
    except Exception as e:
        print_error(f"Falha na verificacao de produtos: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_abertura_caixa(db):
    """Teste 3: Abertura de caixa."""
    print_header("TESTE 3: Abertura de Caixa")
    try:
        # Verifica se já existe caixa aberto
        sessao_aberta = db.query(CashSession).filter(CashSession.status == "aberta").first()
        if sessao_aberta:
            print_info(f"Caixa já está aberto desde {sessao_aberta.data_abertura}")
            print_info(f"Valor de abertura: {format_currency(sessao_aberta.valor_abertura)}")
            return sessao_aberta
        
        # Abre novo caixa
        valor_abertura = 100.0
        nova_sessao = CashSession(
            valor_abertura=valor_abertura,
            observacao="Abertura automática - Teste do sistema",
            status="aberta",
        )
        db.add(nova_sessao)
        db.commit()
        db.refresh(nova_sessao)
        
        print_success(f"Caixa aberto com sucesso")
        print_info(f"ID da sessão: {nova_sessao.id}")
        print_info(f"Valor de abertura: {format_currency(valor_abertura)}")
        print_info(f"Data de abertura: {nova_sessao.data_abertura}")
        return nova_sessao
    except Exception as e:
        print_error(f"Falha na abertura de caixa: {e}")
        return None


def test_4_vendas(db, sessao_aberta):
    """Teste 4: Realização de vendas."""
    print_header("TESTE 4: Realização de Vendas")
    try:
        produtos = db.query(Product).filter(Product.ativo.is_(True)).limit(3).all()
        if not produtos:
            print_error("Nenhum produto disponível para venda")
            return False
        
        vendas_realizadas = []
        
        # Venda 1: Produto único
        print_info("\nVenda 1: Produto único")
        produto1 = produtos[0]
        qtd1 = 2
        preco_unit1 = produto1.preco_venda
        subtotal1 = preco_unit1 * qtd1
        lucro1 = (preco_unit1 - produto1.preco_custo) * qtd1
        
        estoque_antes1 = produto1.estoque_atual
        
        venda1 = Sale(
            cash_session_id=sessao_aberta.id,
            data_venda=date.today(),
            total_vendido=subtotal1,
            total_lucro=lucro1,
            total_pecas=qtd1,
            tipo_pagamento="dinheiro",
            status="concluida",
        )
        db.add(venda1)
        db.flush()
        
        item1 = SaleItem(
            sale_id=venda1.id,
            product_id=produto1.id,
            quantidade=qtd1,
            preco_unitario=preco_unit1,
            preco_custo_unitario=produto1.preco_custo,
            subtotal=subtotal1,
            lucro_item=lucro1,
        )
        db.add(item1)
        
        produto1.estoque_atual = (produto1.estoque_atual or 0) - qtd1
        db.commit()
        db.refresh(venda1)
        db.refresh(produto1)
        
        print_success(f"Venda #{venda1.id} registrada")
        print_info(f"  Produto: {produto1.codigo} - {produto1.nome}")
        print_info(f"  Quantidade: {qtd1}")
        print_info(f"  Total: {format_currency(subtotal1)}")
        print_info(f"  Lucro: {format_currency(lucro1)}")
        print_info(f"  Estoque antes: {estoque_antes1} | Estoque depois: {produto1.estoque_atual}")
        vendas_realizadas.append(venda1)
        
        # Venda 2: Múltiplos produtos
        if len(produtos) >= 2:
            print_info("\nVenda 2: Múltiplos produtos")
            produto2 = produtos[1]
            produto3 = produtos[2] if len(produtos) >= 3 else produtos[0]
            
            qtd2 = 1
            qtd3 = 3
            
            subtotal2 = produto2.preco_venda * qtd2
            subtotal3 = produto3.preco_venda * qtd3
            total_vendido2 = subtotal2 + subtotal3
            
            lucro2 = (produto2.preco_venda - produto2.preco_custo) * qtd2
            lucro3 = (produto3.preco_venda - produto3.preco_custo) * qtd3
            total_lucro2 = lucro2 + lucro3
            
            estoque_antes2 = produto2.estoque_atual
            estoque_antes3 = produto3.estoque_atual
            
            venda2 = Sale(
                cash_session_id=sessao_aberta.id,
                data_venda=date.today(),
                total_vendido=total_vendido2,
                total_lucro=total_lucro2,
                total_pecas=qtd2 + qtd3,
                tipo_pagamento="pix",
                status="concluida",
            )
            db.add(venda2)
            db.flush()
            
            item2 = SaleItem(
                sale_id=venda2.id,
                product_id=produto2.id,
                quantidade=qtd2,
                preco_unitario=produto2.preco_venda,
                preco_custo_unitario=produto2.preco_custo,
                subtotal=subtotal2,
                lucro_item=lucro2,
            )
            item3 = SaleItem(
                sale_id=venda2.id,
                product_id=produto3.id,
                quantidade=qtd3,
                preco_unitario=produto3.preco_venda,
                preco_custo_unitario=produto3.preco_custo,
                subtotal=subtotal3,
                lucro_item=lucro3,
            )
            db.add(item2)
            db.add(item3)
            
            produto2.estoque_atual = (produto2.estoque_atual or 0) - qtd2
            produto3.estoque_atual = (produto3.estoque_atual or 0) - qtd3
            db.commit()
            db.refresh(venda2)
            db.refresh(produto2)
            db.refresh(produto3)
            
            print_success(f"Venda #{venda2.id} registrada")
            print_info(f"  Produto 1: {produto2.codigo} - Qtd: {qtd2} - Total: {format_currency(subtotal2)}")
            print_info(f"  Produto 2: {produto3.codigo} - Qtd: {qtd3} - Total: {format_currency(subtotal3)}")
            print_info(f"  Total da venda: {format_currency(total_vendido2)}")
            print_info(f"  Lucro total: {format_currency(total_lucro2)}")
            print_info(f"  Estoque {produto2.codigo}: {estoque_antes2} -> {produto2.estoque_atual}")
            print_info(f"  Estoque {produto3.codigo}: {estoque_antes3} -> {produto3.estoque_atual}")
            vendas_realizadas.append(venda2)
        
        print_success(f"\nTotal de vendas realizadas: {len(vendas_realizadas)}")
        return True
    except Exception as e:
        print_error(f"Falha na realização de vendas: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_validacao_vendas(db, sessao_aberta):
    """Teste 5: Validação das vendas realizadas."""
    print_header("TESTE 5: Validacao das Vendas")
    try:
        vendas = (
            db.query(Sale)
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .all()
        )
        print_success(f"Total de vendas na sessão: {len(vendas)}")
        
        total_vendido = sum(v.total_vendido for v in vendas)
        total_lucro = sum(v.total_lucro for v in vendas)
        total_pecas = sum(v.total_pecas for v in vendas)
        
        print_info(f"Total vendido: {format_currency(total_vendido)}")
        print_info(f"Total de lucro: {format_currency(total_lucro)}")
        print_info(f"Total de peças: {total_pecas}")
        
        # Validação via query agregada (exclui canceladas)
        vendas_query = (
            db.query(
                func.coalesce(func.sum(Sale.total_vendido), 0.0),
                func.coalesce(func.sum(Sale.total_lucro), 0.0),
                func.coalesce(func.sum(Sale.total_pecas), 0),
            )
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .one()
        )
        total_v_query, total_l_query, total_p_query = vendas_query
        
        print_info("\nValidação via query agregada:")
        print_info(f"  Total vendido: {format_currency(total_v_query)}")
        print_info(f"  Total de lucro: {format_currency(total_l_query)}")
        print_info(f"  Total de peças: {int(total_p_query)}")
        
        if abs(total_vendido - total_v_query) < 0.01:
            print_success("Validação: Totais conferem!")
        else:
            print_error(f"Divergência nos totais: {total_vendido} vs {total_v_query}")
            return False
        
        return True
    except Exception as e:
        print_error(f"Falha na validacao: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5b_edicao_venda_remover_item(db, sessao_aberta):
    """Teste 5b: Edição de venda - remover item (devolve estoque e recalcula totais)."""
    print_header("TESTE 5b: Edicao de venda - Remover item")
    try:
        vendas = (
            db.query(Sale)
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .order_by(Sale.id.desc())
            .all()
        )
        venda_com_itens = None
        for v in vendas:
            itens = list(v.itens)
            if len(itens) >= 2:
                venda_com_itens = v
                break
        if not venda_com_itens:
            print_info("Nenhuma venda com 2+ itens para testar remocao. Pulando.")
            return True

        itens_antes = list(venda_com_itens.itens)
        item_remover = itens_antes[0]
        produto = db.get(Product, item_remover.product_id)
        estoque_antes = float(produto.estoque_atual or 0)
        total_antes = float(venda_com_itens.total_vendido or 0)
        subtotal_item = float(item_remover.subtotal or 0)
        lucro_item = float(item_remover.lucro_item or 0)
        qtd_item = int(item_remover.quantidade or 0)

        # Simula remocao do item: devolve estoque, atualiza totais da venda, remove item
        produto.estoque_atual = estoque_antes + item_remover.quantidade
        venda_com_itens.total_vendido = (venda_com_itens.total_vendido or 0) - subtotal_item
        venda_com_itens.total_lucro = (venda_com_itens.total_lucro or 0) - lucro_item
        venda_com_itens.total_pecas = (venda_com_itens.total_pecas or 0) - qtd_item
        db.delete(item_remover)
        db.commit()
        db.refresh(venda_com_itens)
        db.refresh(produto)

        total_depois = float(venda_com_itens.total_vendido or 0)
        estoque_depois = float(produto.estoque_atual or 0)
        if abs((total_antes - subtotal_item) - total_depois) > 0.01:
            print_error(f"Total venda apos remocao incorreto: esperado {total_antes - subtotal_item}, obtido {total_depois}")
            return False
        if abs((estoque_antes + qtd_item) - estoque_depois) > 0.01:
            print_error(f"Estoque apos devolucao incorreto: esperado {estoque_antes + qtd_item}, obtido {estoque_depois}")
            return False
        print_success("Item removido da venda; estoque devolvido e totais recalculados.")
        print_info(f"  Total venda: {format_currency(total_antes)} -> {format_currency(total_depois)}")
        print_info(f"  Estoque {produto.codigo}: {estoque_antes} -> {estoque_depois}")
        return True
    except Exception as e:
        print_error(f"Falha no teste de edicao (remover item): {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5c_storno(db, sessao_aberta):
    """Teste 5c: Stornar venda (status cancelada, devolve estoque). Totais da sessão excluem canceladas."""
    print_header("TESTE 5c: Storno de venda")
    try:
        vendas_ativas = (
            db.query(Sale)
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .all()
        )
        if not vendas_ativas:
            print_info("Nenhuma venda ativa para stornar. Pulando.")
            return True
        venda_storno = vendas_ativas[0]
        total_storno = float(venda_storno.total_vendido or 0)
        total_sessao_antes = (
            db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .scalar()
        )
        for item in venda_storno.itens:
            prod = db.get(Product, item.product_id)
            if prod:
                prod.estoque_atual = (prod.estoque_atual or 0) + item.quantidade
        venda_storno.status = "cancelada"
        db.commit()

        total_sessao_depois = (
            db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .scalar()
        )
        if abs((total_sessao_antes - total_storno) - total_sessao_depois) > 0.01:
            print_error(f"Total da sessao apos storno: esperado {total_sessao_antes - total_storno}, obtido {total_sessao_depois}")
            return False
        print_success("Venda stornada; estoque devolvido e total da sessao exclui cancelada.")
        print_info(f"  Total sessao (ativas): {format_currency(total_sessao_antes)} -> {format_currency(total_sessao_depois)}")
        return True
    except Exception as e:
        print_error(f"Falha no teste de storno: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_relatorios(db):
    """Teste 6: Geração de relatórios."""
    print_header("TESTE 6: Relatórios")
    try:
        hoje = date.today()
        
        # Relatório Diário
        print_info("\nRelatório Diário:")
        vendas_diarias = (
            db.query(
                func.coalesce(func.sum(Sale.total_vendido), 0.0),
                func.coalesce(func.sum(Sale.total_lucro), 0.0),
                func.coalesce(func.sum(Sale.total_pecas), 0),
                func.count(Sale.id),
            )
            .filter(Sale.data_venda == hoje)
            .filter(Sale.status != "cancelada")
            .one()
        )
        total_v, total_l, total_p, num_v = vendas_diarias
        margem = (total_l / total_v * 100) if total_v > 0 else 0.0
        ticket_medio = (total_v / num_v) if num_v > 0 else 0.0
        
        print_info(f"  Total vendido: {format_currency(total_v)}")
        print_info(f"  Total de lucro: {format_currency(total_l)}")
        print_info(f"  Margem: {margem:.2f}%")
        print_info(f"  Peças vendidas: {int(total_p)}")
        print_info(f"  Nº de vendas: {num_v}")
        print_info(f"  Ticket médio: {format_currency(ticket_medio)}")
        
        # Produtos mais vendidos
        print_info("\nProdutos mais vendidos (hoje):")
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
            .filter(Sale.data_venda == hoje)
            .filter(Sale.status != "cancelada")
            .group_by(Product.codigo, Product.nome)
            .order_by(func.sum(SaleItem.quantidade).desc())
            .limit(5)
            .all()
        )
        
        if top_itens:
            for cod, nome, qtd, receita, lucro in top_itens:
                print_info(f"  {cod} - {nome}: Qtd={qtd:.0f} | "
                          f"Receita={format_currency(receita)} | Lucro={format_currency(lucro)}")
        else:
            print_info("  Nenhum produto vendido hoje")
        
        # Valor de estoque atual
        print_info("\nValor de estoque (atual):")
        produtos_estoque = db.query(Product).all()
        valor_estoque_custo = sum(
            (p.preco_custo or 0) * (p.estoque_atual or 0) for p in produtos_estoque
        )
        valor_estoque_venda = sum(
            (p.preco_venda or 0) * (p.estoque_atual or 0) for p in produtos_estoque
        )
        print_info(f"  Estoque a custo: {format_currency(valor_estoque_custo)}")
        print_info(f"  Estoque a venda: {format_currency(valor_estoque_venda)}")
        
        print_success("Relatórios gerados com sucesso")
        return True
    except Exception as e:
        print_error(f"Falha na geração de relatórios: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_7_fechamento_caixa(db, sessao_aberta):
    """Teste 7: Fechamento de caixa."""
    print_header("TESTE 7: Fechamento de Caixa")
    try:
        # Calcula total de vendas (exclui canceladas)
        total_vendas = (
            db.query(func.coalesce(func.sum(Sale.total_vendido), 0.0))
            .filter(Sale.cash_session_id == sessao_aberta.id)
            .filter(Sale.status != "cancelada")
            .scalar()
        )
        
        valor_fechamento = sessao_aberta.valor_abertura + total_vendas
        
        print_info(f"Valor de abertura: {format_currency(sessao_aberta.valor_abertura)}")
        print_info(f"Total de vendas: {format_currency(total_vendas)}")
        print_info(f"Valor esperado no fechamento: {format_currency(valor_fechamento)}")
        
        # Fecha o caixa
        sessao_aberta.valor_fechamento = valor_fechamento
        sessao_aberta.status = "fechada"
        sessao_aberta.data_fechamento = datetime.utcnow()
        db.commit()
        db.refresh(sessao_aberta)
        
        print_success("Caixa fechado com sucesso")
        print_info(f"Data de fechamento: {sessao_aberta.data_fechamento}")
        print_info(f"Valor no fechamento: {format_currency(valor_fechamento)}")
        
        return True
    except Exception as e:
        print_error(f"Falha no fechamento de caixa: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Executa todos os testes."""
    print("\n" + "=" * 70)
    print("  TESTE COMPLETO DO SISTEMA PDV")
    print("  Testando desde abertura de caixa até relatórios")
    print("=" * 70)
    
    resultados = {}
    
    # Teste 1: Inicialização
    resultados["inicializacao"] = test_1_inicializacao()
    if not resultados["inicializacao"]:
        print("\n[ERRO] Falha na inicializacao. Abortando testes.")
        return
    
    db = SessionLocal()
    try:
        # Teste 2: Produtos
        resultados["produtos"] = test_2_produtos(db)
        if not resultados["produtos"]:
            print("\n[ATENCAO] Produtos nao encontrados apos tentativa de seed.")
            print("   Continuando com os testes disponiveis...")
        
        # Teste 3: Abertura de caixa
        sessao_aberta = test_3_abertura_caixa(db)
        resultados["abertura_caixa"] = sessao_aberta is not None
        if not sessao_aberta:
            print("\n[ERRO] Falha na abertura de caixa. Abortando testes de vendas.")
            return
        
        # Teste 4: Vendas
        resultados["vendas"] = test_4_vendas(db, sessao_aberta)
        
        # Teste 5: Validação
        resultados["validacao"] = test_5_validacao_vendas(db, sessao_aberta)

        # Teste 5b: Edição de venda - remover item
        resultados["edicao_remover_item"] = test_5b_edicao_venda_remover_item(db, sessao_aberta)

        # Teste 5c: Storno de venda
        resultados["storno"] = test_5c_storno(db, sessao_aberta)
        
        # Teste 6: Relatórios
        resultados["relatorios"] = test_6_relatorios(db)
        
        # Teste 7: Fechamento de caixa
        resultados["fechamento_caixa"] = test_7_fechamento_caixa(db, sessao_aberta)
        
    finally:
        db.close()
    
    # Resumo final
    print_header("RESUMO DOS TESTES")
    total_testes = len(resultados)
    testes_ok = sum(1 for v in resultados.values() if v)
    
    for nome, sucesso in resultados.items():
        status = "[OK] PASSOU" if sucesso else "[ERRO] FALHOU"
        print(f"  {nome.upper():.<50} {status}")
    
    print("\n" + "-" * 70)
    print(f"  Total: {testes_ok}/{total_testes} testes passaram")
    print("-" * 70)
    
    if testes_ok == total_testes:
        print("\n[SUCESSO] TODOS OS TESTES PASSARAM COM SUCESSO!")
    else:
        print(f"\n[ATENCAO] {total_testes - testes_ok} teste(s) falharam. Verifique os erros acima.")


if __name__ == "__main__":
    main()
