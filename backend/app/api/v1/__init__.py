"""API v1."""

from fastapi import APIRouter

from app.api.v1 import analysis, documents, jobs, match, session

api_router = APIRouter(prefix="/v1")
api_router.include_router(session.router)
api_router.include_router(documents.router)
api_router.include_router(analysis.router)
api_router.include_router(jobs.router)
api_router.include_router(match.router)

__all__ = ["api_router"]
