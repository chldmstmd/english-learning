import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base

logger = logging.getLogger(__name__)

_VOA_SYNC_INTERVAL_SECONDS = 6 * 3600


async def _periodic_voa_sync():
    await asyncio.sleep(15)
    while True:
        logger.info("Starting periodic VOA sync...")
        try:
            from app.services import voa_service
            await voa_service.sync_all_feeds()
        except Exception as exc:
            logger.error("Periodic VOA sync error: %s", exc)
        await asyncio.sleep(_VOA_SYNC_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models.user           # noqa: F401
    import app.models.article        # noqa: F401
    import app.models.vocabulary     # noqa: F401
    import app.models.annotation     # noqa: F401
    import app.models.sync_log       # noqa: F401
    import app.models.bookmark       # noqa: F401
    import app.models.reading_history  # noqa: F401
    import app.models.article_translation  # noqa: F401
    import app.models.book           # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sync_task = asyncio.create_task(_periodic_voa_sync())
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Context-Aware Smart Reader", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import articles, vocab, translate, settings, library, admin, auth, books  # noqa: E402

app.include_router(auth.router)
app.include_router(articles.router, prefix="/api/v1")
app.include_router(vocab.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(library.router, prefix="/api/v1")
app.include_router(books.router, prefix="/api/v1")
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
