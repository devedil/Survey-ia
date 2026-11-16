from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.browser.router import router as browser_router
from backend.app.browser.session_manager import BrowserSessionManager
from backend.app.core.config import get_settings
from backend.app.documents.router import router as documents_router
from backend.app.answers.router import router as answers_router
from backend.app.memory.router import router as memory_router
from backend.app.questions.router import router as questions_router
from backend.app.profiles.router import router as profiles_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    browser_sessions = BrowserSessionManager(settings.browser_allowed_origins)
    app.state.browser_session_manager = browser_sessions
    try:
        yield
    finally:
        browser_sessions.close_all()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend base para AI Survey Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(questions_router, prefix="/api/v1")
app.include_router(answers_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(browser_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI Survey Assistant backend is running"}
