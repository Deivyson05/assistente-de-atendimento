"""Etapa 5 do pipeline de RAG: armazenamento em indice vetorial.

Indice persistente. chromadb.Client() e efemero: vive na RAM do processo e e
reconstruido a cada restart. PersistentClient grava em disco, entao os
embeddings sao gerados uma vez e reaproveitados.

O indice guarda a impressao digital da pasta de documentos. Se um PDF for
adicionado, removido ou alterado, o indice e reconstruido automaticamente.

Este modulo cuida apenas da persistencia; a geracao do embedding em si esta em
embedding.py, e a leitura/chunking dos documentos em ingestion.py/chunking.py.
"""

import chromadb

from api.rag.chunking import criar_chunks
from api.rag.embedding import get_embedding_function
from api.rag.ingestion import carregar_documentos, impressao_digital

# Chroma tem limite pratico por chamada; enviar em lote e ordens de grandeza
# mais rapido do que uma chamada por chunk.
TAMANHO_LOTE = 256


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
