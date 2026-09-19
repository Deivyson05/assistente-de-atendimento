# Mika AI — Chatbot com RAG para a Mika Odonto

Chatbot web que responde dúvidas em linguagem natural com base em uma base de conhecimento documental (RAG) e conduz o fluxo conversacional de agendamento de uma clínica odontológica fictícia — a **Mika Odonto**.

Para a arquitetura completa (pipeline de RAG etapa a etapa, decisões técnicas, limitações e evoluções possíveis), veja **[DOCS.md](DOCS.md)**.

---

## Base de conhecimento

Domínio: **atendimento ao cliente de uma clínica odontológica** (cenário fictício).

Arquivos em [`back-end/api/docs/`](back-end/api/docs/), extraídos de PDF em tempo de indexação:

- Atendimento ao Cliente
- Dúvidas Odontológicas Frequentes
- Horários e Agendamento
- Pagamentos, Orçamentos e Convênios
- Serviços e Procedimentos
- Ambiente e Qualidade
- Documentação institucional

---

## Arquitetura

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js (App Router), React, Tailwind |
| Backend | Python, FastAPI |
| Orquestração do fluxo de RAG | **LangGraph** |
| Geração da resposta (LLM externa) | Groq — `openai/gpt-oss-120b` |
| Embeddings | Sentence Transformers — `paraphrase-multilingual-MiniLM-L12-v2` (local, não usa API externa) |
| Índice vetorial | ChromaDB (persistente) |
| Banco de dados | PostgreSQL (Neon) |

Pipeline de RAG: coleta → limpeza → chunking → embeddings → índice vetorial → recuperação (com limiar de evidência e abstenção) → montagem do contexto (chunks + histórico da conversa) → geração pela LLM → exibição no chat. Essas cinco últimas etapas são orquestradas como um `StateGraph` do LangGraph (`back-end/api/chat/graph.py`). Detalhes de cada etapa e o diagrama do grafo em [DOCS.md](DOCS.md#pipeline-de-rag).

---

## Dependências

- **Backend**: [`back-end/requirements.txt`](back-end/requirements.txt) — FastAPI, SQLAlchemy, Groq, LangGraph, ChromaDB, Sentence Transformers, pypdf.
- **Frontend**: [`front-end/package.json`](front-end/package.json) — Next.js, React, Tailwind, Axios.

---

## Como executar

### Backend

```bash
cd back-end
python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

Crie um arquivo `.env` em `back-end/` com:

```
llm_api_key=
database_url=
debug=True
```

- `llm_api_key`: chave da API da Groq.
- `database_url`: connection string do PostgreSQL.

Construa o índice vetorial (lê os PDFs, gera os embeddings e persiste em `api/vectorstore/`):

```bash
python -m api.rag.cli
```

Suba a API:

```bash
python -m uvicorn api.index:app --reload
```

A API sobe em `http://127.0.0.1:8000`. `GET /chat/status` mostra o diagnóstico do índice (chunks indexados, modelo de embedding, limiar de evidência).

### Frontend

```bash
cd front-end
npm install
npm run dev
```

Crie um arquivo `.env` em `front-end/` com:

```
NEXT_PUBLIC_BACKENDAPI=http://127.0.0.1:8000
```

Abra `http://localhost:3000` — o chat aparece como um botão flutuante ("Assistente Virtual") na página inicial.

---

## Autor

Deivyson Ricardo Silva dos Santos
