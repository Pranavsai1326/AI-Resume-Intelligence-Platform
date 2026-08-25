"""API v1."""

from fastapi import APIRouter

from app.api.v1 import ai, analysis, career, documents, export, jobs, match, resume, session, tailor

api_router = APIRouter(prefix="/v1")
api_router.include_router(session.router)
api_router.include_router(documents.router)
api_router.include_router(analysis.router)
api_router.include_router(jobs.router)
api_router.include_router(match.router)
api_router.include_router(resume.router)
api_router.include_router(ai.router)
api_router.include_router(tailor.router)
api_router.include_router(export.router)
api_router.include_router(career.router)

__all__ = ["api_router"]
