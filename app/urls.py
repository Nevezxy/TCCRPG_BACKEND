from django.contrib import admin
from django.urls import include, path
from rest_framework.permissions import AllowAny
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('personagem/', include('Personagem.urls')),
    path("usuario/", include("Usuario.urls")),
    path("campanha/", include("Campanha.urls")),
    path("sistema/", include("Sistema.urls")),
    
    # Schema
    # AUDIT FIX: estas views não declaravam permission_classes próprias,
    # então dependiam do DEFAULT_PERMISSION_CLASSES global. Documentação
    # da API deve continuar acessível sem login.
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),

    # Swagger
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]),
        name="swagger-ui",
    ),

    # Redoc
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema", permission_classes=[AllowAny]),
        name="redoc",
    ),
]


