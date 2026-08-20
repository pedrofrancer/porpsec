from app.api.v1.endpoints.companies_router import router as companies_router
from app.api.v1.endpoints.geography_router import router as geography_router
from app.api.v1.endpoints.categories_router import router as categories_router
from app.api.v1.endpoints.import_router import router as import_router

api_router = companies_router
api_router.include_router(geography_router)
api_router.include_router(categories_router)
api_router.include_router(import_router)
