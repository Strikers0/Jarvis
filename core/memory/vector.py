from __future__ import annotations

from typing import Any, Optional


class VectorMemoryManager:
    def __init__(self, collection_name: str = "jarvis_memory", persist_dir: str = "vector_memory"):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None
        self._encoder = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            self._client = None

    def _get_encoder(self):
        if self._encoder is not None:
            return self._encoder
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            try:
                from chromadb.utils import embedding_functions
                self._encoder = embedding_functions.DefaultEmbeddingFunction()
            except ImportError:
                self._encoder = None
        return self._encoder

    @property
    def available(self) -> bool:
        return self._client is not None and self._get_encoder() is not None

    def add_memory(
        self,
        text: str,
        metadata: Optional[dict] = None,
        memory_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self.available:
            return None
        import uuid
        mid = memory_id or str(uuid.uuid4())
        encoder = self._get_encoder()
        embedding = encoder.encode([text])[0].tolist()
        self._collection.add(
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
            ids=[mid],
        )
        return mid

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.available:
            return []
        encoder = self._get_encoder()
        query_embedding = encoder.encode([query])[0].tolist()
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        items = []
        if results.get("documents") and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                items.append({
                    "text": doc,
                    "metadata": results.get("metadatas", [{}])[0][i] if results.get("metadatas") else {},
                    "distance": results.get("distances", [[0]])[0][i] if results.get("distances") else 0,
                })
        return items

    def delete_memory(self, memory_id: str) -> bool:
        if not self.available:
            return False
        self._collection.delete(ids=[memory_id])
        return True

    def count(self) -> int:
        if not self.available:
            return 0
        return self._collection.count()

    def close(self) -> None:
        self._client = None
        self._collection = None
