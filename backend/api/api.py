from ninja import NinjaAPI

from .auth import anonymous, verified
from .errors import register_error_handlers
from .routers.auth import router as auth_router

api = NinjaAPI(auth=verified, docs_url=None, openapi_url=None)
register_error_handlers(api)
api.add_router("/auth", auth_router)


@api.get("/health", auth=anonymous)
def health(request):
    return {"status": "ok"}
