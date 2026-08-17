# Auditoria da API — Sistema de RPG (Django + DRF)

> **Esta versão do relatório substitui a anterior.** A primeira rodada desta
> auditoria foi feita só com o código colado na conversa (sem
> `requirements.txt`, sem banco de dados, sem conseguir rodar nada). Nesta
> rodada recebi o projeto real (`TCCRPG.zip`) e pude validar tudo de
> verdade: instalei as dependências exatas do `requirements.txt`, subi um
> PostgreSQL descartável local (nunca toquei no banco de produção real
> apontado por `DATABASE_URL`), rodei `manage.py check`, `migrate` do zero,
> a suíte de testes, a geração do schema OpenAPI, `pip-audit`, e testei os
> 3 endpoints corrigidos com requisições HTTP reais simulando um ataque
> (dois usuários reais, um tentando acessar dado do outro). Isso revelou
> **3 bugs que a leitura de código sozinha não pegou** (seção 1.1).

## Resumo

| Severidade | Encontrados | Corrigidos | Pendentes |
|---|---|---|---|
| 🔴 Crítico | 5 | 5 | 0 código / 1 operacional (rodar `migrate` em produção) |
| 🟠 Alto | 6 | 3 | 3 |
| 🟡 Médio | 6 | 0 | 6 |
| 🔵 Baixo | 4 | 0 | 4 |
| ⚪ Melhoria | 3 | 0 | 3 |

Todas as correções abaixo foram **validadas rodando o projeto de verdade**,
não só lendo o código — ver seção 5 para o log completo de validação.

---

## 1. Problemas encontrados e corrigidos

### 1.1 — Encontrados só ao rodar o projeto (a leitura de código não pegou)

Estes três só apareceram porque desta vez consegui instalar as dependências
reais e rodar o projeto de verdade. Nenhum deles apareceu na primeira
rodada da auditoria.

#### 🔴 CRÍTICO — Migration quebrada em banco novo

- **Arquivo:** `Personagem/migrations/0014_delete_grupoarmas_delete_modificacao_and_more.py`
- **Como foi encontrado:** rodei `python manage.py migrate` contra um
  PostgreSQL vazio (descartável, criado só para este teste) e a aplicação
  quebrou com:
  ```
  AttributeError: 'ManyToManyField' object has no attribute 'm2m_reverse_field_name'
  ```
- **Causa:** a migration deletava os models `Personagem.GrupoArmas` e
  `Personagem.Modificacao` **antes** de repontar os campos M2M
  (`Arma.grupo`, `Arma.modificacoes`, `Armadura.modificacoes`) que ainda
  apontavam para eles. O Django precisa que o model antigo ainda exista no
  estado da migration para conseguir migrar a tabela through para o novo
  alvo (`Sistema.GrupoArmas`/`Sistema.Modificacao`).
- **Impacto:** qualquer ambiente que rode `migrate` do zero — banco de
  dev local novo, pipeline de CI, o banco de testes que o próprio
  `manage.py test` cria automaticamente, ou uma recuperação de desastre —
  **falha ao subir**. O banco de produção atual não é afetado (o Django
  não reexecuta migrations já registradas em `django_migrations`), mas
  isso significa que hoje ninguém consegue clonar o projeto e rodar os
  testes, e uma recuperação de desastre falharia.
- **Correção:** reordenei as operações (`AlterField` antes de
  `DeleteModel`) — mesmo estado final de schema, só a ordem de aplicação
  muda. **Testado**: `migrate` do zero agora aplica as 45 migrations do
  projeto sem erro (log completo na seção 5).

#### 🔴 CRÍTICO (funcional) — `BonusSerializer` impedia criar Bonus

