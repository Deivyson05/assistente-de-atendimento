"""Orquestração do assistente: RAG para dúvidas + fluxo conversacional de agendamento.

Pipeline executado a cada mensagem (etapas 6 a 10):

    pergunta -> reformulação -> recuperação -> decisão de evidência
             -> contexto -> LLM -> (comando JSON -> ferramenta -> LLM)* -> resposta

A decisão de evidência é a aresta condicional do material: se a busca vetorial
não trouxe nada suficientemente próximo e o turno é uma pergunta, o assistente
se abstém sem nem chamar a LLM.
"""

import json
import re
import time

from groq import Groq

from api.llm.carregar_servicos import carregar_servicos
from api.llm.prompt import build_system_prompt
from api.llm.retriever import RESPOSTA_SEM_EVIDENCIA, Retriever
from api.llm.vectorstore import construir_indice
from api.services.horario_marcado_service import HorarioMarcadoService
from api.services.prestador_service import PrestadorService
from api.settings import settings

# Marcador usado para devolver o resultado de uma ferramenta ao modelo.
# É removido da entrada do usuário para que ninguém consiga forjar um resultado.
MARCADOR_FERRAMENTA = "[RESULTADO_FERRAMENTA]"

_BLOCO_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_SOLTO = re.compile(r'\{\s*"action"\s*:.*?\}', re.DOTALL)

_PALAVRAS_AGENDAMENTO = (
    "agendar", "agendamento", "marcar", "remarcar", "desmarcar", "cancelar",
    "consulta", "horario", "horário", "disponibilidade", "vaga",
)
_INTERROGATIVAS = (
    "qual", "quais", "quanto", "quando", "onde", "como", "porque", "por que",
    "quem", "posso", "pode", "tem", "vocês", "voces", "existe", "precisa",
    "aceita", "atende", "funciona", "o que",
)

# Serviços mudam pouco; evita uma consulta ao banco a cada chamada da LLM.
_TTL_SERVICOS = 300


