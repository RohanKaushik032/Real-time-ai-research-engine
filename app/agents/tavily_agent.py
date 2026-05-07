import os
import time
import asyncio
import httpx
import logging

from .base import BaseAgent

logger = logging.getLogger("tavily")
CACHE_TTL = 300


# =========================================
# CROSS ENCODER (moved here to break circular import)
# =========================================
_encoder = None

def _get_encoder():
    """Singleton cross-encoder — loads once, reused forever."""
    global _encoder
    if _encoder is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading CrossEncoder model (first time only)...")
        _encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _encoder


# =========================================
# AGENT
# =========================================
class TavilyAgent(BaseAgent):
    name = "tavily"

    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")

    async def fetch(self, topic: str, retries=2):
        start = time.time()

        if not self.api_key:
            logger.error("TAVILY_API_KEY is not set in environment")
            return self._fail("Missing Tavily API Key", 0)

        url = "https://api.tavily.com/search"

        payload = {
            "api_key": self.api_key,
            "query": topic,
            "search_depth": "advanced",
            "max_results": 6
        }

        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    res = await client.post(url, json=payload)

                    if res.status_code != 200:
                        raise Exception(f"HTTP {res.status_code}: {res.text}")

                    data = res.json()

                results = []

                for item in data.get("results", []):
                    content = (item.get("content") or "").strip()

                    if len(content) < 30:
                        continue

                    results.append({
                        "title": item.get("title"),
                        "content": content[:500],
                        "url": item.get("url"),
                        "source": "tavily"
                    })

                latency = int((time.time() - start) * 1000)
                logger.info(f"Tavily returned {len(results)} results in {latency}ms")
                return self._ok(results, latency)

            except Exception as e:
                logger.warning(f"Tavily retry {attempt+1}: {e}")
                if attempt < retries:
                    await asyncio.sleep(0.5)

        latency = int((time.time() - start) * 1000)
        logger.error("Tavily failed all retries, returning empty")
        return self._ok([], latency)


# =========================================
# CACHE & GLOBAL INSTANCE
# =========================================
_SEARCH_CACHE = {}
_CACHE_TIME = {}
_agent = TavilyAgent()


# =========================================
# DEDUP
# =========================================
def _deduplicate(results):
    seen = set()
    unique = []
    for r in results:
        url = r.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
        elif not url:
            # keep results without URLs (rare) but don't dedup them
            unique.append(r)
    return unique


# =========================================
# DDG FALLBACK (inline, no separate file needed)
# =========================================
async def _ddg_search(query: str):
    """DuckDuckGo fallback search."""
    try:
        # Support both old and new package names gracefully
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=4))
        )
        return [
            {
                "title": r.get("title", ""),
                "content": (r.get("body") or "")[:500],
                "url": r.get("href", ""),
                "source": "ddg"
            }
            for r in results
            if len((r.get("body") or "")) >= 30
        ]
    except Exception as e:
        logger.warning(f"DDG search failed: {e}")
        return []


# =========================================
# MAIN SEARCH
# =========================================
async def cached_search(query: str):
    now = time.time()

    # --- cache hit ---
    if query in _SEARCH_CACHE:
        if now - _CACHE_TIME.get(query, 0) < CACHE_TTL:
            logger.info(f"Cache hit for: {query}")
            return _SEARCH_CACHE[query]

    tavily_results = []
    ddg_results = []

    # --- parallel fetch ---
    try:
        tavily_task = asyncio.create_task(_agent.fetch(query))
        ddg_task = asyncio.create_task(_ddg_search(query))

        tavily_res, ddg_res = await asyncio.gather(
            tavily_task, ddg_task, return_exceptions=True
        )

        if isinstance(tavily_res, Exception):
            logger.error(f"Tavily task exception: {tavily_res}")
        else:
            tavily_results = tavily_res.get("data", [])
            logger.info(f"Tavily results: {len(tavily_results)}")

        if isinstance(ddg_res, Exception):
            logger.error(f"DDG task exception: {ddg_res}")
        else:
            ddg_results = ddg_res or []
            logger.info(f"DDG results: {len(ddg_results)}")

    except Exception as e:
        logger.error(f"Parallel fetch failed: {e}")

    # --- merge ---
    combined = []

    for r in tavily_results:
        r["weight"] = 1.0
        combined.append(r)

    for r in ddg_results:
        r["weight"] = 0.6
        combined.append(r)

    # --- FIX: return empty list so engine.py handles fallback correctly ---
    if not combined:
        logger.warning("No results from Tavily or DDG — returning empty for engine fallback")
        return []  # ✅ engine.py will show proper fallback message

    # --- dedup ---
    combined = _deduplicate(combined)

    # --- rerank (no circular import) ---
    try:
        model = _get_encoder()

        pairs = [
            (query, (r.get("content") or "")[:300])
            for r in combined
        ]

        scores = model.predict(pairs)

        for i, r in enumerate(combined):
            r["score"] = float(scores[i]) * r.get("weight", 1.0)

        combined = sorted(combined, key=lambda x: x.get("score", 0), reverse=True)
        logger.info("Reranking successful")

    except Exception as e:
        logger.warning(f"Rerank failed (using original order): {e}")

    final_results = combined[:5]

    # --- update cache ---
    _SEARCH_CACHE[query] = final_results
    _CACHE_TIME[query] = now

    logger.info(f"Returning {len(final_results)} final results")
    return final_results