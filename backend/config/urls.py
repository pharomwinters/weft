from api.api import api
from django.http import JsonResponse
from django.urls import path, re_path


def api_not_found(request, *args, **kwargs):
    body = {"error": {"code": "not_found", "message": "Not found.", "details": {}}}
    return JsonResponse(body, status=404)


urlpatterns = [
    path("api/v1/", api.urls),
    re_path(r"^api/", api_not_found),
]
