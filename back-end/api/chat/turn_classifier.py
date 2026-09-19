"""Heurísticas para classificar a intenção do turno atual da conversa.

São palpites baratos por palavra-chave, não um classificador de NLP: servem
só para decidir se a mensagem pertence a um fluxo de agendamento (onde a
abstenção por falta de evidência deve ser suprimida) e se ela é uma pergunta
(onde a abstenção faz sentido).
"""

_PALAVRAS_AGENDAMENTO = (
    "agendar", "agendamento", "marcar", "remarcar", "desmarcar", "cancelar",
    "consulta", "horario", "horário", "disponibilidade", "vaga",
)
_INTERROGATIVAS = (
    "qual", "quais", "quanto", "quando", "onde", "como", "porque", "por que",
    "quem", "posso", "pode", "tem", "vocês", "voces", "existe", "precisa",
    "aceita", "atende", "funciona", "o que",
)


def parece_agendamento(mensagem: str) -> bool:
    texto = mensagem.lower()
    return any(palavra in texto for palavra in _PALAVRAS_AGENDAMENTO)


def parece_pergunta(mensagem: str) -> bool:
    texto = mensagem.lower().strip()
    if "?" in texto:
        return True
    return any(texto.startswith(p) for p in _INTERROGATIVAS)
