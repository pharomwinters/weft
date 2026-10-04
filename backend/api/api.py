from ninja import NinjaAPI

from .auth import anonymous, verified
from .errors import register_error_handlers
from .routers.account import router as account_router
from .routers.auth import router as auth_router
from .routers.setup import router as setup_router
from .routers.workspaces import router as workspaces_router

api = NinjaAPI(auth=verified, docs_url=None, openapi_url=None)
register_error_handlers(api)
api.add_router("/auth", auth_router)
api.add_router("/account", account_router)
api.add_router("/setup", setup_router)
api.add_router("/workspaces", workspaces_router)


@api.get("/health", auth=anonymous)
def health(request):
    return {"status": "ok"}
