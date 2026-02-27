from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import tokens
from database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup (suitable for a POC; use Alembic for production)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Token-counting middleware that validates API credentials, measures text "
        "via tiktoken, and atomically deducts from a group's token-type bucket."
    ),
    lifespan=lifespan,
)

app.include_router(tokens.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
