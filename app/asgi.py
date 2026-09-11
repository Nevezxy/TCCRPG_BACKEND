"""
ASGI config for app project.

Ponto de entrada do servidor em produção (Daphne): atende HTTP (a API REST
de sempre, pelas mesmas views) e WebSocket (sincronização do Escudo do
Mestre, ver `Campanha/consumers.py`) no mesmo processo e na mesma porta.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

# Precisa vir ANTES de importar qualquer coisa que toque em models (o
# roteamento importa os consumers): é aqui que o Django é inicializado.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from Campanha.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # A autenticação do WebSocket é por token (não por cookie), então um
        # site de terceiros não teria como sequestrar a conexão de ninguém;
        # validar a origem com a MESMA lista do CORS é defesa em profundidade.
        "websocket": OriginValidator(URLRouter(websocket_urlpatterns), settings.CORS_ALLOWED_ORIGINS),
    }
)
