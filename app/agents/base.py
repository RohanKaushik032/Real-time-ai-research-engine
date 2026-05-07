# =========================================
# 🔹 BASE AGENT + LLM UTILITIES (PRODUCTION)
# =========================================

import os
import asyncio
import logging
from openai import OpenAI

logger = logging.getLogger("llm")

# =========================================
# 🔹 SAFE OPENAI CLIENT
# =========================================
_client = None

def get_client():
    global _client

    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        _client = OpenAI(api_key=api_key)

    return _client


# =========================================
# 🔹 LLM CALL (WITH RETRY)
# =========================================
async def call_llm(prompt: str, temperature=0.5, retries=2):

    client = get_client()

    for attempt in range(retries + 1):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                timeout=30
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.warning(f"LLM error (attempt {attempt+1}): {e}")
            await asyncio.sleep(0.8)

    return ""


# =========================================
# 🔹 CACHE (SAFE + LIMITED)
# =========================================
_LLM_CACHE = {}
_CACHE_MAX_SIZE = 500


def _cleanup_cache():
    if len(_LLM_CACHE) > _CACHE_MAX_SIZE:
        keys = list(_LLM_CACHE.keys())[:int(_CACHE_MAX_SIZE * 0.2)]
        for k in keys:
            _LLM_CACHE.pop(k, None)


async def cached_llm(prompt: str, temperature=0.5):

    key = f"{hash(prompt)}_{temperature}"

    if key in _LLM_CACHE:
        return _LLM_CACHE[key]

    result = await call_llm(prompt, temperature)

    if result:
        _LLM_CACHE[key] = result
        _cleanup_cache()

    return result


# =========================================
# 🔹 STREAMING (FIXED VERSION)
# =========================================
async def stream_llm(prompt: str, temperature=0.5):

    client = get_client()

    def create_stream():
        return client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            stream=True,
            timeout=60
        )

    try:
        stream = await asyncio.to_thread(create_stream)

        has_output = False

        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content

                if delta:
                    has_output = True
                    yield delta

            except Exception as e:
                logger.warning(f"Chunk parse error: {e}")
                continue

        # 🔴 CRITICAL: empty stream protection
        if not has_output:
            logger.warning("Empty stream response from model")
            yield "⚠️ Model returned empty response"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield "⚠️ Error generating response"


# =========================================
# 🔹 BASE AGENT
# =========================================
class BaseAgent:

    def _ok(self, data, latency):
        return {
            "success": True,
            "data": data,
            "latency": latency
        }

    def _fail(self, error, latency):
        return {
            "success": False,
            "error": str(error),
            "latency": latency
        }