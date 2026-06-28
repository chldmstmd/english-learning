import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings as app_settings
from app.database import engine, Base, AsyncSessionLocal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models.user           # noqa: F401
    import app.models.article        # noqa: F401
    import app.models.annotation     # noqa: F401
    import app.models.reading_history  # noqa: F401
    import app.models.article_translation  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.services.schema_service import ensure_runtime_schema
        await ensure_runtime_schema(conn)

    # Any article left in `processing` is a corpse from a background task that
    # died with the previous process; reset it so it can be retried.
    from app.services import batch_translation_service
    async with AsyncSessionLocal() as session:
        await batch_translation_service.recover_stuck_translations(session)

    yield


app = FastAPI(title="Context Translation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import articles, translate, settings, auth  # noqa: E402

app.include_router(auth.router)
app.include_router(articles.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
