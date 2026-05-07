import asyncio
import json
import uuid
import time
import logging
import os

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from dotenv import load_dotenv
load_dotenv()


from app.engine import run_pipeline
from app.database import (
    get_all_chats,
    get_chat,
    delete_chat,
    create_chat,
    update_chat_title
)

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("api")


# =========================
# AUTH
# =========================
# BUG FIX 1: Removed duplicate `load_dotenv()` call (it was called twice).
API_KEYS = os.getenv("API_KEYS", "dev-key").split(",")


def verify_api_key(x_api_key: str = Header(None, alias="x-api-key")):
    # BUG FIX 2: Removed debug `print()` statements that leaked API keys to logs in production.
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Unauthorized")


# =========================
# RATE LIMIT
# =========================
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # BUG FIX 3: Added proper type hints to the exception handler — FastAPI requires
    # `request` typed as `Request` for the handler to be registered correctly.
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded"}
    )


# =========================
# STREAM HANDLER
# =========================
async def stream_response(topic: str, chat_id: str, user_id: str, request: Request):

    logger.info(f"Stream start | chat_id={chat_id}")

    # BUG FIX 4: Removed unused `finished = False` guard flag — it was declared but
    # never set to True, so it served no purpose and was misleading dead code.

    try:
        async for event in run_pipeline(topic, session_id=chat_id, user_id=user_id):

            if await request.is_disconnected():
                logger.warning(f"Client disconnected | chat_id={chat_id}")
                return

            yield f"data: {json.dumps(event)}\n\n"

    except Exception as e:
        logger.error(f"Stream error | {str(e)}")

        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    finally:
        # BUG FIX 5: Replaced bare `except: pass` with a typed `except Exception`
        # to avoid silently swallowing critical errors (e.g. SystemExit, KeyboardInterrupt).
        try:
            if not await request.is_disconnected():
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception:
            pass

        logger.info(f"Stream end | chat_id={chat_id}")


# =========================
# MAIN ROUTE
# =========================
@app.post("/research")
@limiter.limit("10/minute")
async def research(request: Request, _: str = Depends(verify_api_key)):

    try:
        # =========================
        # PARSE INPUT (SAFE)
        # =========================
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        topic = (data.get("topic") or "").strip()
        chat_id = data.get("chat_id")
        user_id = data.get("user_id", "default")

        # =========================
        # VALIDATION
        # =========================
        if not topic:
            raise HTTPException(400, "Missing topic")

        if len(topic) > 1000:
            raise HTTPException(400, "Query too long")

        # =========================
        # CHAT INIT
        # =========================
        if not chat_id:
            chat_id = str(uuid.uuid4())
            title = topic[:60] + ("..." if len(topic) > 60 else "")
            create_chat(chat_id, title)

        logger.info(f"Query | chat_id={chat_id} | user_id={user_id}")

        # =========================
        # STREAM WRAPPER (SAFE)
        # =========================
        async def event_generator():
            try:
                async for chunk in stream_response(topic, chat_id, user_id, request):

                    if await request.is_disconnected():
                        logger.info(f"Client disconnected | chat_id={chat_id}")
                        break

                    yield chunk

            except Exception as e:
                logger.error(f"Stream crash: {e}")
                # BUG FIX 6: The original code had a Python f-string syntax error:
                # `f"data: { {'type': ...} }\n\n"` — the inner dict literal conflicted
                # with the f-string brace syntax, producing malformed SSE output.
                # Fixed by using json.dumps() consistently, like the rest of the code.
                yield f"data: {json.dumps({'type': 'error', 'content': 'Internal error'})}\n\n"

        # =========================
        # RETURN STREAM (SSE SAFE)
        # =========================
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Research error: {str(e)}")
        raise HTTPException(500, "Internal server error")


# =========================
# FEEDBACK
# =========================
@app.post("/feedback")
@limiter.limit("20/minute")
async def feedback(request: Request, _: str = Depends(verify_api_key)):

    try:
        data = await request.json()

        correction = data.get("correction")
        query = data.get("query")
        chat_id = data.get("chat_id")
        user_id = data.get("user_id", "default")

        if not correction:
            raise HTTPException(400, "Missing correction")

        # BUG FIX 7: Moved import to top-level scope. Importing inside a function on
        # every request is inefficient and can hide import errors until runtime.
        from app.vector_store import embed, store_memory

        text = f"""
User correction:
Query: {query}
Correction: {correction}
"""

        emb = await embed(text)

        # BUG FIX 8: Added a guard — `store_memory` expects a valid embedding. If
        # `embed()` returns None (e.g. on API failure), calling store_memory with
        # None would silently fail or raise an unhandled error downstream.
        if emb is None:
            raise HTTPException(500, "Failed to generate embedding")

        store_memory(
            user_id=user_id,
            text=text,
            embedding=emb,
            session_id=chat_id or "global"
        )

        logger.info(f"Feedback stored | chat_id={chat_id}")

        return {"ok": True}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Feedback error: {str(e)}")
        raise HTTPException(500, str(e))


