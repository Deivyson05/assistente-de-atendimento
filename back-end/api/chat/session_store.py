"""Estado de conversa por sessão: histórico, janela e status de agendamento.

Guardado em memória do processo — cada sessão vive enquanto o servidor não é
reiniciado. Ver DOCS.md, seção Limitações, sobre a implicação disso.
"""

from api.chat.tools import MARCADOR_FERRAMENTA


class SessionStore:
    def __init__(self, historico_max_mensagens: int):
        self._historico_max_mensagens = historico_max_mensagens
        # sessoes[session_id] = {"historico": [...], "em_agendamento": bool}
        self.sessoes: dict[str, dict] = {}

    def obter(self, session_id: str) -> dict:
        if session_id not in self.sessoes:
            self.sessoes[session_id] = {"historico": [], "em_agendamento": False}
        return self.sessoes[session_id]

    def janela(self, historico: list[dict]) -> list[dict]:
        """Últimas N mensagens enviadas à LLM, para o histórico não crescer sem limite."""
        limite = self._historico_max_mensagens
        return historico[-limite:] if len(historico) > limite else historico

    def perguntas_anteriores(self, historico: list[dict]) -> list[str]:
        return [
            m["content"]
            for m in historico
            if m["role"] == "user" and not m["content"].startswith(MARCADOR_FERRAMENTA)
        ]