class ChatService:
    def __init__(
        self,
        prestador_service: PrestadorService,
        horario_marcado_service: HorarioMarcadoService,
        docs_folder: str | None = None,
    ):
        self.client = Groq(api_key=settings.llm_api_key)
        self.prestador_service = prestador_service
        self.horario_marcado_service = horario_marcado_service
        self.docs_folder = docs_folder or settings.rag_docs_folder

        # sessoes[session_id] = {"historico": [...], "em_agendamento": bool}
        self.sessoes: dict[str, dict] = {}

        self._retriever: Retriever | None = None
        self._servicos_cache: tuple[float, str] | None = None

    # ------------------------------------------------------------------
    # Índice vetorial (etapas 4 e 5)
    # ------------------------------------------------------------------
    @property
    def retriever(self) -> Retriever:
        """Índice carregado na primeira utilização, não no import do módulo."""
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

    def preparar_indice(self) -> None:
        """Força a construção do índice (usado no startup da API)."""
        _ = self.retriever

    # ------------------------------------------------------------------
    # Sessão e histórico
    # ------------------------------------------------------------------
    def _sessao(self, session_id: str) -> dict:
        if session_id not in self.sessoes:
            self.sessoes[session_id] = {"historico": [], "em_agendamento": False}
        return self.sessoes[session_id]

    def _janela(self, historico: list[dict]) -> list[dict]:
        limite = settings.historico_max_mensagens
        return historico[-limite:] if len(historico) > limite else historico

    def _perguntas_anteriores(self, historico: list[dict]) -> list[str]:
        return [
            m["content"]
            for m in historico
            if m["role"] == "user" and not m["content"].startswith(MARCADOR_FERRAMENTA)
        ]

    def _servicos(self) -> str:
        agora = time.time()
        if self._servicos_cache and agora - self._servicos_cache[0] < _TTL_SERVICOS:
            return self._servicos_cache[1]
        servicos = carregar_servicos()
        self._servicos_cache = (agora, servicos)
        return servicos

    # ------------------------------------------------------------------
    # Classificação do turno
    # ------------------------------------------------------------------
    @staticmethod
    def _sanitizar(mensagem: str) -> str:
        """Impede que o usuário finja ser um resultado de ferramenta."""
        return mensagem.replace(MARCADOR_FERRAMENTA, "[marcador removido]").strip()

    @staticmethod
    def _parece_agendamento(mensagem: str) -> bool:
        texto = mensagem.lower()
        return any(palavra in texto for palavra in _PALAVRAS_AGENDAMENTO)

    @staticmethod
    def _parece_pergunta(mensagem: str) -> bool:
        texto = mensagem.lower().strip()
        if "?" in texto:
            return True
        return any(texto.startswith(p) for p in _INTERROGATIVAS)

    # ------------------------------------------------------------------
    # Ferramentas (tool calling manual por JSON)
    # ------------------------------------------------------------------
    def _extrair_acao(self, resposta: str) -> tuple[dict | None, str]:
        """Devolve (ação, texto sem o bloco JSON).

        Só a primeira ação é considerada — o prompt pede um comando por resposta.
        O texto limpo é o que vai para a tela caso a ação não possa ser executada,
        para que o JSON cru nunca apareça para o cliente.
        """
        encontrado = _BLOCO_JSON.search(resposta)
        bruto = encontrado.group(1) if encontrado else None

        if not encontrado:
            encontrado = _JSON_SOLTO.search(resposta)
            bruto = encontrado.group(0) if encontrado else None

        if not encontrado:
            return None, resposta

        texto_limpo = resposta.replace(encontrado.group(0), "").strip()

        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as erro:
            print(f"[CHAT] JSON inválido emitido pelo modelo: {erro}")
            return None, texto_limpo or resposta

        if not isinstance(dados, dict) or "action" not in dados:
            return None, texto_limpo or resposta
        return dados, texto_limpo

    def _executar_tool(self, acao: dict) -> str:
        nome = acao.get("action")

        if nome == "get_prestadores_servico":
            prestadores = self.prestador_service.get_by_servico(acao["servico"])
            return json.dumps(
                [
                    {"id": p.id, "nome": p.nome, "servico": p.servico}
                    for p in prestadores
                ],
                ensure_ascii=False,
            )

        if nome == "get_horarios_ocupados":
            horarios = self.horario_marcado_service.get_by_prestador_e_data(
                acao["prestador_id"], acao["data"]
            )
            # data_hora chega como "YYYY-MM-DD HH:MM"; o modelo só precisa da hora.
            return json.dumps(
                [str(h.data_hora).split(" ")[-1][:5] for h in horarios],
                ensure_ascii=False,
            )

        if nome == "agendar":
            return self._agendar(acao)

        return json.dumps({"erro": "Ferramenta não encontrada"}, ensure_ascii=False)

    def _agendar(self, acao: dict) -> str:
        from api.schemas.horario_marcado_schema import HorarioMarcadoCreate

        self.horario_marcado_service.create(
            HorarioMarcadoCreate(
                prestador_id=acao["prestador_id"],
                cliente_nome=acao["nome"],
                cliente_email=acao["email"],
                cliente_telefone=acao["telefone"],
                data_hora=f"{acao['data']} {acao['hora']}",
            )
        )
        return json.dumps({"sucesso": True}, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Geração (etapa 9)
    # ------------------------------------------------------------------
    def _chamar_llm(self, system_prompt: str, historico: list[dict]) -> str:
        resposta = self.client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": system_prompt}]
            + self._janela(historico),
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        return resposta.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Entrada principal (etapas 6 a 10)
    # ------------------------------------------------------------------
    def send_message(self, message: str, session_id: str = "default") -> str:
        sessao = self._sessao(session_id)
        historico = sessao["historico"]

        mensagem = self._sanitizar(message)

        # --- Etapa 6.5: reformulação da pergunta com o histórico ---
        query = self.retriever.montar_query(
            mensagem, self._perguntas_anteriores(historico)
        )

        # --- Etapa 7: recuperação ---
        recuperados = self.retriever.recuperar(query)
        com_evidencia = self.retriever.decidir_evidencia(recuperados)
        score = self.retriever.score_maximo(recuperados)

        turno_agendamento = sessao["em_agendamento"] or self._parece_agendamento(mensagem)
        if turno_agendamento:
            sessao["em_agendamento"] = True

        if settings.debug:
            print(
                f"[RAG] sessao={session_id} score_max={score:.4f} "
                f"limiar={settings.rag_limiar_evidencia} evidencia={com_evidencia} "
                f"agendamento={turno_agendamento} query={query!r}"
            )

        historico.append({"role": "user", "content": mensagem})

        # --- Nó de abstenção: pergunta sem evidência não chega a chamar a LLM ---
        if not com_evidencia and not turno_agendamento and self._parece_pergunta(mensagem):
            historico.append({"role": "assistant", "content": RESPOSTA_SEM_EVIDENCIA})
            return RESPOSTA_SEM_EVIDENCIA

        # --- Etapa 8: montagem do contexto ---
        relevantes = self.retriever.filtrar_relevantes(recuperados) if com_evidencia else []
        contexto = self.retriever.montar_contexto(relevantes)
        system_prompt = build_system_prompt(contexto, self._servicos())

        # --- Etapas 9 e 10: geração, com rodadas de ferramenta quando necessário ---
        for passo in range(settings.max_passos_ferramenta + 1):
            try:
                resposta = self._chamar_llm(system_prompt, historico)
            except Exception as erro:
                print(f"[CHAT] Falha na chamada da LLM: {erro}")
                return (
                    "Tive um problema para processar sua mensagem agora. "
                    "Pode tentar novamente em instantes?"
                )

            historico.append({"role": "assistant", "content": resposta})
            acao, texto_limpo = self._extrair_acao(resposta)

            if acao is None:
                return texto_limpo or resposta

            if passo == settings.max_passos_ferramenta:
                print("[CHAT] Limite de passos de ferramenta atingido.")
                return (
                    "Não consegui concluir essa operação agora. "
                    "Pode repetir o que você precisa?"
                )

            try:
                resultado = self._executar_tool(acao)
            except Exception as erro:
                print(f"[CHAT] Erro ao executar {acao.get('action')}: {erro}")
                resultado = json.dumps(
                    {"erro": "não foi possível executar a operação"}, ensure_ascii=False
                )

            if acao.get("action") == "agendar" and '"sucesso": true' in resultado.lower():
                sessao["em_agendamento"] = False
                sucesso = "Agendamento realizado com sucesso! ✅"
                historico.append({"role": "assistant", "content": sucesso})
                return sucesso

            historico.append({
                "role": "user",
                "content": f"{MARCADOR_FERRAMENTA} {acao['action']}: {resultado}",
            })

        return "Não consegui concluir essa operação agora."
