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
    import app.models.vocabulary     # noqa: F401
    import app.models.annotation     # noqa: F401
    import app.models.bookmark       # noqa: F401
    import app.models.reading_history  # noqa: F401
    import app.models.article_translation  # noqa: F401
    import app.models.book           # noqa: F401
    import app.models.book_shelf      # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if app_settings.admin_email:
        from sqlalchemy import select, update
        from app.models.user import User as UserModel
        async with AsyncSessionLocal() as session:
            user = await session.scalar(
                select(UserModel).where(UserModel.email == app_settings.admin_email.lower().strip())
            )
            if user and user.role == "user":
                await session.execute(
                    update(UserModel).where(UserModel.id == user.id).values(role="super_admin")
                )
                await session.commit()
                logger.info("Promoted %s to super_admin", app_settings.admin_email)

    yield


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
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
