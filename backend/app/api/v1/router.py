"""
Main API router – registers all endpoint routers.

To add a new feature:
  1. Create backend/app/api/v1/endpoints/your_feature.py
  2. Import the router here and add it with include_router()
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    forum,
    health,
    moderator,
    professional,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(forum.router)
api_router.include_router(professional.router)
api_router.include_router(admin.router)
api_router.include_router(moderator.router)
