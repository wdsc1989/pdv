"""
Reseta vendas e sessões de caixa e cria novas vendas de teste
para validação visual dos relatórios no Streamlit.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

# Garante que o diretório raiz esteja no sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.database import SessionLocal, init_db
from models.cash_session import CashSession
from models.product import Product
from models.sale import Sale, SaleItem


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        # Primeiro, garante produtos base do seed
        try:
            from scripts.seed_products import main as seed_main

            seed_main()
        except Exception:
            # Se por algum motivo o seed falhar, seguimos apenas com o que existir
            pass

        # Limpa vendas e sessões de caixa atuais
        db.query(SaleItem).delete()
        db.query(Sale).delete()
        db.query(CashSession).delete()
        db.commit()

        # Abre uma nova sessão de caixa para os testes
        sessao = CashSession(
            valor_abertura=100.0,
            observacao="Sessão de teste para relatórios",
            status="aberta",
        )
        db.add(sessao)
        db.commit()
        db.refresh(sessao)

        produtos = (
            db.query(Product)
            .order_by(Product.codigo)
            .limit(5)
            .all()
        )
        if len(produtos) < 3:
            print("Poucos produtos para montar vendas de teste.")
            return

        hoje = date.today()

        def cria_venda(
            data_venda: date,
            itens_info: list[tuple[Product, int]],
            tipo_pagamento: str,
        ) -> None:
            total_vendido = 0.0
            total_lucro = 0.0
            total_pecas = 0

            venda = Sale(
                cash_session_id=sessao.id,
                data_venda=data_venda,
                total_vendido=0.0,
                total_lucro=0.0,
                total_pecas=0,
                tipo_pagamento=tipo_pagamento,
                status="concluida",
            )
            db.add(venda)
            db.flush()

            for prod, qtd in itens_info:
                qtd = int(qtd)
                subtotal = (prod.preco_venda or 0.0) * qtd
                lucro_item = ((prod.preco_venda or 0.0) - (prod.preco_custo or 0.0)) * qtd
                total_vendido += subtotal
                total_lucro += lucro_item
                total_pecas += qtd

                prod.estoque_atual = (prod.estoque_atual or 0) - qtd

                db.add(
                    SaleItem(
                        sale_id=venda.id,
                        product_id=prod.id,
                        quantidade=qtd,
                        preco_unitario=prod.preco_venda or 0.0,
                        preco_custo_unitario=prod.preco_custo or 0.0,
                        subtotal=subtotal,
                        lucro_item=lucro_item,
                    )
                )

            venda.total_vendido = total_vendido
            venda.total_lucro = total_lucro
            venda.total_pecas = total_pecas
            db.commit()

        # Vendas de teste:
        # - Hoje: 2 itens
        cria_venda(
            data_venda=hoje,
            itens_info=[(produtos[0], 2), (produtos[1], 1)],
            tipo_pagamento="dinheiro",
        )

        # - Ontem: 1 item
        cria_venda(
            data_venda=hoje - timedelta(days=1),
            itens_info=[(produtos[2], 3)],
            tipo_pagamento="credito",
        )

        # - Há 5 dias (ainda dentro da semana)
        cria_venda(
            data_venda=hoje - timedelta(days=5),
            itens_info=[(produtos[1], 1), (produtos[3], 2)],
            tipo_pagamento="pix",
        )

        # - Há 20 dias (ainda dentro do mês, se mês tiver 30/31 dias)
        cria_venda(
            data_venda=hoje - timedelta(days=20),
            itens_info=[(produtos[4], 1)],
            tipo_pagamento="debito",
        )

        print("Vendas de teste criadas com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

