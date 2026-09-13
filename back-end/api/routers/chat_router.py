from fastapi import APIRouter

from api.controllers.chat_controller import ChatController
from api.database import SessionLocal
from api.repository.horario_marcado_repository import HorarioMarcadoRepository
from api.repository.prestador_repository import PrestadorRepository
from api.schemas.chat_schema import ChatRequest
from api.services.chat_service import ChatService
from api.services.horario_marcado_service import HorarioMarcadoService
from api.services.prestador_service import PrestadorService

router = APIRouter(prefix="/chat", tags=["chat"])

# sessão dedicada do chat: o histórico e o índice vivem no processo, então o
# serviço precisa ser um singleton entre requisições
_db = SessionLocal()
_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """Criado na primeira utilização.

    Antes, o serviço era instanciado no import do módulo, o que fazia o servidor
    só subir depois de baixar o modelo de embedding e indexar todos os PDFs.
    """
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(
            prestador_service=PrestadorService(PrestadorRepository(_db)),
            horario_marcado_service=HorarioMarcadoService(
                HorarioMarcadoRepository(_db)
            ),
        )
    return _chat_service


@router.post("/")
def chat(req: ChatRequest):
    ctrl = ChatController(get_chat_service())
    # garante que os dados lidos do banco estejam atualizados a cada request
    _db.expire_all()
    return {"message": ctrl.chat(req.message, req.session_id)}


@router.get("/status")
def status():
    """Diagnóstico do índice vetorial — útil para conferir se o RAG subiu."""
    servico = get_chat_service()
    retriever = servico.retriever
    return {
        "chunks_indexados": retriever.colecao.count(),
        "modelo_embedding": retriever.colecao.metadata.get("modelo_embedding"),
        "top_k": retriever.top_k,
        "limiar_evidencia": retriever.limiar,
        "sessoes_ativas": len(servico.sessoes),
    }
