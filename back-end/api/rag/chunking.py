"""Etapa 3 do pipeline de RAG: quebra do conteudo em chunks.

A divisao e feita por PALAVRA, e nao por caractere, para nao partir palavra no
meio (o que degrada o embedding).

Sobre o tamanho: o modelo de embedding usado (paraphrase-multilingual-MiniLM-L12-v2)
tem janela de 128 tokens. Em portugues, uma palavra gera de 1,5 a 2 tokens, entao
chunks acima de ~80 palavras seriam truncados silenciosamente no momento de gerar
o vetor - parte do chunk ficaria indexada, parte nao. Por isso o padrao e 70
palavras com 15 de sobreposicao; a sobreposicao evita que uma resposta que cai
exatamente na fronteira entre dois chunks se perca.
"""

TAMANHO_PADRAO = 70
OVERLAP_PADRAO = 15


def criar_chunks(
    documentos: list[dict],
    tamanho: int = TAMANHO_PADRAO,
    overlap: int = OVERLAP_PADRAO,
) -> list[dict]:
    """Devolve [{chunk_id, documento_id, titulo, fonte, texto}]."""
    if overlap >= tamanho:
        raise ValueError("overlap deve ser menor que tamanho")

    chunks: list[dict] = []

    for doc in documentos:
        palavras = doc["texto"].split()
        inicio = 0
        numero_chunk = 1

        while inicio < len(palavras):
            fim = min(inicio + tamanho, len(palavras))
            texto_chunk = " ".join(palavras[inicio:fim])

            chunks.append({
                "chunk_id": f'{doc["id"]}_c{numero_chunk}',
                "documento_id": doc["id"],
                "titulo": doc["titulo"],
                "fonte": doc["fonte"],
                "texto": texto_chunk,
            })

            if fim == len(palavras):
                break

            inicio += tamanho - overlap
            numero_chunk += 1

    return chunks
