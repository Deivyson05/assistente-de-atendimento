from fastapi import FastAPI
from api.chat import router as chat_router
from api.routers import prestador_router, horario_marcado_router
from api.database import engine, Base
from api.models import prestador, horario_marcado
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

app.include_router(chat_router.router)
app.include_router(prestador_router.router)
app.include_router(horario_marcado_router.router)

def handler(request, context):
    return app
#uvicorn main:app --reload