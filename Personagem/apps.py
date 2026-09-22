from django.apps import AppConfig


class PersonagemConfig(AppConfig):
    name = 'Personagem'

    def ready(self):
        # Limpeza das referências de bônus quando a entidade de origem é
        # excluída — ver `Personagem/signals.py`. Importado aqui (e não no
        # topo do módulo) porque em `ready()` os models já estão carregados.
        from . import signals  # noqa: F401