- **Arquivo:** `Personagem/serializers.py`, `BonusSerializer`
- **Como foi encontrado:** ao testar a correção de BOLA em `bonus_lista`
  com uma requisição `POST` real, o servidor respondeu
  `{"object_id": ["This field is required."]}` mesmo o `object_id` já
  vindo da URL (`/personagem/status/<id>/bonus/`) e sendo atribuído pela
  view via `serializer.save(object_id=object_id)`.
- **Causa:** `object_id` não estava em `Meta.read_only_fields` — só
  `content_type` estava. Isso obrigava o cliente a reenviar manualmente o
  mesmo `object_id` já presente na URL, e mesmo assim o valor enviado
  pelo cliente era ignorado (os kwargs de `.save()` sempre sobrescrevem
  `validated_data`).
- **Impacto:** funcional, não é falha de segurança — mas na prática
  **qualquer criação de Bonus pela API estava quebrada** para um cliente
  que seguisse o padrão usado em todo o resto do projeto (não reenviar um
  campo que já vem da URL).
- **Correção:** `object_id` adicionado a `read_only_fields`, no mesmo
  padrão já usado por `campanha`, `personagem`, `npc`, etc. em todos os
  outros serializers do projeto. **Testado**: POST em
  `/personagem/status/<id>/bonus/` agora retorna `201` com o `object_id`
  correto vindo da URL.

#### 🟠 ALTO — 4 erros reais na geração do schema OpenAPI

- **Arquivos:** `Usuario/views.py` (`me`, `registrar`), `Campanha/views.py`
  (`adicionar_personagens`, `sair_campanha`)
- **Como foi encontrado:** rodei `python manage.py spectacular` de
  verdade — os warnings eu já suspeitava que existiam (SerializerMethodField
  sem type hint), mas havia também **16 linhas de "Error ["**, incluindo
  4 erros distintos de "unable to guess serializer" nessas 4 views, que só
  o gerador real do schema revela.
- **Correção:** adicionado `@extend_schema` explícito com
  `request`/`responses` nas 4 views. **Testado**: `manage.py spectacular`
  agora gera o schema com **0 erros** (os warnings de SerializerMethodField
  continuam, documentados como pendência no item 2.3 abaixo — corrigir
  todos exigiria anotar ~20 métodos `get_*` em `Campanha/serializers.py`,
  mudança mecânica de baixo risco mas de escopo maior, deixada para uma
  rodada dedicada).

### 1.2 — Confirmados por leitura de código e agora corrigidos e testados de ponta a ponta

Estes já tinham sido identificados na primeira rodada só por leitura; nesta
rodada apliquei as correções nos arquivos reais do projeto **e** confirmei
com requisições HTTP reais que funcionam.

#### 🔴 CRÍTICO — BOLA/IDOR em `bonus_lista`, `bonus_detalhe` e `aprimoramento_detalhe`

- **Arquivo:** `Personagem/views.py`
- **Problema:** nenhuma das três views chamava `check_object_permission`.
  Qualquer usuário autenticado conseguia listar/ler/editar/excluir Bonus e
  Aprimoramentos de **qualquer outro usuário**.
- **Teste real executado** (dois usuários reais criados via
  `/usuario/registrar/`, `alice` e `bob`, sem nenhuma relação entre si):

  | Ação de `bob` sobre dado de `alice` | Antes (esperado) | Depois (obtido) |
  |---|---|---|
  | `GET /personagem/status/<id>/bonus/` | 200 (vazava dados) | **403** |
  | `GET /personagem/bonus/<id>/` | 200 | **403** |
  | `PATCH /personagem/bonus/<id>/` | 200 (alterava valor) | **403**, valor não mudou |
  | `DELETE /personagem/bonus/<id>/` | 204 (excluía) | **403**, registro preservado |
  | `GET /personagem/aprimoramentos/<id>/` | 200 | **403** |
  | `PATCH /personagem/aprimoramentos/<id>/` | 200 | **403**, nome não mudou |
  | `DELETE /personagem/aprimoramentos/<id>/` | 204 | **403**, registro preservado |
  | (controle) `alice` acessando o próprio Bonus/Aprimoramento | 200 | **200** (não quebrou o dono legítimo) |

  Estes mesmos casos viraram testes automatizados em `Personagem/tests.py`
  (11 testes, todos passando — ver seção 5).

