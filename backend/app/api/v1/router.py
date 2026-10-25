from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.matching import router as matching_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.profile import router as profile_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.saved_searches import router as saved_searches_router
from app.core.config import settings
from app.core.database import check_database_health
from app.schemas.health import HealthResponse

api_router = APIRouter()


@api_router.get("/health", response_model=HealthResponse, tags=["System"])
async def get_health() -> HealthResponse:
    """Service health and liveness probe."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        version="0.1.0",
    )


@api_router.get("/health/db", tags=["System"])
async def get_db_health() -> JSONResponse:
    """Database connectivity health check."""
    health_result = await check_database_health()
    status_code = (
        status.HTTP_200_OK
        if health_result.get("connected")
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=health_result)


# Include sub-routers
api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(resumes_router)
api_router.include_router(jobs_router)
api_router.include_router(matching_router)
api_router.include_router(documents_router)
api_router.include_router(applications_router)
api_router.include_router(saved_searches_router)
api_router.include_router(notifications_router)
