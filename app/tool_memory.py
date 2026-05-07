# =========================================
# 🔧 TOOL MEMORY (PRODUCTION VERSION)
# =========================================

import time

TOOL_DB = {}

# =========================================
# CONFIG
# =========================================
MAX_TOOL_HISTORY = 15
TOOL_TTL_SECONDS = 3600  # 1 hour


# =========================================
# CLEAN OLD TOOL MEMORY
# =========================================
def _clean_old_tools(key):
    if key not in TOOL_DB:
        return

    now = time.time()

    TOOL_DB[key] = [
        t for t in TOOL_DB[key]
        if now - t["time"] < TOOL_TTL_SECONDS
    ]


# =========================================
# TRACK TOOL USAGE
# =========================================
def track_tool(user_id, session_id, tool_name, query):

    if not tool_name or not query:
        return

    key = f"{user_id}_{session_id}"

    if key not in TOOL_DB:
        TOOL_DB[key] = []

    # 🔥 prevent duplicate consecutive calls
    if TOOL_DB[key]:
        last = TOOL_DB[key][-1]
        if last["tool"] == tool_name and last["query"] == query:
            return

    TOOL_DB[key].append({
        "tool": tool_name,
        "query": query.strip(),
        "time": time.time()
    })

    # 🔥 clean expired
    _clean_old_tools(key)

    # 🔥 limit size
    TOOL_DB[key] = TOOL_DB[key][-MAX_TOOL_HISTORY:]


# =========================================
# GET RAW TOOL HISTORY
# =========================================
def get_tool_history(user_id, session_id):

    key = f"{user_id}_{session_id}"

    if key not in TOOL_DB:
        return []

    _clean_old_tools(key)

    return TOOL_DB[key]


# =========================================
# SMART TOOL RETRIEVAL
# =========================================
def get_recent_tools(user_id, session_id, limit=5):

    key = f"{user_id}_{session_id}"

    if key not in TOOL_DB:
        return []

    _clean_old_tools(key)

    return TOOL_DB[key][-limit:]


def get_frequent_tools(user_id, session_id):

    key = f"{user_id}_{session_id}"

    if key not in TOOL_DB:
        return []

    _clean_old_tools(key)

    counts = {}

    for t in TOOL_DB[key]:
        tool = t["tool"]
        counts[tool] = counts.get(tool, 0) + 1

    # sort by usage frequency
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)


# =========================================
# CONTEXT FOR AGENTS
# =========================================
def get_tool_context(user_id, session_id):

    recent = get_recent_tools(user_id, session_id, limit=3)
    frequent = get_frequent_tools(user_id, session_id)

    return {
        "recent_tools": recent,
        "frequent_tools": frequent
    }