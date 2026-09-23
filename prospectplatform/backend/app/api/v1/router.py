from fastapi import APIRouter
from app.api.v1.endpoints.companies_router import router as companies_router
from app.api.v1.endpoints.geography_router import router as geography_router
from app.api.v1.endpoints.categories_router import router as categories_router
from app.api.v1.endpoints.import_router import router as import_router
from app.api.v1.endpoints.collect_router import router as collect_router
from app.api.v1.endpoints.audits import router as audits_router
from app.api.v1.endpoints.prospection import router as prospection_router
from app.api.v1.endpoints.dispatcher import router as dispatcher_router
from app.api.v1.endpoints.messages import router as messages_router
from app.api.v1.endpoints.replies import router as replies_router
from app.api.v1.endpoints.previews import router as previews_router

api_router = APIRouter()
api_router.include_router(companies_router)
api_router.include_router(geography_router)
api_router.include_router(categories_router)
api_router.include_router(import_router)
api_router.include_router(collect_router)
api_router.include_router(audits_router)
api_router.include_router(prospection_router)
api_router.include_router(dispatcher_router)
api_router.include_router(messages_router)
api_router.include_router(replies_router)
api_router.include_router(previews_router)
