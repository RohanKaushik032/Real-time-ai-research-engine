# =========================================
# 🧠 SESSION MEMORY (IMPROVED + LLM-AWARE)
# =========================================

import time

SESSION_DB = {}

# =========================================
# CONFIG
# =========================================
MAX_MESSAGES = 12
SESSION_TTL_SECONDS = 3600  # 1 hour
MAX_CHARS_PER_SESSION = 4000


# =========================================
# CLEAN OLD MEMORY
# =========================================
def _clean_old_memory(key):
    if key not in SESSION_DB:
        return

    now = time.time()

    SESSION_DB[key] = [
        m for m in SESSION_DB[key]
        if now - m["time"] < SESSION_TTL_SECONDS
    ]


# =========================================
# ESTIMATE LENGTH
# =========================================
def _total_chars(messages):
    return sum(len(m["content"]) for m in messages)


# =========================================
# SIMPLE IMPORTANCE FILTER
# =========================================
def _is_important(content: str):
    # ignore trivial messages
    if len(content) < 15:
        return False

    # ignore greetings
    low_value = ["hi", "hello", "thanks", "ok"]
    if content.lower().strip() in low_value:
        return False

    return True


# =========================================
# ADD TO SESSION
# =========================================
def add_to_session(user_id, session_id, role, content):

    if not content or not isinstance(content, str):
        return

    key = f"{user_id}_{session_id}"

    if key not in SESSION_DB:
        SESSION_DB[key] = []

    content = content.strip()

    # prevent duplicates
    if SESSION_DB[key] and SESSION_DB[key][-1]["content"] == content:
        return

    SESSION_DB[key].append({
        "role": role,
        "content": content,
        "time": time.time()
    })

    # clean expired
    _clean_old_memory(key)

    # keep only important messages if overflow
    if len(SESSION_DB[key]) > MAX_MESSAGES:
        SESSION_DB[key] = [
            m for m in SESSION_DB[key]
            if _is_important(m["content"])
        ][-MAX_MESSAGES:]

    # enforce size
    while _total_chars(SESSION_DB[key]) > MAX_CHARS_PER_SESSION:
        SESSION_DB[key].pop(0)


# =========================================
# FORMAT FOR LLM
# =========================================
def _format_for_llm(messages):
    lines = []

    for m in messages:
        role = m["role"].upper()
        lines.append(f"{role}: {m['content']}")

    return "\n".join(lines)


# =========================================
# GET SESSION CONTEXT
# =========================================
def get_session_context(user_id, session_id):

    key = f"{user_id}_{session_id}"

    if key not in SESSION_DB:
        return []

    _clean_old_memory(key)

    messages = SESSION_DB[key]

    # return BOTH raw + formatted (important for hybrid system)
    return [
        {
            "role": m["role"],
            "content": m["content"],
            "formatted": f"{m['role'].upper()}: {m['content']}"
        }
        for m in messages
    ]