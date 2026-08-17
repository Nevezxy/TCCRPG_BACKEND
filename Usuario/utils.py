from rest_framework.exceptions import PermissionDenied

from .permissions import IsOwnerOrAdmin


permission = IsOwnerOrAdmin()


def check_object_permission(request, obj):

    if not permission.has_object_permission(request, None, obj):
        raise PermissionDenied()