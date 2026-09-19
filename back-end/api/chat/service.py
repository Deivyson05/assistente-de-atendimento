"""Orquestração do assistente: RAG para dúvidas + fluxo conversacional de agendamento.

O fluxo em si (etapas 6 a 10) é um grafo do LangGraph — ver api/chat/graph.py.
Este módulo cuida do que fica FORA do grafo, por request: obter/persistir a
sessão da conversa e resolver o dado de negócio (lista de serviços) que entra
no prompt.
"""

import time

from api.chat.graph import ChatGraph
from api.chat.session_store import SessionStore
from api.chat.tools import ToolRouter
from api.llm.base import LLMProvider
from api.llm.groq_provider import GroqProvider
from api.prompt.servicos import carregar_servicos
from api.rag.service import RagService
from api.services.horario_marcado_service import HorarioMarcadoService
from api.services.prestador_service import PrestadorService
from api.settings import settings

# Serviços mudam pouco; evita uma consulta ao banco a cada chamada da LLM.
_TTL_SERVICOS = 300


class ChatService:
    def __init__(
        self,
        prestador_service: PrestadorService,
        horario_marcado_service: HorarioMarcadoService,
        docs_folder: str | None = None,
        llm: LLMProvider | None = None,
        rag: RagService | None = None,
    ):
        self.llm = llm or GroqProvider()
        self.rag = rag or RagService(docs_folder)
        self.tools = ToolRouter(prestador_service, horario_marcado_service)
        self.sessions = SessionStore(settings.historico_max_mensagens)
        self.graph = ChatGraph(self)

        self._servicos_cache: tuple[float, str] | None = None

    # ------------------------------------------------------------------
    # Índice vetorial (etapas 4 e 5) — delegado ao RagService
    # ------------------------------------------------------------------
    @property
    def retriever(self):
        return self.rag.get_retriever()

    def preparar_indice(self) -> None:
        """Força a construção do índice (usado no startup da API)."""
        self.rag.get_retriever()

    # ------------------------------------------------------------------
    # Serviços disponíveis (dado de negócio injetado no prompt)
    # ------------------------------------------------------------------
    def _servicos(self) -> str:
        agora = time.time()
        if self._servicos_cache and agora - self._servicos_cache[0] < _TTL_SERVICOS:
            return self._servicos_cache[1]
        servicos = carregar_servicos()
        self._servicos_cache = (agora, servicos)
        return servicos

    # ------------------------------------------------------------------
    # Entrada principal — delega a execução do turno ao grafo
    # ------------------------------------------------------------------
    def send_message(self, message: str, session_id: str = "default") -> str:
        sessao = self.sessions.obter(session_id)

        resultado = self.graph.executar(
            pergunta=message,
            session_id=session_id,
            historico=sessao["historico"],
            em_agendamento=sessao["em_agendamento"],
            servicos=self._servicos(),
        )

        sessao["historico"] = resultado["historico"]
        sessao["em_agendamento"] = resultado.get("em_agendamento", sessao["em_agendamento"])
        return resultado["resposta"]