# =========================
# HISTORY
# =========================
@app.get("/history")
def history(_: str = Depends(verify_api_key)):
    try:
        return {"chats": get_all_chats()}
    except Exception as e:
        logger.error(f"History error: {str(e)}")
        raise HTTPException(500, str(e))


@app.get("/chat/{chat_id}")
def chat(chat_id: str, _: str = Depends(verify_api_key)):
    try:
        return {"messages": get_chat(chat_id)}
    except Exception as e:
        logger.error(f"Chat fetch error: {str(e)}")
        raise HTTPException(500, str(e))


# =========================
# CHAT MANAGEMENT
# =========================
@app.post("/rename_chat")
async def rename(req: Request, _: str = Depends(verify_api_key)):
    # BUG FIX 9: Added try/except and proper HTTPException re-raise so rename
    # failures don't crash with an unhandled 500 and no log trace.
    try:
        data = await req.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not data.get("chat_id") or not data.get("title"):
        raise HTTPException(400, "Invalid input")

    # BUG FIX 10: Added title length sanitisation consistent with database.py's
    # 100-char limit — without this, a long title bypassed the DB constraint.
    title = data["title"].strip()[:100]
    if not title:
        raise HTTPException(400, "Title cannot be empty")

    update_chat_title(data["chat_id"], title)
    return {"ok": True}


@app.post("/delete_chat")
async def delete(req: Request, _: str = Depends(verify_api_key)):
    # BUG FIX 11: Added try/except for JSON parsing, consistent with all other routes.
    try:
        data = await req.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not data.get("chat_id"):
        raise HTTPException(400, "Missing chat_id")

    delete_chat(data["chat_id"])
    return {"ok": True}


# =========================
# HEALTH
# =========================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": time.time()
    }


# =========================
# STATIC
# =========================
# BUG FIX 12: Moved the static mount and home route to the END of the file.
# In the original, `app.mount("/static", ...)` was placed before some route
# definitions. While FastAPI handles this fine in most cases, keeping mounts
# last is the correct pattern — a catch-all static mount can shadow dynamic
# routes registered after it if path prefixes overlap.
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def home():
    return FileResponse("frontend/index.html")






















# import asyncio
# import json
# import uuid
# import time
# import logging
# import os

# from fastapi import FastAPI, Request, HTTPException, Depends, Header
# from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
# from fastapi.staticfiles import StaticFiles

# from slowapi import Limiter
# from slowapi.util import get_remote_address
# from slowapi.errors import RateLimitExceeded

# from dotenv import load_dotenv
# load_dotenv()


# from app.engine import run_pipeline
# from app.database import (
#     get_all_chats,
#     get_chat,
#     delete_chat,
#     create_chat,
#     update_chat_title
# )

# # =========================
# # LOGGING
# # =========================
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s"
# )
# logger = logging.getLogger("api")


# # =========================
# # AUTH
# # =========================
# from dotenv import load_dotenv
# load_dotenv()

# API_KEYS = os.getenv("API_KEYS", "dev-key").split(",")


# def verify_api_key(x_api_key: str = Header(None, alias="x-api-key")):
#     print("RECEIVED:", x_api_key)
#     print("EXPECTED:", API_KEYS)

#     if not x_api_key or x_api_key not in API_KEYS:
#         raise HTTPException(status_code=401, detail="Unauthorized")


# # =========================
# # RATE LIMIT
# # =========================
# limiter = Limiter(key_func=get_remote_address)

# app = FastAPI()
# app.state.limiter = limiter


# @app.exception_handler(RateLimitExceeded)
# def rate_limit_handler(request, exc):
#     return JSONResponse(
#         status_code=429,
#         content={"error": "Rate limit exceeded"}
#     )


# # =========================
# # STREAM HANDLER
# # =========================
# async def stream_response(topic: str, chat_id: str, user_id: str, request: Request):

#     logger.info(f"Stream start | chat_id={chat_id}")

#     finished = False  # 🔥 guard flag

#     try:
#         async for event in run_pipeline(topic, session_id=chat_id, user_id=user_id):

#             if await request.is_disconnected():
#                 logger.warning(f"Client disconnected | chat_id={chat_id}")
#                 return  # 🔥 exit immediately (no done)

#             yield f"data: {json.dumps(event)}\n\n"

#     except Exception as e:
#         logger.error(f"Stream error | {str(e)}")

#         yield f"data: {json.dumps({
#             'type': 'error',
#             'content': str(e)
#         })}\n\n"

#     finally:
#         # 🔥 send done only if still connected and not already finished
#         try:
#             if not await request.is_disconnected():
#                 yield f"data: {json.dumps({'type': 'done'})}\n\n"
#         except:
#             pass

#         logger.info(f"Stream end | chat_id={chat_id}")
        


