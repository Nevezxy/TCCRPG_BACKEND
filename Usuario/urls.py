from django.urls import path

from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    me,
    me_campanhas,
    me_personagens,
    me_poder_detalhe,
    me_poderes,
    outras_campanhas,
    outros_personagens,
    perfil,
    registrar,
)

urlpatterns = [

    path("registrar/", registrar),

    path("me/", me),

    # Perfil (a página `/perfil` do frontend). Tudo sob `me/` é sempre do
    # usuário logado — não existe id na URL para trocar pelo de outra pessoa.
    path("me/personagens/", me_personagens),
    path("me/campanhas/", me_campanhas),
    path("me/poderes/", me_poderes),
    path("me/poderes/<int:pk>/", me_poder_detalhe),

    # Aba "Outros usuários" do perfil — só superusuário.
    path("outros/personagens/", outros_personagens),
    path("outros/campanhas/", outras_campanhas),

    # Perfil de outro usuário (somente leitura, sem e-mail).
    path("<int:pk>/", perfil),

    # AUDIT FIX: TokenObtainPairView/TokenRefreshView não declaram
    # permission_classes próprias, então herdam o DEFAULT_PERMISSION_CLASSES
    # do projeto. Agora que o padrão é IsAuthenticated (ver app/settings.py),
    # login e refresh precisam ser explicitamente públicos, ou ninguém
    # consegue fazer login.
    path("login/", TokenObtainPairView.as_view(permission_classes=[AllowAny])),

    path("refresh/", TokenRefreshView.as_view(permission_classes=[AllowAny])),
]