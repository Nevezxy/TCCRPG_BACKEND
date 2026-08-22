# API RPG — Backend (Django + Django REST Framework)

API REST para uma ferramenta de apoio a mestres e jogadores de RPG de mesa:
gerenciamento de campanhas, personagens, NPCs, locais, organizações, mapas,
sessões, missões, eventos e notas colaborativas, com um sistema de fichas
customizável por "Sistema" de jogo (D&D, sistema próprio, etc.).

> Este README foi escrito a partir do código-fonte real do projeto
> (models, views, serializers, urls, settings, migrations). Não descreve
> nenhum endpoint ou comportamento que não exista no código.

## Sumário

- [Tecnologias](#tecnologias)
- [Arquitetura](#arquitetura)
- [Estrutura de diretórios](#estrutura-de-diretórios)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Banco de dados e migrations](#banco-de-dados-e-migrations)
- [Execução local](#execução-local)
- [Autenticação](#autenticação)
- [Principais endpoints](#principais-endpoints)
- [Documentação da API](#documentação-da-api)
- [Upload de mídia (Cloudinary)](#upload-de-mídia-cloudinary)
- [Testes](#testes)
- [Deploy](#deploy)
- [Troubleshooting](#troubleshooting)

## Tecnologias

- **Python / Django 6.0.6**
- **Django REST Framework** — API REST
- **djangorestframework-simplejwt** — autenticação via JWT (access + refresh)
- **drf-spectacular** — geração de schema OpenAPI 3 + Swagger UI + Redoc
- **PostgreSQL** (via `dj-database-url`) — banco de dados em produção
- **Cloudinary** (`cloudinary`, `django-cloudinary-storage`) — armazenamento de imagens/mídia
- **django-cors-headers** — CORS
- **WhiteNoise** — servir arquivos estáticos em produção
- **Gunicorn** — servidor WSGI de produção
- **python-dotenv** — carregamento de variáveis de ambiente a partir de `.env` em desenvolvimento

## Arquitetura

O projeto é dividido em 4 apps Django, cada um com um domínio bem definido:

| App | Responsabilidade |
|---|---|
| `Usuario` | Usuário customizado (`AbstractUser`), registro, login/refresh JWT, endpoint `me`, e a permission central `IsOwnerOrAdmin` usada por todo o projeto |
| `Personagem` | Fichas de personagem e todos os seus sub-recursos: Atributos, Status, Defesas, Perícias, Itens, Armas, Armaduras, Técnicas, Poderes, Habilidades, Aprimoramentos e Bônus (genéricos, via `GenericForeignKey`) |
| `Sistema` | Biblioteca "de regras" reaproveitável entre campanhas: Poderes, Habilidades, Itens, Armas, Armaduras, Modificações, Grupos de Armas e Regras de um sistema de jogo — com endpoints de "copiar para personagem" |
| `Campanha` | Camada de mesa: Campanha, NPCs (com relações entre si), Locais, Organizações (com membros), Mapas, Sessões, Missões, Eventos e Notas (anotações genéricas anexáveis a quase qualquer objeto do domínio) |

Padrões usados de forma consistente no projeto:

- **Autorização centralizada**: `Usuario/permissions.py::IsOwnerOrAdmin` implementa uma única regra de `has_object_permission` capaz de resolver, a partir de *qualquer* objeto do domínio, a quem ele pertence (personagem → usuário; NPC/Local/Organização/... → campanha → mestre/jogadores) e aplicar a regra correta: mestre tem acesso total; jogador só lê se `visivel_para_jogadores`; jogador só edita se também `editavel_para_jogadores`; exclusão é sempre exclusiva do mestre.
- **Views baseadas em função** (`@api_view`) em vez de `ViewSet`/`generics`, com padrão de lista aninhada em URL (`/campanha/<id>/npcs/`) e detalhe "achatado" (`/campanha/npcs/<npc_pk>/`).
- **Serializers com `Meta.read_only_fields`** para impedir mass assignment de campos como `usuario`, `campanha`, `codigo`, `criado_em`/`atualizado_em` — a propriedade "dona" de cada recurso é sempre atribuída pela view a partir da URL, nunca aceita do corpo da requisição.
- **`RestringeCamposDeMestreMixin`** (`Campanha/serializers.py`): garante que os campos `visivel_para_jogadores`/`editavel_para_jogadores` só possam ser alterados pelo mestre da campanha, mesmo em um PATCH que o jogador tenha permissão de fazer por outro motivo.
- **`CloudinaryUrlSerializerMixin`**: converte os `CloudinaryField` em URL completa na resposta, mantendo o campo gravável na entrada.
- **Notas genéricas**: `Nota` usa `GenericForeignKey` com uma allowlist explícita de modelos anotáveis (`Campanha`, `NPC`, `Local`, `Organizacao`, `Mapa`, `Sessao`, `Missao`, `Evento`, `Personagem`), evitando que qualquer `ContentType` do projeto seja referenciável.

## Estrutura de diretórios

```
.
├── app/                    # Configuração do projeto Django
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── Usuario/                 # Usuário customizado, auth, permission central
│   ├── models.py
│   ├── permissions.py       # IsOwnerOrAdmin
│   ├── utils.py             # check_object_permission / pode_criar_ou_excluir
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── Personagem/               # Fichas de personagem e sub-recursos
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── utils.py              # criação de dados iniciais (modelos "dnd"/"tcc")
│   └── urls.py
├── Sistema/                   # Biblioteca de regras por sistema de jogo
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── Campanha/                   # Campanhas, NPCs, Locais, Organizações, Notas...
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── docs/
│   └── AUDIT.md              # Relatório de auditoria do projeto
├── manage.py
├── build.sh                  # Script de build usado no deploy (Render)
├── render.yaml                # Configuração de serviço do Render
└── schema.yaml                # Schema OpenAPI gerado (drf-spectacular)
```

## Requisitos

- Python 3.11+ (recomendado, compatível com Django 6.0)
- PostgreSQL (produção). Em desenvolvimento local sem Postgres, é possível
  usar SQLite descomentando o bloco correspondente em `app/settings.py` e
  ajustando `DATABASES` — mas note que o projeto usa `dj_database_url.parse`
  sobre `DATABASE_URL` por padrão.
- Conta Cloudinary (para upload de imagens/mídia — banners, fotos de
  personagem/NPC, mapas, etc.)

## Instalação

```bash
git clone <url-do-repositorio>
cd <pasta-do-projeto>

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## Variáveis de ambiente

O projeto carrega variáveis de um arquivo `.env` na raiz (via `python-dotenv`,
ver `app/settings.py`). As variáveis usadas no código são:

| Variável | Usada em | Obrigatória | Descrição |
|---|---|---|---|
| `SECRET_KEY` | `app/settings.py` | **Sim** | Chave secreta do Django. A aplicação falha na inicialização se estiver ausente. |
| `DEBUG` | `app/settings.py` | Não (padrão `False`) | Definir literalmente como a string `True` para ativar modo debug. Qualquer outro valor (inclusive ausente) resulta em `False`. |
| `DATABASE_URL` | `app/settings.py` | **Sim** | URL de conexão do PostgreSQL no formato `postgres://usuario:senha@host:porta/nome_do_banco` (parseada por `dj_database_url`, com `ssl_require=True`). |
| `CLOUDINARY_CLOUD_NAME` | `app/settings.py` | Sim (se for usar upload de mídia) | Nome do cloud Cloudinary. |
| `CLOUDINARY_API_KEY` | `app/settings.py` | Sim | Chave de API do Cloudinary. |
| `CLOUDINARY_API_SECRET` | `app/settings.py` | Sim | Segredo de API do Cloudinary. |

Exemplo de `.env` local (**nunca** commitar um `.env` real — `.gitignore`
já exclui `.env` e `.env.*`, exceto `.env.example`):

```dotenv
SECRET_KEY=troque-por-uma-chave-secreta-longa-e-aleatoria
DEBUG=True
DATABASE_URL=postgres://usuario:senha@localhost:5432/rpg_db
CLOUDINARY_CLOUD_NAME=seu-cloud-name
CLOUDINARY_API_KEY=sua-api-key
CLOUDINARY_API_SECRET=sua-api-secret
```

> Um `.env.example` com estes mesmos nomes (sem valores reais) está na raiz
> do repositório — copie-o para `.env` e preencha com valores reais.

## Banco de dados e migrations

O projeto usa PostgreSQL em produção (`ssl_require=True`, então bancos locais
sem SSL configurado podem precisar ajustar essa flag para desenvolvimento).

```bash
# Aplicar todas as migrations
python manage.py migrate

# Criar um superusuário (necessário para acessar /admin/)
python manage.py createsuperuser

# Após alterar models, gerar novas migrations
python manage.py makemigrations
```

Cada app (`Campanha`, `Personagem`, `Sistema`, `Usuario`) mantém seu próprio
histórico de migrations em `<app>/migrations/`.

## Execução local

```bash
python manage.py runserver
```

A API sobe em `http://127.0.0.1:8000/` por padrão — esse endereço já está
declarado como servidor local no schema OpenAPI (`SPECTACULAR_SETTINGS`).

CORS está liberado (`CORS_ALLOW_CREDENTIALS=True`) para os seguintes
origins de desenvolvimento, entre outros de produção (ver
`CORS_ALLOWED_ORIGINS` em `app/settings.py`):

- `http://localhost:5173` / `http://127.0.0.1:5173` (Vite)
- `http://localhost:8080`
- `http://localhost:5500`

## Autenticação

Autenticação via **JWT** (`djangorestframework-simplejwt`), com os
seguintes endpoints (prefixo `/usuario/`):

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/usuario/registrar/` | Cria um novo usuário (`username`, `email`, `password`, `first_name`, `last_name`). Público. |
| `POST` | `/usuario/login/` | Troca `username`/`password` por par de tokens `access`/`refresh`. Público. |
| `POST` | `/usuario/refresh/` | Troca um `refresh` token válido por um novo `access` token. Público. |
| `GET` | `/usuario/me/` | Retorna os dados do usuário autenticado. Requer autenticação. |

Todas as demais rotas do projeto exigem o header:

```
Authorization: Bearer <access_token>
```

## Principais endpoints

Todos os endpoints abaixo (exceto os de autenticação, listados acima)
exigem usuário autenticado.

### Personagens (`/personagem/`)

- `GET|POST /personagem/` — listar/criar personagens do usuário logado (superusuário vê todos)
- `GET|PUT|PATCH|DELETE /personagem/<id>/`
- Sub-recursos aninhados por personagem, todos no padrão `GET|POST /personagem/<personagem_id>/<recurso>/` + `GET|PUT|PATCH|DELETE /personagem/<recurso>/<id>/`:
  `status/`, `atributos/`, `defesas/`, `pericias/`, `itens/`, `arma/`, `armadura/`, `tecnicas/`, `poderes/`, `habilidades/`
- `GET|POST /personagem/habilidades/<habilidade_id>/aprimoramentos/` + `GET|PUT|PATCH|DELETE /personagem/aprimoramentos/<id>/`
- Bônus genéricos (aplicáveis a qualquer sub-recurso do personagem): `GET|POST /personagem/<tipo>/<object_id>/bonus/` + `GET|PUT|PATCH|DELETE /personagem/bonus/<id>/`, onde `<tipo>` é um de: `status`, `atributo`, `defesa`, `pericia`, `item`, `arma`, `armadura`, `tecnica`, `poder`, `habilidade`.

### Sistema (`/sistema/`)

- `GET /sistema/` — listar sistemas de jogo disponíveis
- `GET /sistema/<sistema_id>/{regras|poderes|itens|armas|armaduras|habilidades}/`
- `GET /sistema/modificacoes/` e `GET /sistema/grupos-armas/` (não filtrados por sistema)
- Endpoints de cópia para a ficha de um personagem: `POST /sistema/personagens/<personagem_id>/{poderes|itens|armas|armaduras|habilidades}/<id>/copiar/`

### Campanha (`/campanha/`)

- `GET|POST /campanha/` — listar/criar campanhas (mestre ou jogador)
- `GET|PUT|PATCH|DELETE /campanha/<id>/`
- `POST /campanha/entrar/` — entrar em uma campanha por código de convite
- `POST /campanha/<id>/sair/` — sair de uma campanha (mestre não pode sair)
- `POST /campanha/<id>/personagens/` — vincular personagens próprios à campanha
- `GET /campanha/<id>/personagens-disponiveis/`
- `DELETE /campanha/<id>/personagens/<personagem_pk>/`
- Recursos "de mundo", todos com o padrão lista aninhada / detalhe achatado, e todos com os campos `visivel_para_jogadores`/`editavel_para_jogadores` controlando o que jogadores enxergam e podem editar:
  - `<id>/npcs/` + `npcs/<npc_pk>/`, com relações: `npcs/<npc_pk>/relacoes/` + `relacoes-npc/<relacao_pk>/`
  - `<id>/locais/` + `locais/<local_pk>/`
  - `<id>/organizacoes/` + `organizacoes/<organizacao_pk>/`, com membros: `organizacoes/<organizacao_pk>/membros/` + `membros-organizacao/<membro_pk>/`
  - `<id>/mapas/` + `mapas/<mapa_pk>/`
  - `<id>/sessoes/` + `sessoes/<sessao_pk>/`
  - `<id>/missoes/` + `missoes/<missao_pk>/`
  - `<id>/eventos/` + `eventos/<evento_pk>/`
- Notas (anexáveis a quase qualquer objeto acima, via `content_type`/`object_id`): `GET|POST /campanha/notas/` (filtros via querystring: `?content_type=<tipo>&object_id=<id>` ou `?campanha=<id>`) + `GET|PUT|PATCH|DELETE /campanha/notas/<id>/`

## Documentação da API

Gerada automaticamente por `drf-spectacular`:

- **Schema OpenAPI 3 (JSON/YAML)**: `GET /api/schema/`
- **Swagger UI**: `GET /api/docs/`
- **Redoc**: `GET /api/redoc/`

Uma cópia estática do schema também é versionada em `schema.yaml` na raiz
do projeto (útil para diffs e para clientes que geram código a partir do
schema).

## Upload de mídia (Cloudinary)

Todos os campos de imagem/mídia do projeto (`Campanha.banner`,
`Personagem.foto/banner`, `NPC.foto`, `Local.imagem`, `Organizacao.logo`,
`Mapa.imagem`, `Sessao.imagem`, `Missao.imagem`, `Evento.imagem`,
`Item.foto`, `Tecnica.midia`, `Poder.midia`) usam `CloudinaryField` e são
enviados diretamente para o Cloudinary configurado pelas variáveis
`CLOUDINARY_*`. Os serializers convertem esses campos para a URL completa
na resposta (`CloudinaryUrlSerializerMixin`), mas continuam graváveis na
entrada.

> Ver `docs/AUDIT.md` para uma observação de segurança pendente sobre
> validação de tipo/tamanho de arquivo nesses campos.

## Testes

```bash
python manage.py test
```

O app `Personagem` tem uma suíte de testes de regressão (`Personagem/tests.py`,
11 casos) cobrindo especificamente as permissões de `Bonus` e
`Aprimoramento` — os dois pontos onde a auditoria encontrou falhas de
controle de acesso entre usuários (ver `docs/AUDIT.md`). Os demais apps
(`Campanha`, `Sistema`, `Usuario`) ainda não têm testes implementados; ver
`docs/AUDIT.md`, seção "Pendente para a próxima rodada", para os próximos
casos recomendados.

## Deploy

O projeto está configurado para deploy no **Render** (`render.yaml`):

```yaml
services:
  - type: web
    name: minha-api-django
    runtime: python
    buildCommand: "./build.sh"
    startCommand: "gunicorn app.wsgi:application"
```

`build.sh` executa, nesta ordem:

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
```
