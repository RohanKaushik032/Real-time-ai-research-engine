# =========================================
# ENGINE (FIXED - PRODUCTION SAFE)
# =========================================

import asyncio
import time
import logging
import re
from functools import lru_cache

from app.agents.tavily_agent import cached_search
from app.agents.base import stream_llm, cached_llm
from app.hybrid_memory import get_hybrid_context, format_context_for_prompt
from app.session_memory import add_to_session
from app.database import save_message
from app.vector_store import embed, store_memory

logger = logging.getLogger("engine")
logging.basicConfig(level=logging.INFO)


# =========================================
# ROUTER
# =========================================
def classify_query(query: str):
    q = query.lower()

    if len(q) < 40:
        return "fast"

    if any(x in q for x in ["compare", "analyze", "why", "impact"]):
        return "deep"

    return "fast"


# =========================================
# CROSS ENCODER
# NOTE: moved to tavily_agent.py to avoid circular import.
# Kept here only as a proxy so other code that imports from engine still works.
# =========================================
@lru_cache(maxsize=1)
def get_cross_encoder():
    from sentence_transformers import CrossEncoder
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# =========================================
# SAFE CALC
# =========================================
def safe_calculate(expr: str):
    try:
        expr = re.sub(r"[^0-9+\-*/(). ]", "", expr)
        return str(eval(expr))
    except:
        return None


# =========================================
# DEDUP
# =========================================
def deduplicate_sources(sources):
    seen = set()
    unique = []

    for s in sources:
        url = s.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(s)

    return unique


# =========================================
# RERANK (SAFE)
# =========================================
def cross_rerank(query, sources):
    try:
        if len(sources) < 2:
            return sources

        model = get_cross_encoder()
        pairs = [(query, s.get("content", "")[:300]) for s in sources]
        scores = model.predict(pairs)

        for i, s in enumerate(sources):
            s["score"] = float(scores[i])

        return sorted(sources, key=lambda x: x["score"], reverse=True)

    except Exception as e:
        logger.warning(f"Rerank failed: {e}")
        return sources


# =========================================
# CONTEXT
# =========================================
def build_context_with_citations(sources):
    context_blocks = []
    mapped_sources = []

    if not sources:
        return "", []

    for i, s in enumerate(sources):
        idx = i + 1

        title = s.get("title") or "Source"
        url = s.get("url") or "#"
        content = s.get("content") or ""

        mapped_sources.append({
            "id": idx,
            "title": title,
            "url": url
        })

        context_blocks.append(
            f"[{idx}] {title}\n{content[:300]}"
        )

    return "\n\n".join(context_blocks), mapped_sources


# =========================================
# PROMPT
# =========================================
def build_prompt(query, context, memory=None):
    mem = "\n".join(memory[:3]) if memory else ""

    return f"""
You are an expert research assistant with deep knowledge across science, technology, and current events.

STRICT RULES:
- Use ONLY the provided sources as your primary reference
- Cite sources using [1], [2], etc. inline where relevant
- Do NOT hallucinate — if something is not in the sources, say so clearly
- Write in clear, engaging prose — not robotic or overly formal

USER QUERY:
{query}

PAST CONTEXT:
{mem}

SOURCES:
{context}

OUTPUT FORMAT (follow this exactly):

## Answer
Write a thorough, well-structured answer of 6-8 sentences. Cover the main point clearly, include key facts from the sources, and give the reader real insight — not just surface-level summaries. Cite sources inline like [1].

## Detailed Explanation
Write 15-20 lines of in-depth explanation. Break down the topic, explain the mechanisms or reasons behind it, discuss implications, and connect ideas across sources. Use paragraphs, not just bullets. Cite sources where applicable.

## Key Points
- (5-7 concise, specific bullet points — each should be a distinct insight, not a repetition)
- Each point should be 1-2 sentences and contain a concrete fact or takeaway

## Examples (if relevant)
Provide 2-3 specific, real-world examples that illustrate the concepts above.
"""


