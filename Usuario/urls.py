from django.urls import path

from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import registrar, me

urlpatterns = [

    path("registrar/", registrar),

    path("me/", me),

    # AUDIT FIX: TokenObtainPairView/TokenRefreshView não declaram
    # permission_classes próprias, então herdam o DEFAULT_PERMISSION_CLASSES
    # do projeto. Agora que o padrão é IsAuthenticated (ver app/settings.py),
    # login e refresh precisam ser explicitamente públicos, ou ninguém
    # consegue fazer login.
    path("login/", TokenObtainPairView.as_view(permission_classes=[AllowAny])),

    path("refresh/", TokenRefreshView.as_view(permission_classes=[AllowAny])),
]