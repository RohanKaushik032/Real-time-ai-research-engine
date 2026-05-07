# =========================================
# 🧠 ANALYSIS AGENT (PRODUCTION ALIGNED)
# =========================================

import re
import asyncio
import logging
from .base import cached_llm

logger = logging.getLogger("analysis_agent")


# =========================================
# 🔹 SOURCE SCORING (OPTIONAL USE)
# =========================================
class AnalysisAgent:

    def evaluate_sources(self, sources):
        scored_sources = []

        for src in sources:
            content = src.get("content", "") or ""
            url = src.get("url", "") or ""

            credibility = self._score_credibility(url)
            evidence = self._score_evidence(content)

            total_score = credibility * 0.6 + evidence * 0.4

            scored_sources.append({
                "title": src.get("title"),
                "content": content,
                "url": url,
                "credibility": credibility,
                "evidence": evidence,
                "score": round(total_score, 2)
            })

        return sorted(scored_sources, key=lambda x: x["score"], reverse=True)

    def _score_credibility(self, url: str) -> int:
        if not url:
            return 2

        trusted = ["bbc", "nature", "harvard", "who.int", "gov", "edu", "ieee"]

        score = 3
        for t in trusted:
            if t in url:
                score += 2

        return min(score, 5)

    def _score_evidence(self, content: str) -> int:
        score = 0

        if re.search(r"\d+%", content):
            score += 2

        if re.search(r"\d{4}", content):
            score += 1

        if len(content) > 200:
            score += 2

        return min(score, 5)


# =========================================
# 🔹 SAFE PARSE
# =========================================
def _parse_lines(text: str, max_items=5):
    if not text:
        return []

    lines = [
        l.strip("-• ").strip()
        for l in text.split("\n")
        if l.strip()
    ]

    return lines[:max_items]


# =========================================
# 🔹 DECOMPOSE QUERY
# =========================================
async def decompose(topic: str):

    if not topic or len(topic) < 3:
        return [topic]

    prompt = f"""
Break this query into 3-4 focused sub-questions.

Query:
{topic}

Return bullet list only.
"""

    try:
        res = await asyncio.wait_for(
            cached_llm(prompt, 0.3),
            timeout=8
        )

        parsed = _parse_lines(res, 4)
        return parsed if parsed else [topic]

    except Exception as e:
        logger.warning(f"Decompose error: {e}")
        return [topic]


# =========================================
# 🔹 REFINE SEARCH
# =========================================
async def refine(topic: str, prev_queries: list):

    if not topic:
        return prev_queries

    prompt = f"""
Improve these search queries.

Topic:
{topic}

Current:
{prev_queries}

Return 3 better queries.
"""

    try:
        res = await asyncio.wait_for(
            cached_llm(prompt, 0.4),
            timeout=8
        )

        parsed = _parse_lines(res, 3)
        return parsed if parsed else prev_queries

    except Exception as e:
        logger.warning(f"Refine error: {e}")
        return prev_queries


# =========================================
# 🔹 FOLLOWUP QUESTIONS
# =========================================
async def followups(topic: str, interests=None):

    if not topic:
        return []

    interests_txt = ", ".join(interests) if interests else "general"

    prompt = f"""
Suggest 3-4 follow-up questions.

Topic:
{topic}

User interests:
{interests_txt}
"""

    try:
        res = await asyncio.wait_for(
            cached_llm(prompt, 0.6),
            timeout=8
        )

        return _parse_lines(res, 4)

    except Exception as e:
        logger.warning(f"Followup error: {e}")
        return []