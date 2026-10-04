from accounts import services
from accounts.models import TotpDevice, User
from accounts.sessions import SessionRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from permissions import actions
from permissions.core import INSTANCE, require

from ..schemas import AdminFlagIn, AdminUserOut, ResetLinkOut

router = Router()


def _user(request: SessionRequest, user_id: int) -> User:
    require(request.auth, actions.INSTANCE_MANAGE_USERS, INSTANCE)
    return get_object_or_404(User, pk=user_id)


@router.get("", response=list[AdminUserOut])
def list_users(request: SessionRequest):
    require(request.auth, actions.INSTANCE_MANAGE_USERS, INSTANCE)
    enrolled = set(
        TotpDevice.objects.filter(confirmed=True).values_list("user_id", flat=True)
    )
    return [
        {
            "id": user.pk,
            "email": user.email,
            "is_instance_admin": user.is_instance_admin,
            "is_active": user.is_active,
            "has_2fa": user.pk in enrolled,
            "created_at": user.created_at,
        }
        for user in User.objects.order_by("email")
    ]


@router.post("/{user_id}/deactivate", response={204: None})
def deactivate(request: SessionRequest, user_id: int):
    services.deactivate(_user(request, user_id), actor=request.auth, request=request)
    return Status(204, None)


@router.post("/{user_id}/reactivate", response={204: None})
def reactivate(request: SessionRequest, user_id: int):
    services.reactivate(_user(request, user_id), actor=request.auth, request=request)
    return Status(204, None)


@router.put("/{user_id}/admin", response={204: None})
def set_admin(request: SessionRequest, user_id: int, payload: AdminFlagIn):
    services.set_admin(
        _user(request, user_id),
        payload.is_instance_admin,
        actor=request.auth,
        request=request,
    )
    return Status(204, None)


@router.post("/{user_id}/reset-link", response={201: ResetLinkOut})
def create_reset_link(request: SessionRequest, user_id: int):
    url, link = services.create_reset_link(
        _user(request, user_id), actor=request.auth, request=request
    )
    return Status(201, {"url": url, "expires_at": link.expires_at})


@router.post("/{user_id}/reset-2fa", response={204: None})
def reset_second_factor(request: SessionRequest, user_id: int):
    services.reset_second_factor(
        _user(request, user_id), actor=request.auth, request=request
    )
    return Status(204, None)
