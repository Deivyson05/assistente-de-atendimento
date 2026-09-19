"""Configuração e chamada do provedor de IA atualmente em uso: Groq.

Este módulo é intencionalmente pequeno: só sabe instanciar o cliente e chamar
o endpoint de chat completions. Não sabe nada sobre RAG, sessão de conversa ou
tool calling — isso é responsabilidade de api/rag/ e api/chat/.
"""

from groq import Groq

from api.settings import settings


class GroqProvider:
    """Implementa LLMProvider (api/llm/base.py) usando a API da Groq."""

    def __init__(self):
        self.client = Groq(api_key=settings.llm_api_key)

    def generate(self, system_prompt: str, messages: list[dict]) -> str:
        resposta = self.client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        return resposta.choices[0].message.content or ""
