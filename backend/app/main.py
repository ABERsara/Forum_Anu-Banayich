import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.i18n import LanguageMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette inserts each new middleware at the front of the stack, so adding
# this last puts it *outermost* — it sees the request before CORS and every
# response on the way back. That is what we want: the language has to be
# resolved before anything downstream can raise, and `Vary: Accept-Language`
# then lands on every response, not only the ones that reach the router.
app.add_middleware(LanguageMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
