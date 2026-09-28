"""Estado de conversa por sessão: histórico e janela enviada à LLM.

Guardado em memória do processo — cada sessão vive enquanto o servidor não é
reiniciado. Ver DOCS.md, seção Limitações, sobre a implicação disso.
"""


class SessionStore:
    def __init__(self, historico_max_mensagens: int):
        self._historico_max_mensagens = historico_max_mensagens
        self.sessoes: dict[str, dict] = {}

    def obter(self, session_id: str) -> dict:
        if session_id not in self.sessoes:
            self.sessoes[session_id] = {"historico": []}
        return self.sessoes[session_id]

    def janela(self, historico: list[dict]) -> list[dict]:
        """Últimas N mensagens enviadas à LLM, para o histórico não crescer sem limite."""
        limite = self._historico_max_mensagens
        return historico[-limite:] if len(historico) > limite else historico
