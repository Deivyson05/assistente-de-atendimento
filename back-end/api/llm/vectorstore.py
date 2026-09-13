"""Etapas 4 e 5 do pipeline de RAG: embeddings e indice vetorial.

Duas correcoes importantes em relacao a versao anterior:

1. Modelo de embedding multilingue. O all-MiniLM-L6-v2 foi treinado em ingles;
   com documentos em portugues a similaridade calculada era praticamente ruido.
   paraphrase-multilingual-MiniLM-L12-v2 e o modelo usado no material da
   disciplina justamente por entender portugues.

2. Indice persistente. chromadb.Client() e efemero: vive na RAM do processo e
   e reconstruido a cada restart. PersistentClient grava em disco, entao os
   embeddings sao gerados uma vez e reaproveitados.

O indice guarda a impressao digital da pasta de documentos. Se um PDF for
adicionado, removido ou alterado, o indice e reconstruido automaticamente.
"""

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from api.llm.chunk import criar_chunks
from api.llm.load_documents import carregar_documentos, impressao_digital

# Chroma tem limite pratico por chamada; enviar em lote e ordens de grandeza
# mais rapido do que uma chamada por chunk.
TAMANHO_LOTE = 256

_embedding_function = None


def get_embedding_function(modelo: str):
    """Carrega o modelo de embedding uma unica vez por processo."""
    global _embedding_function
    if _embedding_function is None:
        _embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=modelo,
            normalize_embeddings=True,
        )
    return _embedding_function


def similaridade(distancia: float) -> float:
    """Converte a distancia de cosseno do Chroma em similaridade [-1, 1].

    Com a colecao criada em hnsw:space=cosine, distancia = 1 - similaridade.
    Esse valor e o equivalente ao score do IndexFlatIP do FAISS com vetores
    normalizados, e e o numero comparado com o limiar de evidencia.
    """
    return 1.0 - float(distancia)


def _metadados_do_indice(modelo: str, digital: str, tamanho: int, overlap: int) -> dict:
    return {
        "hnsw:space": "cosine",
        "modelo_embedding": modelo,
        "impressao_digital": digital,
        "chunk_tamanho": str(tamanho),
        "chunk_overlap": str(overlap),
    }


def _esta_atualizado(colecao, esperado: dict) -> bool:
    atual = colecao.metadata or {}
    if colecao.count() == 0:
        return False
    return all(
        str(atual.get(chave)) == str(valor)
        for chave, valor in esperado.items()
        if chave != "hnsw:space"
    )


def construir_indice(
    pasta_docs: str,
    caminho_indice: str,
    modelo: str,
    colecao_nome: str = "docs",
    chunk_tamanho: int = 70,
    chunk_overlap: int = 15,
    forcar: bool = False,
    verbose: bool = True,
):
    """Garante um indice atualizado em disco e devolve a colecao pronta para busca."""
    digital = impressao_digital(pasta_docs)
    esperado = _metadados_do_indice(modelo, digital, chunk_tamanho, chunk_overlap)

    client = chromadb.PersistentClient(path=caminho_indice)
    ef = get_embedding_function(modelo)

    colecao = client.get_or_create_collection(
        name=colecao_nome,
        embedding_function=ef,
        metadata=esperado,
    )

    if not forcar and _esta_atualizado(colecao, esperado):
        if verbose:
            print(f"[RAG] Indice reaproveitado: {colecao.count()} chunks.")
        return colecao

    # Documentos mudaram (ou o modelo/parametros mudaram): reconstruir do zero.
    if verbose:
        print("[RAG] Indice desatualizado ou inexistente. Reconstruindo...")
    client.delete_collection(colecao_nome)
    colecao = client.get_or_create_collection(
        name=colecao_nome,
        embedding_function=ef,
        metadata=esperado,
    )

    documentos = carregar_documentos(pasta_docs)
    if verbose:
        print(f"[RAG] Documentos carregados: {len(documentos)}")
        for doc in documentos:
            print(f"       - {doc['fonte']} ({len(doc['texto'])} chars)")

    chunks = criar_chunks(documentos, tamanho=chunk_tamanho, overlap=chunk_overlap)
    if verbose:
        print(f"[RAG] Chunks gerados: {len(chunks)}")

    if not chunks:
        raise RuntimeError(
            f"Nenhum chunk gerado a partir de {pasta_docs}. "
            "Verifique se os PDFs existem e possuem texto extraivel."
        )

    for inicio in range(0, len(chunks), TAMANHO_LOTE):
        lote = chunks[inicio:inicio + TAMANHO_LOTE]
        colecao.add(
            ids=[c["chunk_id"] for c in lote],
            documents=[c["texto"] for c in lote],
            metadatas=[
                {
                    "documento_id": c["documento_id"],
                    "titulo": c["titulo"],
                    "fonte": c["fonte"],
                }
                for c in lote
            ],
        )
        if verbose:
            print(f"[RAG] Indexados {min(inicio + TAMANHO_LOTE, len(chunks))}/{len(chunks)}")

    if verbose:
        print(f"[RAG] Indice pronto em {caminho_indice} ({colecao.count()} chunks).")
    return colecao
