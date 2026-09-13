from pathlib import Path

from pydantic_settings import BaseSettings

# Caminhos resolvidos a partir do arquivo, e nao do diretorio de execucao:
# antes, rodar o servidor de outra pasta fazia o RAG nao achar os PDFs.
API_DIR = Path(__file__).resolve().parent
BACKEND_DIR = API_DIR.parent


class Settings(BaseSettings):
    llm_api_key: str
    database_url: str
    debug: bool = False  # valor padrão

    # --- Modelo de geração (Groq) ---
    llm_model: str = "llama-3.3-70b-versatile"
    # Temperatura baixa: em RAG a resposta deve seguir o contexto, não ser criativa.
    llm_temperature: float = 0.1
    llm_max_tokens: int = 800

    # --- RAG ---
    rag_docs_folder: str = str(API_DIR / "docs")
    rag_index_path: str = str(API_DIR / "vectorstore")
    # Modelo multilíngue: os documentos da clínica estão em português.
    rag_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rag_top_k: int = 5
    # Limiar de evidência. Abaixo dele o assistente se abstém em vez de inventar.
    # Valor didático — deve ser calibrado com um conjunto de perguntas de teste.
    rag_limiar_evidencia: float = 0.35
    rag_chunk_tamanho: int = 70
    rag_chunk_overlap: int = 15

    # --- Conversa ---
    # Janela do histórico enviada ao modelo (evita crescer sem limite).
    historico_max_mensagens: int = 20
    # Quantas rodadas de comando JSON são permitidas por mensagem do usuário.
    max_passos_ferramenta: int = 4

    class Config:
        env_file = str(BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
