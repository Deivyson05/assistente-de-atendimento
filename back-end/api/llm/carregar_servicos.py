"""Lista de serviços ofertados, lida do banco (tabela prestador)."""

FALLBACK = "- Consulte os serviços disponíveis com a recepção"


def carregar_servicos() -> str:
    try:
        from api.database import SessionLocal
        from api.models.prestador import Prestador

        db = SessionLocal()
        try:
            servicos = db.query(Prestador.servico).distinct().all()
        finally:
            db.close()

        if not servicos:
            return FALLBACK
        return "\n".join(f"- {servico}" for (servico,) in servicos)
    except Exception as erro:
        print(f"[RAG] Erro ao carregar serviços: {erro}")
        return FALLBACK
