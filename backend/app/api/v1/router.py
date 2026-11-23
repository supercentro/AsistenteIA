from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    auth,
    chat,
    conversations,
    documents,
    enrollments,
    health,
    subjects,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(subjects.router)
api_router.include_router(activity.router)
api_router.include_router(enrollments.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
