"""Etapa 1 do pipeline de RAG: coleta do conteudo do dominio.

Le os PDFs (e .txt/.md) da pasta de documentos, aplica a limpeza da etapa 2 e
devolve cada documento com identidade propria (id, titulo, fonte). Esses
metadados sao propagados ate a resposta final, permitindo citar "[Fonte X]".
"""

import hashlib
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from api.llm.limpeza import limpar_paginas, limpar_texto

EXTENSOES_SUPORTADAS = {".pdf", ".txt", ".md"}

# Prefixo institucional presente no nome dos arquivos; removido do titulo para
# que "Mika Odonto - Horarios e Agendamento" vire apenas "Horarios e Agendamento".
_PREFIXO_TITULO = "mika odonto"


def _slug(texto: str) -> str:
    ascii_texto = (
        unicodedata.normalize("NFKD", texto)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = "".join(c if c.isalnum() else "_" for c in ascii_texto)
    return "_".join(parte for parte in slug.split("_") if parte)


def _titulo_do_arquivo(caminho: Path) -> str:
    titulo = caminho.stem.replace("_", " ").strip()
    sem_prefixo = titulo.lower()
    if sem_prefixo.startswith(_PREFIXO_TITULO):
        titulo = titulo[len(_PREFIXO_TITULO):].lstrip(" -\u2013\u2014")
    return titulo.strip() or caminho.stem


def _ler_pdf(caminho: Path) -> str:
    reader = PdfReader(caminho)
    paginas = [pagina.extract_text() or "" for pagina in reader.pages]
    return limpar_paginas(paginas)


def carregar_documentos(pasta: str | Path) -> list[dict]:
    """Devolve [{id, titulo, fonte, texto}] com o texto ja limpo."""
    pasta = Path(pasta)
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta de documentos nao encontrada: {pasta}")

    documentos: list[dict] = []
    for caminho in sorted(pasta.rglob("*")):
        if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
            continue

        if caminho.suffix.lower() == ".pdf":
            texto = _ler_pdf(caminho)
        else:
            texto = limpar_texto(caminho.read_text(encoding="utf-8"))

        if not texto.strip():
            # PDF only-image nao produz texto extraivel; ignorar e avisar e
            # melhor do que indexar um documento vazio.
            print(f"[RAG] Aviso: nenhum texto extraido de {caminho.name}")
            continue

        documentos.append({
            "id": _slug(caminho.stem),
            "titulo": _titulo_do_arquivo(caminho),
            "fonte": caminho.name,
            "texto": texto,
        })

    return documentos


def impressao_digital(pasta: str | Path) -> str:
    """Hash do conteudo da pasta, usado para saber se o indice esta desatualizado.

    Considera nome, tamanho e data de modificacao de cada arquivo suportado.
    """
    pasta = Path(pasta)
    if not pasta.exists():
        return "vazio"

    partes = []
    for caminho in sorted(pasta.rglob("*")):
        if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
            continue
        stat = caminho.stat()
        partes.append(f"{caminho.name}:{stat.st_size}:{int(stat.st_mtime)}")

    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:16]
