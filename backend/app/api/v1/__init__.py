"""API v1."""

from fastapi import APIRouter

from app.api.v1 import session

api_router = APIRouter(prefix="/v1")
api_router.include_router(session.router)

__all__ = ["api_router"]
