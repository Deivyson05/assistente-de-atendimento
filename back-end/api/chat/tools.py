"""Tool calling manual por JSON.

Como o modelo usado (Groq/Llama) não tem suporte nativo a function calling, o
prompt instrui a LLM a emitir um bloco ```json com uma ação; este módulo
extrai esse bloco e executa a ação real (consultar prestadores, consultar
horários, agendar).
"""

import json
import re

# Marcador usado para devolver o resultado de uma ferramenta ao modelo.
# É removido da entrada do usuário para que ninguém consiga forjar um resultado.
MARCADOR_FERRAMENTA = "[RESULTADO_FERRAMENTA]"

_BLOCO_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_SOLTO = re.compile(r'\{\s*"action"\s*:.*?\}', re.DOTALL)


def sanitizar(mensagem: str) -> str:
    """Impede que o usuário finja ser um resultado de ferramenta."""
    return mensagem.replace(MARCADOR_FERRAMENTA, "[marcador removido]").strip()


def extrair_acao(resposta: str) -> tuple[dict | None, str]:
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


class ToolRouter:
    """Executa as ações que a LLM pode emitir, contra os serviços reais."""

    def __init__(self, prestador_service, horario_marcado_service):
        self.prestador_service = prestador_service
        self.horario_marcado_service = horario_marcado_service

    def executar(self, acao: dict) -> str:
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
