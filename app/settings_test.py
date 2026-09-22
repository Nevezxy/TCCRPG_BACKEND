"""
Settings para RODAR A SUÍTE — no CI e na máquina de quem desenvolve.

Existe para que testar não exija um banco de produção nem credenciais reais
do Cloudinary: importa tudo de `app.settings` e troca só o que é do
ambiente de teste. Nada aqui muda o comportamento da aplicação em si, então
o que os testes exercitam continua sendo o código de produção.

    # local, rápido (SQLite em memória)
    python manage.py test --settings=app.settings_test

    # como o CI roda (PostgreSQL de verdade)
    TEST_DATABASE_URL=postgres://user:senha@localhost:5432/tccrpg \\
        python manage.py test --settings=app.settings_test

POR QUE O CI USA POSTGRESQL, E NÃO SQLITE: o SQLite IGNORA
`SELECT ... FOR UPDATE`. Toda a proteção contra corrida das compras da Loja
e do Comércio Livre (`Campanha/comercio.py`, `comprar_produto_loja`) passa
por bloqueio de linha, e no SQLite esses testes passam sem exercitar nada.
Foi assim que um `select_for_update()` combinado com `select_related` de FK
nulável chegou em produção: o PostgreSQL recusa a consulta
("FOR UPDATE cannot be applied to the nullable side of an outer join") e o
SQLite não reclamava. Rodar no mesmo banco da produção é o que fecha essa
lacuna.
"""

import os

import dj_database_url

# `app.settings` aborta sem SECRET_KEY (de propósito) e faz o parse de
# DATABASE_URL na importação — os valores abaixo só precisam existir e ser
# parseáveis; o banco de verdade é definido depois.
os.environ.setdefault("SECRET_KEY", "chave-apenas-para-testes-nao-use-em-producao")
os.environ.setdefault("DATABASE_URL", "sqlite:///nao-usado.sqlite3")

from app.settings import *  # noqa: F401,F403,E402

# --- Banco ------------------------------------------------------------------
# Sem `ssl_require`: o serviço de banco do CI (e o local) não tem TLS, e
# exigi-lo aqui impediria a conexão. Produção continua com SSL obrigatório,
# em `app/settings.py`.
_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if _TEST_DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(_TEST_DATABASE_URL)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# --- Throttling -------------------------------------------------------------
# DESLIGADO na suíte. O `UserRateThrottle` (300/min em produção) conta as
# requisições num cache de processo que NÃO é desfeito pela transação de cada
# teste — a suíte inteira divide uma cota só. Passando de 300 requisições
# autenticadas, um teste QUALQUER que rode depois recebe 429, e a falha
# aparece longe da causa: o teste de imagens da biblioteca do app Sistema
# quebrava com `KeyError: 0` porque `resposta.data` era
# `{"detail": "Request was throttled"}` em vez da lista esperada.
#
# Isso deixava a suíte a UMA requisição de quebrar: qualquer teste novo podia
# derrubar um teste alheio que ninguém tinha tocado. `Campanha/test_combate.py`
# já contornava com um `cache.clear()` no tearDown da própria classe; aqui o
# problema some para todo mundo.
#
# Anular as taxas não deixa nada sem cobertura: nenhum teste exercita o
# throttle, e a configuração de produção (`app/settings.py`) continua intacta.
# As CHAVES precisam continuar existindo (com valor None): o DRF procura a
# taxa pelo `scope` da classe, e uma chave ausente é ImproperlyConfigured,
# não "sem limite".
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"anon": None, "user": None},
}

# --- Serviços externos ------------------------------------------------------
# Sem Redis: o channel layer em memória basta, e os testes do Escudo não
# dependem de broker.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# A fila de exclusão de imagens roda na hora, sem thread — uma thread abriria
# outra conexão, que o banco de teste em memória não enxerga.
IMAGENS = {**IMAGENS, "PROCESSAMENTO_SINCRONO": True}  # noqa: F405

# O Cloudinary é mockado nos testes, mas montar a URL de um recurso exige um
# `cloud_name` configurado — sem isto, qualquer serializer com imagem
# levanta "Must supply cloud_name".
import cloudinary  # noqa: E402

cloudinary.config(cloud_name="teste", api_key="teste", api_secret="teste", secure=True)

# Hash rápido: a suíte cria muitos usuários, e o PBKDF2 padrão domina o tempo.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
