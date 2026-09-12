def _carregar_servicos() -> str:
    try:
        from api.database import SessionLocal
        from api.models.prestador import Prestador
        db = SessionLocal()
        try:
            servicos = db.query(Prestador.servico).distinct().all()
            return "\n".join([f"- {s[0]}" for s in servicos])
        finally:
            db.close()
    except Exception as e:
        print(f"Erro ao carregar serviços: {e}")
        return "- Consulte os serviços disponíveis"