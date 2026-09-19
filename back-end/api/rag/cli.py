"""Construção do índice vetorial fora do ciclo de request.

Uso:
    python -m api.rag.cli            # indexa se houver mudança
    python -m api.rag.cli --forcar   # reconstrói do zero
    python -m api.rag.cli --testar "vocês atendem convênio?"

Rodar isso uma vez antes de subir o servidor evita que a primeira requisição
pague o custo de ler os PDFs e gerar todos os embeddings.
"""

import sys

from api.rag.retrieval import Retriever
from api.rag.vectorstore import construir_indice
from api.settings import settings


def main() -> int:
    forcar = "--forcar" in sys.argv

    pergunta = None
    if "--testar" in sys.argv:
        posicao = sys.argv.index("--testar")
        if posicao + 1 < len(sys.argv):
            pergunta = sys.argv[posicao + 1]
        else:
            print("Uso: python -m api.rag.cli --testar \"sua pergunta\"")
            return 1

    colecao = construir_indice(
        pasta_docs=settings.rag_docs_folder,
        caminho_indice=settings.rag_index_path,
        modelo=settings.rag_embedding_model,
        chunk_tamanho=settings.rag_chunk_tamanho,
        chunk_overlap=settings.rag_chunk_overlap,
        forcar=forcar,
    )

    if not pergunta:
        return 0

    retriever = Retriever(
        colecao,
        top_k=settings.rag_top_k,
        limiar=settings.rag_limiar_evidencia,
    )
    recuperados = retriever.recuperar(pergunta)

    print("\n" + "=" * 80)
    print("PERGUNTA:", pergunta)
    print("=" * 80)

    for posicao, item in enumerate(recuperados, start=1):
        barra = "#" * max(0, int(item["score"] * 40))
        print(f"\n{posicao}. {item['chunk_id']} | score={item['score']:.4f} {barra}")
        print(f"   fonte: {item['fonte']}")
        print(f"   {item['texto'][:300]}")

    print("\n" + "-" * 80)
    print(f"Score máximo: {retriever.score_maximo(recuperados):.4f}")
    print(f"Limiar configurado: {settings.rag_limiar_evidencia}")
    print(
        "Decisão:",
        "COM evidência -> chama a LLM"
        if retriever.decidir_evidencia(recuperados)
        else "SEM evidência -> abstém",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
