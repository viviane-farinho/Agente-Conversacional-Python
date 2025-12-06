"""
Script de migracao para criar tabelas do RAG Multi-Agente

Executa:
    python scripts/migrate_rag_multi.py

Este script:
1. Cria as tabelas empresa_documentos_multi e perguntas_sem_resposta_multi
2. Opcionalmente copia documentos do RAG simples para o multi (com coluna agente)
"""
import asyncio
import sys
import os

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import db_connect, db_get_pool
from src.services.rag_multi_infoprodutos import rag_multi_init_tables, rag_multi_add_document


async def migrate(copiar_docs: bool = False):
    """Executa a migracao"""
    print("=" * 60)
    print("MIGRACAO RAG MULTI-AGENTE")
    print("=" * 60)

    # Inicializa conexao com banco
    print("\n[1/3] Conectando ao banco de dados...")
    await db_connect()
    pool = await db_get_pool()
    print("    Conectado!")

    # Cria tabelas do RAG Multi
    print("\n[2/3] Criando tabelas do RAG Multi-Agente...")
    success = await rag_multi_init_tables()

    if success:
        print("    Tabelas criadas com sucesso!")
        print("    - empresa_documentos_multi")
        print("    - perguntas_sem_resposta_multi")
    else:
        print("    ERRO: Falha ao criar tabelas")
        return False

    # Copiar documentos do RAG simples (opcional)
    if copiar_docs:
        print("\n[3/3] Copiando documentos do RAG simples...")
        print("    Isso vai copiar todos os documentos de 'empresa_documentos'")
        print("    para 'empresa_documentos_multi' com agente=NULL (disponivel para todos)")
        await copiar_documentos_rag_simples(pool)
    else:
        print("\n[3/3] Pulando copia de documentos (use --copiar para copiar).")

    print("\n" + "=" * 60)
    print("MIGRACAO CONCLUIDA COM SUCESSO!")
    print("=" * 60)

    print("\nProximos passos:")
    print("1. Execute 'python scripts/popular_rag_multi.py' para popular a base do multi-agente")
    print("2. Ou adicione documentos via API/admin")

    return True


async def copiar_documentos_rag_simples(pool):
    """Copia documentos do RAG simples para o multi"""
    print("\n    Copiando documentos...")

    async with pool.acquire() as conn:
        # Verifica se tabela origem existe
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'empresa_documentos'
            )
        """)

        if not exists:
            print("    Tabela 'empresa_documentos' nao existe. Nada a copiar.")
            return

        # Busca documentos do RAG simples
        rows = await conn.fetch("""
            SELECT titulo, categoria, conteudo, metadata
            FROM empresa_documentos
            ORDER BY id
        """)

        if not rows:
            print("    Nenhum documento encontrado no RAG simples.")
            return

        print(f"    Encontrados {len(rows)} documentos para copiar...")

        # Copia cada documento
        for i, row in enumerate(rows):
            try:
                doc_id = await rag_multi_add_document(
                    titulo=row["titulo"],
                    conteudo=row["conteudo"],
                    categoria=row["categoria"],
                    agente=None,  # Disponivel para todos os agentes
                    metadata=row["metadata"] if row["metadata"] else {}
                )
                print(f"    [{i+1}/{len(rows)}] Copiado: {row['titulo'][:50]}... (ID: {doc_id})")
            except Exception as e:
                print(f"    [{i+1}/{len(rows)}] ERRO ao copiar '{row['titulo'][:30]}...': {e}")

        print(f"\n    {len(rows)} documentos copiados!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migracao RAG Multi-Agente")
    parser.add_argument("--copiar", action="store_true", help="Copiar documentos do RAG simples")
    args = parser.parse_args()
    asyncio.run(migrate(copiar_docs=args.copiar))
