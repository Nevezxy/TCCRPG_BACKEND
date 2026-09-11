from django.apps import AppConfig


class CampanhaConfig(AppConfig):
    name = 'Campanha'

    def ready(self):
        # Sincronização em tempo real do Escudo do Mestre (ver signals.py).
        from . import signals

        signals.conectar()
