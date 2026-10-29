import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import models  # noqa: F401
from backend.db import Base, engine
from backend.items import router as items_router


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(items_router)


@app.get("/health")
def health():
    return {"status": "ok", "seed": int(os.getenv("SEED", 42))}


@app.get("/ready")
def ready():
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": type(e).__name__})
