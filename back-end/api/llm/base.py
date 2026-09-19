"""Contrato comum a qualquer provedor de LLM usado pelo assistente.

Hoje só existe o Groq (groq_provider.py). Este protocolo existe para que
trocar de provedor — ou adicionar um segundo, como o projeto de referência
faz com Groq e Gemma3 lado a lado — não exija tocar em api/chat/, que so
conhece o metodo generate().
"""

from typing import Protocol


class LLMProvider(Protocol):
    def generate(self, system_prompt: str, messages: list[dict]) -> str:
        """Gera a resposta do assistente a partir do prompt de sistema e do
        historico de mensagens (etapa 9 do pipeline de RAG)."""
        ...
