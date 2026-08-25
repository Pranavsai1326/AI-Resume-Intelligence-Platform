"""API v1."""

from fastapi import APIRouter

from app.api.v1 import analysis, documents, session

api_router = APIRouter(prefix="/v1")
api_router.include_router(session.router)
api_router.include_router(documents.router)
api_router.include_router(analysis.router)

__all__ = ["api_router"]
