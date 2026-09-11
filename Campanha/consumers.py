"""
WebSocket do Escudo do Mestre: `ws/campanha/<pk>/escudo/`.

Só EMPURRA eventos (ver `escudo.py`/`signals.py`); a carga inicial continua
sendo REST (GET /campanha/<pk>/escudo/), feita pelo cliente depois do
`pronto`. Nada de dado trafega aqui antes de o usuário estar autorizado.

AUTENTICAÇÃO PELA PRIMEIRA MENSAGEM, e não pela URL: o navegador não deixa
um WebSocket enviar o header `Authorization`, e um token na query string
acaba em log de acesso de proxy/servidor. O cliente conecta e manda
`{"tipo": "auth", "token": "<access JWT>"}`; sem isso em
`PRAZO_AUTENTICACAO` segundos, a conexão é fechada.

Códigos de fechamento (o cliente decide o que fazer com cada um):
  4401 token ausente/inválido/expirado → renovar o token e reconectar
  4403 não participa da campanha (ou deixou de participar) → não reconectar
  4404 campanha não existe (ou foi excluída) → não reconectar

O keepalive de rede é o ping de protocolo do próprio servidor ASGI (Daphne);
o `ping` de aplicação abaixo existe só para o CLIENTE detectar uma conexão
meio-aberta (Wi-Fi que caiu sem o TCP perceber), que o navegador não expõe.
"""

import asyncio
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken

from . import escudo
from .models import Campanha

PRAZO_AUTENTICACAO = 10  # segundos

FECHA_NAO_AUTENTICADO = 4401
FECHA_PROIBIDO = 4403
FECHA_NAO_ENCONTRADO = 4404


@database_sync_to_async
def _autorizar(user_id, campanha_id):
    """Mesma regra de `_busca_campanha_do_participante` (views.py): mestre,
    jogador ou superuser. Devolve o código de fechamento ou None se ok."""
    usuario = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if usuario is None:
        return FECHA_NAO_AUTENTICADO
    campanha = Campanha.objects.filter(pk=campanha_id).only("id", "mestre_id").first()
    if campanha is None:
        return FECHA_NAO_ENCONTRADO
    if usuario.is_superuser or campanha.mestre_id == usuario.pk:
        return None
    if campanha.jogadores.filter(pk=usuario.pk).exists():
        return None
    return FECHA_PROIBIDO


class EscudoConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self.campanha_id = int(self.scope["url_route"]["kwargs"]["pk"])
        self.grupo = escudo.nome_grupo(self.campanha_id)
        self.user_id = None
        self.inscrito = False
        await self.accept()
        self._prazo = asyncio.get_running_loop().call_later(PRAZO_AUTENTICACAO, self._expirou_prazo)

    def _expirou_prazo(self):
        if self.user_id is None:
            asyncio.ensure_future(self.close(code=FECHA_NAO_AUTENTICADO))

    async def disconnect(self, code):
        prazo = getattr(self, "_prazo", None)
        if prazo is not None:
            prazo.cancel()
        if getattr(self, "inscrito", False):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)
            self.inscrito = False

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        # O único formato aceito é um objeto JSON pequeno em texto. Frame
        # binário ou JSON inválido é ignorado em vez de derrubar o consumer
        # com traceback no log (o padrão do AsyncJsonWebsocketConsumer).
        if text_data is None or len(text_data) > 4096:
            return
        try:
            content = json.loads(text_data)
        except ValueError:
            return
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        tipo = content.get("tipo")

        if tipo == "ping":
            if self.inscrito:
                # O channel layer expira a inscrição num grupo depois de
                # `group_expiry` (1 dia por padrão) — uma sessão aberta mais
                # que isso deixaria de receber eventos sem aviso. Renovar a
                # cada ping (≈30s) custa um ZADD no Redis e mantém a
                # inscrição viva enquanto a conexão estiver.
                await self.channel_layer.group_add(self.grupo, self.channel_name)
            await self.send_json({"tipo": "pong"})
            return

        if tipo != "auth" or self.user_id is not None:
            return

        try:
            token = AccessToken(str(content.get("token") or ""))
            user_id = token[jwt_settings.USER_ID_CLAIM]
        except (TokenError, KeyError):
            await self.close(code=FECHA_NAO_AUTENTICADO)
            return

        erro = await _autorizar(user_id, self.campanha_id)
        if erro is not None:
            await self.close(code=erro)
            return

        self.user_id = int(user_id)
        self._prazo.cancel()
        # Inscreve ANTES de responder `pronto`: o cliente só pede o snapshot
        # depois do `pronto`, então qualquer gravação confirmada a partir
        # daqui chega como evento — não existe janela em que uma mudança
        # fique fora tanto do snapshot quanto do fluxo de eventos.
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        self.inscrito = True
        await self.send_json({"tipo": "pronto"})

    async def escudo_evento(self, mensagem):
        evento = mensagem["evento"]
        tipo = evento.get("tipo")
        if tipo == "acesso_revogado":
            if self.user_id in evento.get("usuarios", ()):
                await self.close(code=FECHA_PROIBIDO)
            return
        if tipo == "campanha_removida":
            await self.close(code=FECHA_NAO_ENCONTRADO)
            return
        await self.send_json(evento)
