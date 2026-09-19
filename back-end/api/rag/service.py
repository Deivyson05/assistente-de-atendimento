"""Fachada do pipeline de RAG: compoe ingestao, chunking, embedding, indice e
recuperacao atras de uma unica interface.

Antes essa composicao (construir o indice e instanciar o Retriever) vivia
dentro do ChatService, como uma property preguicosa. Extrair para ca deixa o
ChatService livre de saber como o RAG e montado por dentro, e torna o
pipeline testavel e reutilizavel isoladamente do chat.
"""

from api.rag.retrieval import Retriever
from api.rag.vectorstore import construir_indice
from api.settings import settings


class RagService:
    def __init__(self, docs_folder: str | None = None):
        self.docs_folder = docs_folder or settings.rag_docs_folder
        self._retriever: Retriever | None = None

    def get_retriever(self) -> Retriever:
        """Constroi o indice na primeira utilizacao, nao no import do modulo.

        Antes o indice era montado assim que o router do chat era importado,
        o que fazia o servidor so subir depois de baixar o modelo de embedding
        e indexar todos os PDFs.
        """
        if self._retriever is None:
            colecao = construir_indice(
                pasta_docs=self.docs_folder,
                caminho_indice=settings.rag_index_path,
                modelo=settings.rag_embedding_model,
                chunk_tamanho=settings.rag_chunk_tamanho,
                chunk_overlap=settings.rag_chunk_overlap,
            )
            self._retriever = Retriever(
                colecao,
                top_k=settings.rag_top_k,
                limiar=settings.rag_limiar_evidencia,
            )
        return self._retriever
