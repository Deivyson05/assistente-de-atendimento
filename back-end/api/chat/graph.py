"""Orquestração do assistente como um grafo do LangGraph.

Nós do fluxo principal, na ordem pedida pela atividade:

    entrada -> recuperar -> [decidir_caminho] -> montar_prompt -> gerar -> retorno
                                               -> abster ------------------> retorno

`decidir_caminho` é a aresta condicional central do RAG: a busca vetorial
SEMPRE devolve os k vizinhos mais próximos, mesmo quando nenhum responde à
pergunta, então o grafo decide se há evidência suficiente ANTES de acionar a
LLM. Sem evidência e sem ser um turno de agendamento, vai direto para
`abster`, sem gastar uma chamada de LLM.

O nó `gerar` pode pedir uma ferramenta (tool calling manual por JSON, já que o
modelo não tem function calling nativo). Isso é modelado como um ciclo:

    gerar -> [decidir_ferramenta] -> executar_ferramenta -> gerar (de novo)
                                   -> limite_atingido -> retorno
                                   -> retorno (resposta pronta, sem ferramenta)

O ciclo é limitado por `chamadas_llm` no estado, para nunca rodar
indefinidamente caso o modelo insista em pedir ferramentas.
"""

from typing import TYPE_CHECKING, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from api.chat.tools import MARCADOR_FERRAMENTA, extrair_acao, sanitizar
from api.chat.turn_classifier import parece_agendamento, parece_pergunta
from api.prompt.mika import RESPOSTA_SEM_EVIDENCIA, build_system_prompt
from api.settings import settings

if TYPE_CHECKING:
    from api.chat.service import ChatService


class ChatState(TypedDict, total=False):
    # fornecidos por ChatService ao invocar o grafo (etapa 6: entrada da pergunta)
    pergunta: str
    session_id: str
    historico: list[dict]
    em_agendamento: bool
    servicos: str

    # preenchidos pelos nós do grafo
    query: str
    recuperados: list[dict]
    score_maximo: float
    com_evidencia: bool
    contexto: str
    system_prompt: str
    resposta: str
    acao: dict | None
    chamadas_llm: int
    finalizado: bool