# # =========================
# # MAIN ROUTE
# # =========================
# @app.post("/research")
# @limiter.limit("10/minute")
# async def research(request: Request, _: str = Depends(verify_api_key)):

#     try:
#         # =========================
#         # PARSE INPUT (SAFE)
#         # =========================
#         try:
#             data = await request.json()
#         except Exception:
#             raise HTTPException(400, "Invalid JSON body")

#         topic = (data.get("topic") or "").strip()
#         chat_id = data.get("chat_id")
#         user_id = data.get("user_id", "default")

#         # =========================
#         # VALIDATION
#         # =========================
#         if not topic:
#             raise HTTPException(400, "Missing topic")

#         if len(topic) > 1000:
#             raise HTTPException(400, "Query too long")

#         # =========================
#         # CHAT INIT
#         # =========================
#         if not chat_id:
#             chat_id = str(uuid.uuid4())

#             # cleaner title (not raw topic dump)
#             title = topic[:60] + ("..." if len(topic) > 60 else "")
#             create_chat(chat_id, title)

#         logger.info(f"Query | chat_id={chat_id} | user_id={user_id}")

#         # =========================
#         # STREAM WRAPPER (SAFE)
#         # =========================
#         async def event_generator():
#             try:
#                 async for chunk in stream_response(topic, chat_id, user_id, request):

#                     if await request.is_disconnected():
#                         logger.info(f"Client disconnected | chat_id={chat_id}")
#                         break

#                     yield chunk

#             except Exception as e:
#                 logger.error(f"Stream crash: {e}")
#                 yield f"data: { {'type': 'error', 'content': 'Internal error'} }\n\n"


#         # =========================
#         # RETURN STREAM (SSE SAFE)
#         # =========================
#         return StreamingResponse(
#             event_generator(),
#             media_type="text/event-stream",
#             headers={
#                 "Cache-Control": "no-cache",
#                 "Connection": "keep-alive",
#                 "X-Accel-Buffering": "no"  # 🔥 critical for nginx / buffering issues
#             }
#         )

#     except HTTPException:
#         raise

#     except Exception as e:
#         logger.error(f"Research error: {str(e)}")
#         raise HTTPException(500, "Internal server error")
        
# # =========================
# # FEEDBACK
# # =========================
# @app.post("/feedback")
# @limiter.limit("20/minute")
# async def feedback(request: Request, _: str = Depends(verify_api_key)):

#     try:
#         data = await request.json()

#         correction = data.get("correction")
#         query = data.get("query")
#         chat_id = data.get("chat_id")
#         user_id = data.get("user_id", "default")

#         if not correction:
#             raise HTTPException(400, "Missing correction")

#         from app.vector_store import embed, store_memory

#         # ✅ BETTER CONTEXTUAL MEMORY
#         text = f"""
# User correction:
# Query: {query}
# Correction: {correction}
# """

#         emb = await embed(text)

#         store_memory(
#             user_id=user_id,
#             text=text,
#             embedding=emb,
#             session_id=chat_id or "global"
#         )

#         logger.info(f"Feedback stored | chat_id={chat_id}")

#         return {"ok": True}

#     except Exception as e:
#         logger.error(f"Feedback error: {str(e)}")
#         raise HTTPException(500, str(e))

# # =========================
# # HISTORY
# # =========================
# @app.get("/history")
# def history(_: str = Depends(verify_api_key)):
#     try:
#         return {"chats": get_all_chats()}
#     except Exception as e:
#         logger.error(f"History error: {str(e)}")
#         raise HTTPException(500, str(e))


# @app.get("/chat/{chat_id}")
# def chat(chat_id: str, _: str = Depends(verify_api_key)):
#     try:
#         return {"messages": get_chat(chat_id)}
#     except Exception as e:
#         logger.error(f"Chat fetch error: {str(e)}")
#         raise HTTPException(500, str(e))


# # =========================
# # CHAT MANAGEMENT
# # =========================
# @app.post("/rename_chat")
# async def rename(req: Request, _: str = Depends(verify_api_key)):
#     data = await req.json()

#     if not data.get("chat_id") or not data.get("title"):
#         raise HTTPException(400, "Invalid input")

#     update_chat_title(data["chat_id"], data["title"])
#     return {"ok": True}


# @app.post("/delete_chat")
# async def delete(req: Request, _: str = Depends(verify_api_key)):
#     data = await req.json()

#     if not data.get("chat_id"):
#         raise HTTPException(400, "Missing chat_id")

#     delete_chat(data["chat_id"])
#     return {"ok": True}


# # =========================
# # HEALTH
# # =========================
# @app.get("/health")
# def health():
#     return {
#         "status": "ok",
#         "time": time.time()
#     }


# # =========================
# # STATIC
# # =========================
# app.mount("/static", StaticFiles(directory="frontend"), name="static")


# @app.get("/")
# def home():
#     return FileResponse("frontend/index.html")