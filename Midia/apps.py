from django.apps import AppConfig


class MidiaConfig(AppConfig):
    """
    Infraestrutura de imagens compartilhada por todos os apps (Personagem,
    Campanha, Usuario): enquadramento guardado à parte do arquivo e limpeza
    segura do Cloudinary.

    Os signals são ligados aqui, no `ready()`, porque só neste ponto todos os
    models do projeto já estão registrados — a lista de quem tem
    `CloudinaryField` é descoberta dinamicamente (ver `signals.conectar`), então
    um model novo com imagem entra na limpeza sem precisar mexer neste app.
    """

    name = "Midia"
    verbose_name = "Mídia (imagens)"

    def ready(self):
        from . import signals

        signals.conectar()