class ChatGraph:
    """Compila e executa o StateGraph do assistente.

    Guarda uma referência ao ChatService (não cópias de rag/llm/tools/sessions)
    e lê `self.service.rag`, `.llm`, `.tools`, `.sessions` a cada execução de
    nó — assim trocar o provedor de LLM ou o RagService no ChatService depois
    de construído (comum em testes, que injetam um fake) continua valendo,
    em vez de o grafo ficar preso ao objeto que existia na hora da construção.
    """

    def __init__(self, service: "ChatService"):
        self.service = service
        self._grafo = self._construir_grafo()

    def executar(
        self,
        pergunta: str,
        session_id: str,
        historico: list[dict],
        em_agendamento: bool,
        servicos: str,
    ) -> ChatState:
        estado_inicial: ChatState = {
            "pergunta": pergunta,
            "session_id": session_id,
            "historico": historico,
            "em_agendamento": em_agendamento,
            "servicos": servicos,
            "chamadas_llm": 0,
        }
        return self._grafo.invoke(estado_inicial)

    # ------------------------------------------------------------------
    # Construção do grafo
    # ------------------------------------------------------------------
    def _construir_grafo(self):
        builder = StateGraph(ChatState)

        builder.add_node("entrada", self._no_entrada)
        builder.add_node("recuperar", self._no_recuperar)
        builder.add_node("montar_prompt", self._no_montar_prompt)
        builder.add_node("abster", self._no_abster)
        builder.add_node("gerar", self._no_gerar)
        builder.add_node("executar_ferramenta", self._no_executar_ferramenta)
        builder.add_node("limite_atingido", self._no_limite_atingido)
        builder.add_node("retorno", self._no_retorno)

        builder.add_edge(START, "entrada")
        builder.add_edge("entrada", "recuperar")

        builder.add_conditional_edges(
            "recuperar",
            self._decidir_caminho,
            {"montar_prompt": "montar_prompt", "abster": "abster"},
        )
        builder.add_edge("montar_prompt", "gerar")

        builder.add_conditional_edges(
            "gerar",
            self._decidir_ferramenta,
            {
                "executar_ferramenta": "executar_ferramenta",
                "limite": "limite_atingido",
                "fim": "retorno",
            },
        )
        builder.add_conditional_edges(
            "executar_ferramenta",
            self._decidir_pos_ferramenta,
            {"gerar": "gerar", "retorno": "retorno"},
        )

        builder.add_edge("abster", "retorno")
        builder.add_edge("limite_atingido", "retorno")
        builder.add_edge("retorno", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Nó: entrada da pergunta (etapa 6)
    # ------------------------------------------------------------------
    def _no_entrada(self, estado: ChatState) -> dict:
        pergunta = sanitizar(estado["pergunta"])
        em_agendamento = estado["em_agendamento"] or parece_agendamento(pergunta)
        return {"pergunta": pergunta, "em_agendamento": em_agendamento}

    # ------------------------------------------------------------------
    # Nó: recuperação de contexto (etapas 6.5 e 7)
    # ------------------------------------------------------------------
    def _no_recuperar(self, estado: ChatState) -> dict:
        retriever = self.service.rag.get_retriever()
        historico = estado["historico"]

        # reformulação: pergunta curta herda o assunto da pergunta anterior
        query = retriever.montar_query(
            estado["pergunta"], self.service.sessions.perguntas_anteriores(historico)
        )
        recuperados = retriever.recuperar(query)
        score_maximo = retriever.score_maximo(recuperados)
        com_evidencia = retriever.decidir_evidencia(recuperados)

        if settings.debug:
            print(
                f"[RAG] sessao={estado['session_id']} score_max={score_maximo:.4f} "
                f"limiar={settings.rag_limiar_evidencia} evidencia={com_evidencia} "
                f"agendamento={estado['em_agendamento']} query={query!r}"
            )

        historico.append({"role": "user", "content": estado["pergunta"]})

        return {
            "historico": historico,
            "query": query,
            "recuperados": recuperados,
            "score_maximo": score_maximo,
            "com_evidencia": com_evidencia,
        }

    def _decidir_caminho(self, estado: ChatState) -> Literal["montar_prompt", "abster"]:
        """Aresta condicional: só aciona a LLM quando há evidência (ou é agendamento)."""
        sem_evidencia = not estado["com_evidencia"]
        e_pergunta = parece_pergunta(estado["pergunta"])
        if sem_evidencia and not estado["em_agendamento"] and e_pergunta:
            return "abster"
        return "montar_prompt"

    # ------------------------------------------------------------------
    # Nó: abstenção — pergunta sem evidência não chega a chamar a LLM
    # ------------------------------------------------------------------
    def _no_abster(self, estado: ChatState) -> dict:
        historico = estado["historico"]
        historico.append({"role": "assistant", "content": RESPOSTA_SEM_EVIDENCIA})
        return {"historico": historico, "resposta": RESPOSTA_SEM_EVIDENCIA}

    # ------------------------------------------------------------------
    # Nó: montagem do prompt (etapa 8)
    # ------------------------------------------------------------------
    def _no_montar_prompt(self, estado: ChatState) -> dict:
        retriever = self.service.rag.get_retriever()
        relevantes = (
            retriever.filtrar_relevantes(estado["recuperados"])
            if estado["com_evidencia"]
            else []
        )
        contexto = retriever.montar_contexto(relevantes)
        system_prompt = build_system_prompt(contexto, estado["servicos"])
        return {"contexto": contexto, "system_prompt": system_prompt}

    # ------------------------------------------------------------------
    # Nó: chamada da LLM (etapa 9)
    # ------------------------------------------------------------------
    def _no_gerar(self, estado: ChatState) -> dict:
        historico = estado["historico"]
        chamadas_llm = estado.get("chamadas_llm", 0) + 1

        try:
            resposta = self.service.llm.generate(
                estado["system_prompt"], self.service.sessions.janela(historico)
            )
        except Exception as erro:
            print(f"[CHAT] Falha na chamada da LLM: {erro}")
            return {
                "resposta": (
                    "Tive um problema para processar sua mensagem agora. "
                    "Pode tentar novamente em instantes?"
                ),
                "acao": None,
                "chamadas_llm": chamadas_llm,
            }

        historico.append({"role": "assistant", "content": resposta})
        acao, texto_limpo = extrair_acao(resposta)

        return {
            "historico": historico,
            "resposta": texto_limpo or resposta,
            "acao": acao,
            "chamadas_llm": chamadas_llm,
        }

    def _decidir_ferramenta(self, estado: ChatState) -> Literal["executar_ferramenta", "limite", "fim"]:
        if estado.get("acao") is None:
            return "fim"
        if estado["chamadas_llm"] > settings.max_passos_ferramenta:
            return "limite"
        return "executar_ferramenta"

    # ------------------------------------------------------------------
    # Nó: execução da ferramenta (ciclo — não é uma das 5 etapas nomeadas,
    # mas é a extensão de tool calling que o material sugere como evolução)
    # ------------------------------------------------------------------
    def _no_executar_ferramenta(self, estado: ChatState) -> dict:
        acao = estado["acao"]
        historico = estado["historico"]

        try:
            resultado = self.service.tools.executar(acao)
        except Exception as erro:
            print(f"[CHAT] Erro ao executar {acao.get('action')}: {erro}")
            resultado = '{"erro": "não foi possível executar a operação"}'

        if acao.get("action") == "agendar" and '"sucesso": true' in resultado.lower():
            sucesso = "Agendamento realizado com sucesso! ✅"
            historico.append({"role": "assistant", "content": sucesso})
            return {
                "historico": historico,
                "resposta": sucesso,
                "em_agendamento": False,
                "finalizado": True,
            }

        historico.append({
            "role": "user",
            "content": f"{MARCADOR_FERRAMENTA} {acao['action']}: {resultado}",
        })
        return {"historico": historico}

    def _decidir_pos_ferramenta(self, estado: ChatState) -> Literal["gerar", "retorno"]:
        return "retorno" if estado.get("finalizado") else "gerar"

    # ------------------------------------------------------------------
    # Nó: limite de rodadas de ferramenta atingido
    # ------------------------------------------------------------------
    def _no_limite_atingido(self, estado: ChatState) -> dict:
        print("[CHAT] Limite de passos de ferramenta atingido.")
        return {
            "resposta": (
                "Não consegui concluir essa operação agora. "
                "Pode repetir o que você precisa?"
            )
        }

    # ------------------------------------------------------------------
    # Nó: retorno da resposta (etapa 10)
    # ------------------------------------------------------------------
    def _no_retorno(self, estado: ChatState) -> dict:
        return {"resposta": estado.get("resposta") or "Não consegui gerar uma resposta agora."}
