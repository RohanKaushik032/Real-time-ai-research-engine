# =========================================
# 🧠 HYBRID MEMORY SYSTEM (FIXED + BALANCED)
# =========================================

from app.session_memory import get_session_context
from app.reasoning_memory import get_relevant_memory as get_reasoning_memory
from app.vector_store import get_relevant_memory as get_vector_memory
from app.vector_store import embed

import asyncio


# =========================================
# CONFIG
# =========================================
SESSION_WEIGHT = 0.5
VECTOR_WEIGHT = 0.3
REASONING_WEIGHT = 0.2

MAX_CONTEXT_ITEMS = 8
MAX_PER_SOURCE = 4   # prevent domination


# =========================================
# TEXT OVERLAP SCORE
# =========================================
def score_text_overlap(query, text):
    query_words = set(query.lower().split())
    text_words = set(text.lower().split())

    if not query_words:
        return 0

    return len(query_words & text_words) / len(query_words)


# =========================================
# PROCESS SESSION MEMORY (RECENCY BOOST)
# =========================================
def process_session_memory(session_data):

    formatted = []

    # prioritize recent messages
    session_data = session_data[-6:]

    for i, m in enumerate(session_data):
        recency_boost = 1 - (len(session_data) - i) * 0.1

        formatted.append({
            "text": m["content"],
            "source": "session",
            "score": 0.5 + recency_boost
        })

    return formatted


# =========================================
# MERGE + RANK
# =========================================
def merge_and_rank(query, session_mem, vector_mem, reasoning_mem):

    all_items = []

    # -------- SESSION --------
    for item in session_mem:
        score = score_text_overlap(query, item["text"]) * SESSION_WEIGHT
        item["score"] = score + item.get("score", 0)
        all_items.append(item)

    # -------- VECTOR --------
    for text in vector_mem[:MAX_PER_SOURCE]:
        score = score_text_overlap(query, text) * VECTOR_WEIGHT
        all_items.append({
            "text": text,
            "source": "vector",
            "score": score
        })

    # -------- REASONING --------
    for text in reasoning_mem[:MAX_PER_SOURCE]:
        score = score_text_overlap(query, text) * REASONING_WEIGHT
        all_items.append({
            "text": text,
            "source": "reasoning",
            "score": score
        })

    # -------- SORT --------
    all_items.sort(key=lambda x: x["score"], reverse=True)

    # -------- DEDUP (SMARTER) --------
    seen = set()
    unique = []

    for item in all_items:
        key = item["text"][:100]  # partial match dedup

        if key not in seen:
            unique.append(item)
            seen.add(key)

    return unique[:MAX_CONTEXT_ITEMS]


# =========================================
# MAIN HYBRID RETRIEVAL
# =========================================
async def get_hybrid_context(user_id, session_id, query):

    try:
        query_embedding = await embed(query)
    except:
        query_embedding = None

    # -------- FETCH MEMORY --------
    session_mem = get_session_context(user_id, session_id)

    reasoning_mem = []
    vector_mem = []

    try:
        if query_embedding:
            reasoning_mem = get_reasoning_memory(user_id, query_embedding, session_id)
            vector_mem = get_vector_memory(user_id, query_embedding, session_id)
    except:
        pass

    # -------- PROCESS --------
    session_mem = process_session_memory(session_mem)

    ranked = merge_and_rank(query, session_mem, vector_mem, reasoning_mem)

    return ranked


# =========================================
# FORMAT FOR PROMPT
# =========================================
def format_context_for_prompt(memory_items):

    if not memory_items:
        return ""

    lines = []

    for i, item in enumerate(memory_items):
        lines.append(f"[{i+1}] ({item['source']}) {item['text']}")

    return "\n".join(lines)