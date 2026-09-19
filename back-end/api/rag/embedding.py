"""Etapa 4 do pipeline de RAG: geracao de embeddings.

Modelo de embedding multilingue. O all-MiniLM-L6-v2 foi treinado em ingles;
com documentos em portugues a similaridade calculada era praticamente ruido.
paraphrase-multilingual-MiniLM-L12-v2 e o modelo usado no material da
disciplina justamente por entender portugues.

Separado de vectorstore.py porque a escolha do modelo (e uma eventual troca de
modelo) e uma decisao independente de qual banco vetorial guarda os vetores.
"""

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

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