# =========================================
# EVALUATION
# =========================================
async def evaluate_answer(query, answer, sources):
    try:
        prompt = f"""
Query: {query}
Answer: {answer}

Return JSON only, no markdown:
{{"relevance":0-1,"grounded":0-1,"clarity":0-1}}
"""
        result = await asyncio.wait_for(
            cached_llm(prompt, temperature=0),
            timeout=6
        )

        import json
        # strip markdown fences if present
        result = result.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(result)

        relevance = float(data.get("relevance", 0.5))
        grounded = float(data.get("grounded", 0.5))
        clarity = float(data.get("clarity", 0.5))

    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
        relevance = grounded = clarity = 0.5

    bonus = min(len(sources) / 5, 1)

    return {
        "relevance": relevance,
        "grounded": grounded,
        "clarity": clarity,
        "final": round(0.4*relevance + 0.3*grounded + 0.2*clarity + 0.1*bonus, 2)
    }


# =========================================
# FAST PIPELINE
# =========================================
async def fast_pipeline(query):
    try:
        # ✅ FIX: increased timeout from 4s → 10s
        sources = await asyncio.wait_for(cached_search(query), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Fast search timed out after 10s")
        sources = []
    except Exception as e:
        logger.warning(f"Fast search failed: {e}")
        sources = []

    return sources[:3]


# =========================================
# DEEP PIPELINE
# =========================================
async def deep_pipeline(query):
    try:
        # ✅ FIX: increased timeout from 5s → 15s
        sources = await asyncio.wait_for(cached_search(query), timeout=15)
    except asyncio.TimeoutError:
        logger.warning("Deep search timed out after 15s")
        sources = []
    except Exception as e:
        logger.warning(f"Deep search failed: {e}")
        sources = []

    sources = deduplicate_sources(sources)
    return cross_rerank(query, sources)[:5]


# =========================================
# MAIN PIPELINE (FIXED)
# =========================================
async def run_pipeline(query, session_id=None, user_id="default"):

    start = time.time()
    logger.info(f"Query: {query}")

    try:
        yield {"type": "stage", "content": "🔎 Processing..."}

        # MEMORY
        try:
            memory_items = await get_hybrid_context(user_id, session_id, query)
            memory = format_context_for_prompt(memory_items[:3])
        except Exception as e:
            logger.warning(f"Memory fetch failed: {e}")
            memory = []

        # CALC
        calc = safe_calculate(query)
        if calc:
            yield {"type": "token", "content": calc}
            return

        # MODE
        mode = classify_query(query)
        yield {"type": "stage", "content": f"⚙️ Mode: {mode}"}

        # RETRIEVAL
        try:
            sources = await (deep_pipeline(query) if mode == "deep" else fast_pipeline(query))
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            sources = []

        used_fallback = False
        full = ""

        # FALLBACK — only triggers when sources is truly empty
        if not sources:
            yield {"type": "stage", "content": "⚠️ Using general knowledge"}

            fallback = await cached_llm(query)
            fallback = fallback or "⚠️ Unable to generate response."

            yield {"type": "token", "content": fallback}

            full = fallback
            used_fallback = True

            sources = [{"title": "Fallback", "url": ""}]

        # CONTEXT
        context, mapped_sources = build_context_with_citations(sources)

        yield {"type": "sources", "data": mapped_sources}

        # ✅ FIX: confidence now reflects real source count properly
        confidence = 0.3 if used_fallback else round(min(len(sources) / 5, 1.0), 2)
        yield {"type": "confidence", "value": confidence}

        # GENERATION (only if we have real sources)
        if not used_fallback:
            yield {"type": "stage", "content": "🧠 Generating..."}

            prompt = build_prompt(query, context, memory)

            async for chunk in stream_llm(prompt):
                if chunk:
                    full += chunk
                    yield {"type": "token", "content": chunk}

        # FINAL SAFETY
        if not full.strip():
            fallback = await cached_llm(query) or "⚠️ Unable to generate response."
            yield {"type": "token", "content": fallback}
            full = fallback

        # EVALUATION
        eval_result = await evaluate_answer(query, full, sources)
        yield {"type": "evaluation", "data": eval_result}

        # EXPLAIN
        yield {"type": "explain", "content": f"Used {len(sources)} sources | Mode: {mode}"}

        # SAVE
        try:
            add_to_session(user_id, session_id, "user", query)
            add_to_session(user_id, session_id, "assistant", full)
            save_message(session_id, "user", query)
            save_message(session_id, "assistant", full)
        except Exception as e:
            logger.warning(f"Save failed: {e}")

        yield {
            "type": "metrics",
            "data": {"latency": round(time.time()-start, 2), "mode": mode}
        }

    except Exception as e:
        logger.error(f"Pipeline crash: {e}")
        yield {"type": "error", "content": "Internal error"}