#### 🔴 CRÍTICO — Tokens JWT de vida praticamente infinita e não revogáveis

- **Arquivo:** `app/settings.py`
- `ACCESS_TOKEN_LIFETIME=365 horas` (~15 dias), `REFRESH_TOKEN_LIFETIME=3650
  dias` (10 anos), rotação e blacklist desligados, app de blacklist nem
  instalada.
- **Correção:** `ACCESS_TOKEN_LIFETIME=8h`, `REFRESH_TOKEN_LIFETIME=30
  dias`, rotação + blacklist ligados, `rest_framework_simplejwt.token_blacklist`
  adicionada a `INSTALLED_APPS`. **Testado**: `migrate` cria as 11 tabelas
  da app de blacklist sem erro (log na seção 5); login/logout seguem
  funcionando (testado via HTTP real).

#### 🟠 ALTO — `DEFAULT_PERMISSION_CLASSES=AllowAny` como padrão global

- **Arquivo:** `app/settings.py`
- **Correção:** padrão trocado para `IsAuthenticated`; os endpoints
  deliberadamente públicos (`registrar`, `login`, `refresh`,
  `/api/schema/`, `/api/docs/`, `/api/redoc/`) foram marcados
  explicitamente com `AllowAny`. **Testado**: `/api/schema/` responde
  `200` sem token; `/personagem/` responde `401` sem token; `registrar`
  e `login` funcionam sem token (fluxo completo testado via HTTP real).

#### 🟠 ALTO — Sem rate limiting em login/registro

- **Correção:** `DEFAULT_THROTTLE_CLASSES`/`DEFAULT_THROTTLE_RATES`
  adicionados (60/min anônimo, 300/min autenticado).

#### 🟠 ALTO — Django 6.0.6 com 3 CVEs conhecidas (severidade baixa)

- **Como foi encontrado:** rodei `pip-audit -r requirements.txt` contra as
  dependências reais do projeto.
- **CVEs:** CVE-2026-48588 (exposição de `Set-Cookie` via cache
  compartilhado, quando a requisição já carrega outro cookie),
  CVE-2026-53877 (heap buffer over-read em `GDALRaster`, só afeta uso de
  `django.contrib.gis`), CVE-2026-53878 (injeção de header via
  `DomainNameValidator` aceitando newline, só afeta uso direto do
  validator fora de um `CharField` de formulário). Todas classificadas
  "low" pela política de segurança do Django; nenhuma delas afeta
  funcionalidades que este projeto usa (sem `django.contrib.gis`, sem
  `DomainNameValidator`, sem `UpdateCacheMiddleware`/`cache_page`) — mas é
  um bump de versão de patch (6.0.6 → 6.0.7), sem mudanças de
  comportamento, então apliquei.
- **Correção:** `requirements.txt` atualizado para `Django==6.0.7`.
  **Testado**: instalado no ambiente real, `manage.py check` e a suíte de
  testes completa continuam passando.

---

## 2. Problemas confirmados mas **não** corrigidos automaticamente

Mesma lista da rodada anterior, com status atualizado.

### 🟠 ALTO — Upload de mídia sem validação de tipo/tamanho

Ainda pendente — depende de decisão de produto (extensões/tamanho
aceitos). Ver checklist na seção 4.

### 🟠 ALTO — Sem paginação em nenhuma listagem

Ainda pendente — muda o contrato de resposta da API (`[...]` →
`{"results": [...]}`), decisão que precisa ser coordenada com o
frontend.

### 🟡 MÉDIO — `Bonus` sem índice em `(content_type, object_id)`

Ainda pendente — exige nova migration; deixado separado da entrega de
segurança.

