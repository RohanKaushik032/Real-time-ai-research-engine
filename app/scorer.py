import math
from urllib.parse import urlparse


# =========================================
# CONFIG
# =========================================
HIGH_TRUST_DOMAINS = ["gov", "edu", "ieee", "nature", "acm"]
MEDIUM_TRUST_DOMAINS = ["org", "research", "springer", "sciencedirect"]

MIN_CONTENT_LENGTH = 100


# =========================================
# DOMAIN AUTHORITY
# =========================================
def get_domain_score(url):
    try:
        domain = urlparse(url).netloc.lower()

        if any(d in domain for d in HIGH_TRUST_DOMAINS):
            return 1.0
        if any(d in domain for d in MEDIUM_TRUST_DOMAINS):
            return 0.7

        return 0.4
    except:
        return 0.3


# =========================================
# RELEVANCE (BETTER)
# =========================================
def compute_relevance(query, content, title):
    query_words = set(query.lower().split())

    text = (content + " " + title).lower().split()
    text_words = set(text)

    overlap = query_words.intersection(text_words)

    if not query_words:
        return 0

    return len(overlap) / len(query_words)


# =========================================
# LENGTH QUALITY
# =========================================
def compute_length_score(content):
    length = len(content)

    if length < MIN_CONTENT_LENGTH:
        return 0.2  # penalize short content

    return min(length / 800, 1.0)


# =========================================
# MAIN SCORING
# =========================================
def score_sources(sources, query):

    scored = []

    for src in sources:

        content = (src.get("content") or "")
        title = (src.get("title") or "")
        url = src.get("url") or ""

        # =========================
        # SCORES
        # =========================
        relevance = compute_relevance(query, content, title)
        length_score = compute_length_score(content)
        authority = get_domain_score(url)

        # 🔥 combine (better weighting)
        final_score = (
            0.5 * relevance +
            0.3 * authority +
            0.2 * length_score
        )

        src["score"] = round(final_score, 4)
        src["relevance"] = round(relevance, 3)
        src["authority"] = round(authority, 3)

        scored.append(src)

    # sort descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored


# =========================================
# CONFIDENCE (SMARTER)
# =========================================
def compute_confidence(scored_sources):

    if not scored_sources:
        return 0

    top = scored_sources[:5]

    scores = [s["score"] for s in top]

    avg = sum(scores) / len(scores)

    # 🔥 variance penalty
    variance = sum((s - avg) ** 2 for s in scores) / len(scores)
    variance_penalty = min(variance * 100, 30)

    confidence = (avg * 100) - variance_penalty

    return round(max(0, min(confidence, 100)), 2)