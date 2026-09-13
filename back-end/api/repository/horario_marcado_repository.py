from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from api.models.horario_marcado import HorarioMarcado
from api.schemas.horario_marcado_schema import HorarioMarcadoCreate


class HorarioMarcadoRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: HorarioMarcadoCreate) -> HorarioMarcado:
        horario_marcado = HorarioMarcado(**data.model_dump())
        self.db.add(horario_marcado)
        self.db.commit()
        self.db.refresh(horario_marcado)
        return horario_marcado

    def get_all(self) -> list[HorarioMarcado]:
        return self.db.query(HorarioMarcado).all()

    def update(self, horario_marcado: HorarioMarcado) -> HorarioMarcado:
        self.db.add(horario_marcado)
        self.db.commit()
        self.db.refresh(horario_marcado)
        return horario_marcado

    def delete(self, horario_marcado: HorarioMarcado) -> None:
        self.db.delete(horario_marcado)
        self.db.commit()

    def get_horarios_ocupados_by_prestador_e_data(
        self, prestador_id: int, data: str
    ) -> list[HorarioMarcado]:
        """Agendamentos de um prestador em um dia.

        data_hora é uma coluna DateTime; comparar com a string "YYYY-MM-DD"
        (como era feito antes) só casaria com meia-noite exata, então a consulta
        devolvia sempre lista vazia e o assistente considerava o dia todo livre.
        A comparação correta é por intervalo do dia.
        """
        try:
            inicio = datetime.strptime(str(data)[:10], "%Y-%m-%d")
        except ValueError:
            print(f"[AGENDA] Data inválida recebida: {data!r}")
            return []

        fim = inicio + timedelta(days=1)

        return (
            self.db.query(HorarioMarcado)
            .filter(
                HorarioMarcado.prestador_id == prestador_id,
                HorarioMarcado.data_hora >= inicio,
                HorarioMarcado.data_hora < fim,
            )
            .order_by(HorarioMarcado.data_hora)
            .all()
        )
