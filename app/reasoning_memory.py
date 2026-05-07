# =========================================
# 🧠 REASONING MEMORY (PRODUCTION VERSION)
# =========================================

import time
import math

REASONING_DB = {}
SESSION_DB = {}

# =========================================
# CONFIG
# =========================================
MAX_MEMORY_PER_SESSION = 20
SIMILARITY_THRESHOLD = 0.35
SESSION_TTL_SECONDS = 3600  # 1 hour


# =========================================
# STORE REASONING MEMORY
# =========================================
def store_memory(user_id, text, embedding, session_id):
    if not embedding or not isinstance(embedding, list):
        return

    key = f"{user_id}_{session_id}"

    if key not in REASONING_DB:
        REASONING_DB[key] = []

    REASONING_DB[key].append({
        "text": text,
        "embedding": embedding,
        "time": time.time()
    })

    # 🔥 limit memory size
    REASONING_DB[key] = REASONING_DB[key][-MAX_MEMORY_PER_SESSION:]


# =========================================
# COSINE SIMILARITY (FIXED)
# =========================================
def similarity(a, b):
    try:
        if len(a) != len(b):
            return 0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0

        return dot / (norm_a * norm_b)

    except Exception:
        return 0


# =========================================
# CLEAN OLD MEMORY (TTL)
# =========================================
def _clean_old_memory(key):
    if key not in REASONING_DB:
        return

    now = time.time()

    REASONING_DB[key] = [
        m for m in REASONING_DB[key]
        if now - m["time"] < SESSION_TTL_SECONDS
    ]


# =========================================
# RETRIEVE RELEVANT MEMORY
# =========================================
def get_relevant_memory(user_id, query_embedding, session_id):

    if not query_embedding:
        return []

    key = f"{user_id}_{session_id}"

    if key not in REASONING_DB:
        return []

    # 🔥 clean expired memory
    _clean_old_memory(key)

    memories = REASONING_DB[key]

    scored = []

    for m in memories:
        score = similarity(query_embedding, m["embedding"])

        # 🔥 filter noise
        if score >= SIMILARITY_THRESHOLD:
            scored.append((score, m["text"]))

    # sort by relevance
    scored.sort(reverse=True, key=lambda x: x[0])

    return [text for _, text in scored[:3]]


# =========================================
# SESSION MEMORY (CHAT CONTEXT)
# =========================================
def add_to_session(user_id, session_id, role, content):
    key = f"{user_id}_{session_id}"

    if key not in SESSION_DB:
        SESSION_DB[key] = []

    SESSION_DB[key].append({
        "role": role,
        "content": content,
        "time": time.time()
    })

    # 🔥 remove expired + limit size
    now = time.time()

    SESSION_DB[key] = [
        m for m in SESSION_DB[key]
        if now - m["time"] < SESSION_TTL_SECONDS
    ][-10:]


def get_session_context(user_id, session_id):
    key = f"{user_id}_{session_id}"

    if key not in SESSION_DB:
        return []

    # 🔥 clean expired
    now = time.time()

    SESSION_DB[key] = [
        m for m in SESSION_DB[key]
        if now - m["time"] < SESSION_TTL_SECONDS
    ]

    return SESSION_DB[key]