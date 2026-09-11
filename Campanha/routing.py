from django.urls import path

from .consumers import EscudoConsumer

websocket_urlpatterns = [
    path("ws/campanha/<int:pk>/escudo/", EscudoConsumer.as_asgi()),
]
