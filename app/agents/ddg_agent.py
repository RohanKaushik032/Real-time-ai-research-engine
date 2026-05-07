import httpx
import logging

logger = logging.getLogger("ddg")

async def ddg_search(query: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json"}
            )
            
            if res.status_code != 200:
                logger.warning(f"DDG HTTP {res.status_code}")
                return []

            data = res.json()

        results = []

        # =========================
        # PRIMARY RESULT
        # =========================
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "DuckDuckGo"),
                "content": data.get("AbstractText"),
                "url": data.get("AbstractURL") or "#",
                "source": "ddg"
            })

        # =========================
        # RELATED TOPICS
        # =========================
        related = data.get("RelatedTopics", [])

        for item in related:
            # Check for nested 'Topics' first (sub-categories)
            if "Topics" in item:
                for sub in item.get("Topics", []):
                    text = sub.get("Text")
                    url = sub.get("FirstURL")
                    if text and len(text) > 30:
                        results.append({
                            "title": text[:80],
                            "content": text,
                            "url": url or "#",
                            "source": "ddg"
                        })
            
            # Then check for standard result items
            elif isinstance(item, dict):
                text = item.get("Text")
                url = item.get("FirstURL")
                if text and len(text) > 30:
                    results.append({
                        "title": text[:80],
                        "content": text,
                        "url": url or "#",
                        "source": "ddg"
                    })

        return results[:5]

    except Exception as e:
        logger.warning(f"DDG failed: {e}")
        return []