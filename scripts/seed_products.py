"""
Seed de produtos fictícios para testes do PDV.
Pode ser executado em ambiente local ou de produção (cuidado ao rodar em produção).
"""
from config.database import SessionLocal, init_db
from models.product import Product


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        base_produtos = [
            # Vestidos
            dict(
                codigo="VEST001",
                nome="Vestido Midi Floral",
                categoria="Vestido",
                marca="Floratta",
                preco_custo=80.0,
                preco_venda=179.9,
                estoque_atual=15,
                estoque_minimo=5,
            ),
            dict(
                codigo="VEST002",
                nome="Vestido Longo Preto",
                categoria="Vestido",
                marca="Urban Chic",
                preco_custo=95.0,
                preco_venda=219.9,
                estoque_atual=10,
                estoque_minimo=4,
            ),
            # Calças
            dict(
                codigo="CALC001",
                nome="Calça Jeans Skinny Azul",
                categoria="Calça",
                marca="Denim Co",
                preco_custo=70.0,
                preco_venda=159.9,
                estoque_atual=20,
                estoque_minimo=6,
            ),
            dict(
                codigo="CALC002",
                nome="Calça Alfaiataria Preta",
                categoria="Calça",
                marca="Office Line",
                preco_custo=85.0,
                preco_venda=199.9,
                estoque_atual=12,
                estoque_minimo=4,
            ),
            # Blusas
            dict(
                codigo="BLUS001",
                nome="Blusa Básica Branca",
                categoria="Blusa",
                marca="Cotton Wear",
                preco_custo=25.0,
                preco_venda=69.9,
                estoque_atual=40,
                estoque_minimo=10,
            ),
            dict(
                codigo="BLUS002",
                nome="Blusa Estampada Colorida",
                categoria="Blusa",
                marca="Summer Vibes",
                preco_custo=35.0,
                preco_venda=89.9,
                estoque_atual=25,
                estoque_minimo=8,
            ),
            # Saias
            dict(
                codigo="SAIA001",
                nome="Saia Midi Plissada",
                categoria="Saia",
                marca="Elegance",
                preco_custo=60.0,
                preco_venda=149.9,
                estoque_atual=14,
                estoque_minimo=4,
            ),
            dict(
                codigo="SAIA002",
                nome="Saia Jeans Curta",
                categoria="Saia",
                marca="Denim Co",
                preco_custo=55.0,
                preco_venda=129.9,
                estoque_atual=18,
                estoque_minimo=5,
            ),
            # Camisetas / T-shirts
            dict(
                codigo="TSHIRT001",
                nome="Camiseta Lisa Preta",
                categoria="Camiseta",
                marca="Basic Line",
                preco_custo=20.0,
                preco_venda=59.9,
                estoque_atual=50,
                estoque_minimo=15,
            ),
            dict(
                codigo="TSHIRT002",
                nome="Camiseta Estampada",
                categoria="Camiseta",
                marca="Street Art",
                preco_custo=28.0,
                preco_venda=79.9,
                estoque_atual=30,
                estoque_minimo=10,
            ),
            # Jaquetas
            dict(
                codigo="JAQ001",
                nome="Jaqueta Jeans Oversized",
                categoria="Jaqueta",
                marca="Denim Co",
                preco_custo=120.0,
                preco_venda=269.9,
                estoque_atual=8,
                estoque_minimo=3,
            ),
            dict(
                codigo="JAQ002",
                nome="Jaqueta de Couro Sintético",
                categoria="Jaqueta",
                marca="Night Rider",
                preco_custo=140.0,
                preco_venda=299.9,
                estoque_atual=6,
                estoque_minimo=2,
            ),
        ]

        created, updated = 0, 0
        for data in base_produtos:
            prod = db.query(Product).filter(Product.codigo == data["codigo"]).first()
            if prod:
                prod.nome = data["nome"]
                prod.categoria = data["categoria"]
                prod.marca = data["marca"]
                prod.preco_custo = data["preco_custo"]
                prod.preco_venda = data["preco_venda"]
                prod.estoque_atual = data["estoque_atual"]
                prod.estoque_minimo = data["estoque_minimo"]
                updated += 1
            else:
                prod = Product(**data)
                db.add(prod)
                created += 1

        db.commit()
        print(f"Produtos criados: {created}, atualizados: {updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

