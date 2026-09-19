"""Etapa 2 do pipeline de RAG: limpeza e organizacao dos textos.

O texto extraido de um PDF vem com ruido de diagramacao: cabecalho e rodape
repetidos em toda pagina, numero de pagina, quebra de linha no meio da frase e
palavra hifenizada no fim da linha. Esse ruido entra no embedding e piora a
recuperacao, entao ele e removido antes do chunking.

Cuidado importante: a remocao so atua na BORDA da pagina (primeiras e ultimas
linhas). Uma versao que procurava linhas repetidas na pagina inteira apagava
conteudo real - palavras curtas como "a", "de", "para" e numeros soltos (numero
de rua, CEP) se repetem entre paginas e eram confundidos com rodape.
"""

import re
import unicodedata

# Quantas linhas do topo e do rodape sao candidatas a cabecalho/rodape.
_LINHAS_BORDA = 3

# Uma linha de borda e considerada cabecalho/rodape quando se repete em pelo
# menos essa fracao das paginas do documento.
_FRACAO_REPETICAO = 0.6

# Tamanho minimo e maximo de uma linha para poder ser tratada como rodape.
# Curta demais costuma ser palavra solta do texto; longa demais e conteudo.
_MIN_RODAPE = 3
_MAX_RODAPE = 120

_ESPACO_NAO_SEPARAVEL = chr(0x00A0)
_ASPAS_SIMPLES = (chr(0x2018), chr(0x2019))
_ASPAS_DUPLAS = (chr(0x201C), chr(0x201D))

# Linhas que sao apenas numero de pagina, "Pagina 3", "3 de 12" e variacoes.
# Aplicado somente na borda da pagina, nunca no meio do texto. O limite de 4
# digitos evita que um CEP ("01234-567") seja confundido com numero de pagina.
_PADRAO_NUMERO_PAGINA = re.compile(
    r"^(?:pag\.? ?|p[aá]gina ?)?\d{1,4}(?: ?(?:/|-|de) ?\d{1,4})?$",
    re.IGNORECASE,
)


def _normalizar_unicode(texto: str) -> str:
    # NFKC junta acentos combinantes e converte ligaduras/aspas tipograficas
    # para formas canonicas, evitando que duas grafias do mesmo termo gerem
    # vetores diferentes.
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.replace(_ESPACO_NAO_SEPARAVEL, " ")
    for aspa in _ASPAS_SIMPLES:
        texto = texto.replace(aspa, "'")
    for aspa in _ASPAS_DUPLAS:
        texto = texto.replace(aspa, '"')
    return texto


def _linhas_uteis(pagina: str) -> list[str]:
    return [linha.strip() for linha in pagina.splitlines() if linha.strip()]


def _indices_de_borda(quantidade: int) -> set[int]:
    if quantidade <= 2 * _LINHAS_BORDA:
        return set(range(quantidade))
    return set(range(_LINHAS_BORDA)) | set(
        range(quantidade - _LINHAS_BORDA, quantidade)
    )


def _remover_bordas_repetidas(paginas_de_linhas: list[list[str]]) -> list[list[str]]:
    """Remove cabecalho/rodape, detectados por repeticao NA BORDA das paginas."""
    if len(paginas_de_linhas) < 3:
        return paginas_de_linhas

    ocorrencias: dict[str, int] = {}
    for linhas in paginas_de_linhas:
        vistas_nesta_pagina = set()
        for indice in _indices_de_borda(len(linhas)):
            linha = linhas[indice]
            if linha and linha not in vistas_nesta_pagina:
                vistas_nesta_pagina.add(linha)
                ocorrencias[linha] = ocorrencias.get(linha, 0) + 1

    minimo = max(2, int(len(paginas_de_linhas) * _FRACAO_REPETICAO))
    repetidas = {
        linha
        for linha, quantidade in ocorrencias.items()
        if quantidade >= minimo and _MIN_RODAPE <= len(linha) <= _MAX_RODAPE
    }

    limpas = []
    for linhas in paginas_de_linhas:
        borda = _indices_de_borda(len(linhas))
        limpas.append([
            linha
            for indice, linha in enumerate(linhas)
            if not (
                indice in borda
                and (linha in repetidas or _PADRAO_NUMERO_PAGINA.match(linha))
            )
        ])
    return limpas


def _juntar_hifenizacao(texto: str) -> str:
    # "odonto-" no fim de uma linha e "logia" na seguinte viram "odontologia"
    return re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", texto)


def _juntar_linhas_do_paragrafo(texto: str) -> str:
    """Quebra simples vira espaco; quebra dupla continua separando paragrafos."""
    paragrafos = re.split(r"\n{2,}", texto)
    unidos = [re.sub(r"[ \t]*\n[ \t]*", " ", p).strip() for p in paragrafos]
    return "\n\n".join(p for p in unidos if p)


def _normalizar_espacos(texto: str) -> str:
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"[ \t]+([,.;:!?])", r"\1", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def limpar_paginas(paginas: list[str]) -> str:
    """Recebe o texto pagina a pagina e devolve um texto unico ja limpo."""
    paginas_de_linhas = [_linhas_uteis(_normalizar_unicode(p)) for p in paginas]
    paginas_de_linhas = _remover_bordas_repetidas(paginas_de_linhas)

    texto = "\n\n".join(
        "\n".join(linhas) for linhas in paginas_de_linhas if linhas
    )
    texto = _juntar_hifenizacao(texto)
    texto = _juntar_linhas_do_paragrafo(texto)
    return _normalizar_espacos(texto)


def limpar_texto(texto: str) -> str:
    """Versao para arquivos .txt/.md, que nao tem paginacao."""
    return limpar_paginas([texto])
