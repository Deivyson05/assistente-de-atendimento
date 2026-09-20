FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# torch (dependencia do sentence-transformers) na build CPU-only: a padrao do
# PyPI traz CUDA e passa de 2 GB, sem utilidade aqui, ja que a imagem roda sem GPU.
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Codigo + PDFs da base de conhecimento (api/docs). O .env NAO entra na imagem
# (ver .dockerignore); as variaveis chegam pelo docker-compose.
COPY api ./api

EXPOSE 8000

CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]