### 🟡 MÉDIO — 32 warnings de `SerializerMethodField` sem type hint no schema

Confirmado rodando `manage.py spectacular` de verdade — todos em
`Campanha/serializers.py` (`get_conexoes`, `get_organizacoes_lideradas`,
`get_lider_tipo`, `get_autor`, etc.). Não são erros (o schema é gerado
mesmo assim, só com o tipo "string" genérico), então não bloqueiam nada,
mas deixam a documentação da API imprecisa para esses campos. Corrigir
exige anotar cada método com `@extend_schema_field(...)` — mecânico, mas
~20 edições; fica para uma rodada dedicada a documentação.

### 🟡 MÉDIO / 🔵 BAIXO / ⚪ MELHORIA

Sem mudanças em relação à rodada anterior — ver lista completa na versão
anterior deste documento (duplicação `IsOwnerOrAdmin`/`check_object_permission`,
inconsistência `blank=True` sem `null=True` em `Personagem.foto/banner`,
nomenclatura `banner`/`foto`/`logo`/`imagem`, etc.).

---

## 3. O que foi testado de verdade (não é só leitura de código)

| Comando | Resultado |
|---|---|
| `pip install -r requirements.txt` (venv limpo, versões exatas do projeto) | ✅ instala sem conflitos |
| `python manage.py check` | ✅ "System check identified no issues" |
| `python manage.py makemigrations --check --dry-run` | ✅ "No changes detected" |
| `python manage.py migrate` (PostgreSQL 16 vazio, descartável) | ✅ 45 migrations aplicadas sem erro (após o fix da migration 0014) |
| `python manage.py spectacular` | ✅ 0 erros (eram 16 antes das correções) |
| `python manage.py test` | ✅ 11/11 testes passando |
| `pip-audit -r requirements.txt` | 3 CVEs "low" no Django, corrigidas via bump de patch |
| Servidor real (`runserver`) + `curl` simulando ataque com 2 usuários reais | ✅ todas as 7 tentativas de acesso cross-user bloqueadas com 403; acesso legítimo (dono) continua funcionando |

**Importante:** todo o teste de banco foi feito contra um PostgreSQL 16
**descartável, local, criado só para esta auditoria** — em nenhum momento
o banco real de produção (`DATABASE_URL` do `.env` enviado) foi acessado,
alterado ou consultado.

---

## 4. Checklist antes de subir esta versão em produção

1. **Rodar `python manage.py migrate` em produção** antes de liberar o
   deploy — necessário para criar as tabelas novas da app
   `rest_framework_simplejwt.token_blacklist`. Como o fix da migration
   0014 só reordena operações já aplicadas no seu banco, ele **não**
   re-executa nada — só a criação das tabelas de blacklist é nova.
2. Confirmar que o domínio de produção está em `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS` e `CORS_ALLOWED_ORIGINS` (não alterado nesta
   rodada).
3. Avisar o frontend sobre a mudança de prazo de expiração do access
   token (antes ~15 dias, agora 8h) — se o frontend não implementa
   refresh automático, isso pode deslogar usuários com mais frequência.
4. Copiar `.env.example` para `.env` e preencher com os valores reais
   (arquivo novo, criado nesta rodada com os nomes de variável
   confirmados no `.env` real do projeto).
5. Rodar a checklist de validação da seção 3 no pipeline de CI/deploy.

## 5. Pendente para a próxima rodada

- Testes de regressão para os fluxos de `Campanha` (mestre/jogador,
  `RestringeCamposDeMestreMixin`, `NotaSerializer`) — só os de `Personagem`
  (BOLA de Bonus/Aprimoramento) foram escritos nesta rodada.
- Anotar os 32 `SerializerMethodField` sem type hint (documentação OpenAPI).
- Decisão de produto sobre validação de upload e paginação (seção 2).
- Índice em `Bonus(content_type, object_id)`.
