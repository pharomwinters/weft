from ninja import NinjaAPI

from .errors import register_error_handlers

api = NinjaAPI(docs_url=None, openapi_url=None)
register_error_handlers(api)


@api.get("/health")
def health(request):
    return {"status": "ok"}
