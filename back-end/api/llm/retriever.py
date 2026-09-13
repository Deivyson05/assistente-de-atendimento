"""Etapas 7 e 8 do pipeline de RAG: recuperacao e montagem do contexto.

A versao anterior devolvia apenas os textos dos chunks, jogando fora score e
metadados. Sem o score nao e possivel saber se a busca encontrou evidencia:
a busca vetorial SEMPRE devolve os k vizinhos mais proximos, mesmo quando
nenhum deles responde a pergunta.

Aqui o score e preservado e comparado com um limiar. Essa e a decisao que o
material da disciplina implementa como aresta condicional no LangGraph:

    recuperar -> decidir_evidencia -> montar_contexto -> gerar_resposta
                                   -> sem_evidencia
"""

from api.llm.vectorstore import similaridade

RESPOSTA_SEM_EVIDENCIA = "Nao encontrei essa informacao na base consultada."

# Perguntas curtas costumam ser anaforicas ("e o preco?", "e amanha?") e nao
# carregam o assunto. Abaixo desse numero de palavras, a pergunta anterior do
# usuario e concatenada antes de gerar o vetor de busca.
_LIMITE_PERGUNTA_CURTA = 6


class Retriever:
    def __init__(self, colecao, top_k: int = 5, limiar: float = 0.35):
        self.colecao = colecao
        self.top_k = top_k
        self.limiar = limiar

    def montar_query(self, pergunta: str, perguntas_anteriores: list[str]) -> str:
        """Etapa 6.5: reformulacao leve da pergunta usando o historico.

        Sem isso, numa conversa multi-turn a mensagem "e quanto custa?" gera um
        vetor sem assunto nenhum e a recuperacao falha.
        """
        pergunta = pergunta.strip()
        if len(pergunta.split()) >= _LIMITE_PERGUNTA_CURTA or not perguntas_anteriores:
            return pergunta
        return f"{perguntas_anteriores[-1]} {pergunta}".strip()

    def recuperar(self, pergunta: str, top_k: int | None = None) -> list[dict]:
        """Devolve [{texto, titulo, fonte, chunk_id, score}] ordenado por score."""
        if not pergunta.strip():
            return []

        k = top_k or self.top_k
        resultado = self.colecao.query(
            query_texts=[pergunta],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        documentos = resultado.get("documents") or [[]]
        if not documentos or not documentos[0]:
            return []

        metadatas = (resultado.get("metadatas") or [[]])[0]
        distancias = (resultado.get("distances") or [[]])[0]
        ids = (resultado.get("ids") or [[]])[0]

        recuperados = []
        for posicao, texto in enumerate(documentos[0]):
            meta = metadatas[posicao] if posicao < len(metadatas) else {}
            distancia = distancias[posicao] if posicao < len(distancias) else 1.0
            recuperados.append({
                "chunk_id": ids[posicao] if posicao < len(ids) else str(posicao),
                "texto": texto,
                "titulo": (meta or {}).get("titulo", "Documento"),
                "fonte": (meta or {}).get("fonte", ""),
                "score": similaridade(distancia),
            })

        return recuperados

    def score_maximo(self, recuperados: list[dict]) -> float:
        return max((r["score"] for r in recuperados), default=0.0)

    def decidir_evidencia(self, recuperados: list[dict]) -> bool:
        """True quando ha evidencia suficiente para acionar a LLM."""
        return self.score_maximo(recuperados) >= self.limiar

    def filtrar_relevantes(self, recuperados: list[dict]) -> list[dict]:
        """Descarta a cauda fraca do ranking.

        Mantem o melhor chunk e todos os que estao a no maximo 0,12 de distancia
        dele; chunks muito abaixo do topo so gastam contexto e confundem o modelo.
        """
        if not recuperados:
            return []
        teto = self.score_maximo(recuperados)
        return [r for r in recuperados if r["score"] >= min(self.limiar, teto - 0.12)]

    def montar_contexto(self, recuperados: list[dict]) -> str:
        """Etapa 8: contexto rotulado por fonte, para a resposta poder citar."""
        if not recuperados:
            return ""
        return "\n\n".join(
            f"[Fonte {i + 1} - {r['titulo']}]\n{r['texto']}"
            for i, r in enumerate(recuperados)
        )
