def _load_documents(folder: str) -> list[dict]:
    
    docs = []
    for path in Path(folder).rglob("*"):
        if path.suffix == ".pdf":
            reader = PdfReader(path)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
            print(f"=== {path.name} ===")
            print(text)  # ← vê o que está extraindo
            print("==================")
        elif path.suffix in (".txt", ".md"):
            text = path.read_text(encoding="utf-8")
        else:
            continue
        docs.append({"source": str(path), "text": text})
        print(f"Documentos carregados: {len(docs)}")
        for d in docs:
            print(f" - {d['source']} ({len(d['text'])} chars)")
    return docs