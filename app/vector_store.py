# =========================================
# 🔹 VECTOR STORE (IMPROVED + INTELLIGENT)
# =========================================

import chromadb
from chromadb.config import Settings
import time
import uuid
import asyncio
import os
import logging
from openai import OpenAI

logger = logging.getLogger("vector_store")

# =========================================
# INIT CHROMA
# =========================================
client = chromadb.Client(
    Settings(persist_directory="./vector_db")
)

collection = client.get_or_create_collection(name="user_memory")


# =========================================
# OPENAI CLIENT
# =========================================
_openai_client = None

def get_openai_client():
    global _openai_client

    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        _openai_client = OpenAI(api_key=api_key)

    return _openai_client


# =========================================
# FILTER LOW VALUE TEXT
# =========================================
def _is_valid_text(text: str):
    if not text or len(text) < 20:
        return False

    noise = ["ok", "thanks", "yes", "no"]
    if text.lower().strip() in noise:
        return False

    return True


# =========================================
# EMBEDDING
# =========================================
async def embed(text: str):
    try:
        client = get_openai_client()

        res = await asyncio.to_thread(
            client.embeddings.create,
            model="text-embedding-3-small",
            input=text[:2000]
        )

        return res.data[0].embedding

    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None


# =========================================
# STORE MEMORY
# =========================================
def store_memory(user_id, text, embedding, session_id):

    if not embedding or not _is_valid_text(text):
        return

    try:
        collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[{
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": time.time()
            }],
            ids=[str(uuid.uuid4())]
        )

    except Exception as e:
        logger.error(f"Store memory error: {e}")


# =========================================
# RETRIEVE MEMORY (SMART)
# =========================================
def get_relevant_memory(user_id, embedding, session_id, top_k=5):

    if not embedding:
        return []

    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k * 2,  # fetch more → filter later
            where={
                "$and": [
                    {"user_id": user_id},
                    {"session_id": session_id}
                ]
            }
        )

        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        scored = []

        now = time.time()

        for doc, dist, meta in zip(docs, distances, metadatas):

            similarity = 1 - dist
            age = now - meta.get("timestamp", now)

            # 🔥 recency boost
            recency_score = max(0, 1 - (age / 3600))  # 1-hour decay

            final_score = (0.7 * similarity) + (0.3 * recency_score)

            scored.append((final_score, doc))

        # sort by final score
        scored.sort(reverse=True, key=lambda x: x[0])

        # 🔥 dedup (simple)
        seen = set()
        result = []

        for score, doc in scored:
            key = doc[:100]

            if key not in seen:
                seen.add(key)
                result.append(doc)

            if len(result) >= top_k:
                break

        return result

    except Exception as e:
        logger.error(f"Memory retrieval error: {e}")
        return []


# =========================================
# CLEANUP
# =========================================
def cleanup_old(user_id, session_id, limit=100):

    try:
        results = collection.get(
            where={
                "$and": [
                    {"user_id": user_id},
                    {"session_id": session_id}
                ]
            }
        )

        ids = results.get("ids", [])
        metadatas = results.get("metadatas", [])

        if len(ids) <= limit:
            return

        sorted_items = sorted(
            zip(ids, metadatas),
            key=lambda x: x[1].get("timestamp", 0)
        )

        to_delete = [item[0] for item in sorted_items[:-limit]]

        collection.delete(ids=to_delete)

    except Exception as e:
        logger.error(f"Cleanup error: {e}")