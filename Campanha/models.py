import random
import string

from django.db import models
from django.core.exceptions import ValidationError

from Personagem.models import Personagem
from Sistema.models import Sistema
from app import settings
from cloudinary.models import CloudinaryField

from django.db.models import Q

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Campanha(models.Model):
    mestre = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campanhas_criadas")
    jogadores = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="campanhas", blank=True)
    personagens = models.ManyToManyField(Personagem, related_name="campanhas", blank=True)
    
    banner = CloudinaryField("Banner", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)

    descricao = models.TextField(blank=True)
    anotacoes = models.TextField(blank=True)

    codigo = models.CharField(max_length=5, unique=True, editable=False, db_index=True)

    # `sistema` (FK) continua existindo como o sistema PRINCIPAL da campanha
    # — é o que campanhas antigas já têm gravado e o que o resto do app usa
    # quando precisa de UM sistema só (ex.: features de `systemConfig`).
    # `sistemas` (M2M) é a lista completa de bibliotecas de regras em uso:
    # uma mesa pode combinar "Tormenta" + "homebrew da casa" + "suplemento X".
    # Os dois são mantidos em sincronia pelo serializer (ver
    # CampanhaSerializer.sincroniza_sistemas) para não quebrar nada que ainda
    # lê `sistema`; a migration 0013 popula `sistemas` a partir de `sistema`.
    sistema = models.ForeignKey(Sistema, on_delete=models.SET_NULL, related_name='campanhas', blank=True, null=True)

    sistemas = models.ManyToManyField(Sistema, related_name='campanhas_bibliotecas', blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):

        if not self.codigo:

            while True:
                codigo = ''.join(
                    random.choices(
                        string.ascii_uppercase + string.digits,
                        k=5
                    )
                )

                if not Campanha.objects.filter(codigo=codigo).exists():
                    self.codigo = codigo
                    break

        super().save(*args, **kwargs)

class NPC(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="npcs")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="npcs"
    )

    foto = CloudinaryField("Foto", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    apelido = models.CharField(max_length=200, blank=True, db_index=True)
    idade = models.PositiveIntegerField(blank=True, null=True)

    estado_atual = models.CharField(max_length=200, choices=[
        ("vivo", "Vivo"),
        ("morto", "Morto"),
        ("desaparecido", "Desaparecido"),
    ], blank=True)

    # Campo unificado de conteúdo narrativo, em Markdown puro. Substitui os
    # antigos TextFields narrativos (aparencia, personalidade, familia,
    # maior_desejo, maior_prazer, peculiaridade, ocupacao, status_social,
    # segredo, anotacoes) — migrados para cá pela migration de dados 0008.
    conteudo = models.TextField(blank=True)

    localizacao = models.ForeignKey('Local', on_delete=models.SET_NULL, null=True, blank=True, related_name="npcs_localizados")
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)
    
    ficha = models.JSONField(blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome

# RelacaoNPC foi removido (substituído por Conexao — ver migrations
# 0008/0009). O acesso às conexões de um NPC passa a ser via
# `Conexao.objects.filter(...)` (ver serializers.py/views.py) em vez dos
# antigos related_names `relacoes`/`relacoes_com_outros_npcs`.

class Local(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="locais")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="locais"
    )

    imagem = CloudinaryField("Imagem", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    nivel_perigo = models.IntegerField(blank=True, null=True)
    status_atual = models.CharField(max_length=200, choices=[
        ("ativo", "Ativo"),
        ("abandonado", "Abandonado"),
        ("destruido", "Destruído"),
    ], blank=True)

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome
    
class Organizacao(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="organizacoes"
    )

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="organizacoes"
    )

    logo = CloudinaryField("Logo", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)

    lider_npc = models.ForeignKey(
        NPC,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizacoes_lideradas"
    )

    lider_personagem = models.ForeignKey(
        Personagem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizacoes_lideradas"
    )

    sede = models.ForeignKey(
        Local,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizacoes_sede"
    )

    status_atual = models.CharField(
        max_length=20,
        choices=[
            ("ativa", "Ativa"),
            ("inativa", "Inativa"),
            ("destruida", "Destruída"),
        ],
        blank=True,
    )

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def lider(self):
        return self.lider_personagem or self.lider_npc

    def __str__(self):
        return self.nome

    class Meta:
        ordering = ["nome"]

        constraints = [
            # No máximo um líder — mas pode não ter nenhum ainda (a
            # Organização nasce sem líder, na criação rápida do frontend,
            # e o mestre define depois na página dedicada). Antes exigia
            # exatamente um, o que travava a criação de qualquer
            # Organização pelo frontend.
            models.CheckConstraint(
                condition=~(
                    Q(lider_personagem__isnull=False) &
                    Q(lider_npc__isnull=False)
                ),
                name="organizacao_um_unico_lider",
            ),

            # Nome único dentro da campanha
            models.UniqueConstraint(
                fields=["campanha", "nome"],
                name="organizacao_nome_unico_por_campanha",
            ),
        ]

        indexes = [
            models.Index(fields=["campanha", "nome"]),
        ]
    
    
class Mapa(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="mapas")
    local = models.ForeignKey(Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="mapas")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="mapas"
    )

    imagem = CloudinaryField("Imagem", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    tipo = models.CharField(max_length=200)
    largura = models.PositiveIntegerField(blank=True, null=True)
    altura = models.PositiveIntegerField(blank=True, null=True)

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome
    
class Sessao(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="sessoes")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="sessoes"
    )

    numero = models.PositiveIntegerField()
    titulo = models.CharField(max_length=200, db_index=True)
    data = models.DateTimeField()

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
class Missao(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="missoes")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="missoes"
    )

    titulo = models.CharField(max_length=200, db_index=True)
    status = models.CharField(max_length=200, choices=[
        ("ativa", "Ativa"),
        ("concluida", "Concluída"),
        ("falha", "Falha"),
    ], blank=True)
    dificuldade = models.PositiveIntegerField(blank=True, null=True)
    local = models.ForeignKey(Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="missoes")

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
class Evento(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="eventos")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos"
    )

    titulo = models.CharField(max_length=200, db_index=True)
    data = models.CharField(max_length=200, blank=True)
    locais = models.ManyToManyField(Local, blank=True, related_name="eventos")
    organizacoes = models.ManyToManyField(Organizacao, blank=True, related_name="eventos")

    # Ver nota equivalente em NPC.conteudo.
    conteudo = models.TextField(blank=True)
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
class Nota(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notas"
    )

    personagem = models.ForeignKey(
        Personagem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notas_como_personagem"
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE
    )

    object_id = models.PositiveIntegerField()

    objeto = GenericForeignKey(
        "content_type",
        "object_id"
    )

    titulo = models.CharField(max_length=200, blank=True)

    conteudo = models.TextField()

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo or f"Nota #{self.pk}"

    class Meta:
        ordering = ["-atualizado_em"]


# ---------------------------------------------------------------------------
# Pasta — organização em árvore (estilo Obsidian) dos "documentos" de uma
# Campanha. Cada entidade organizável (NPC, Local, Organizacao, Mapa,
# Sessao, Missao, Evento) tem uma FK direta para Pasta (ver campo `pasta`
# em cada model acima) em vez de uma tabela de ligação genérica — decisão
# explícita do escopo desta refatoração.
# ---------------------------------------------------------------------------

class Pasta(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="pastas"
    )

    nome = models.CharField(max_length=200)

    pasta_pai = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subpastas"
    )
    
    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone (ex.: 'folder', 'folder-open', 'file-text').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome

    class Meta:
        ordering = ["ordem", "nome"]

        constraints = [
            # Duas subpastas (ou duas pastas-raiz) da mesma campanha não
            # podem ter o mesmo nome sob o mesmo pai — evita ambiguidade
            # na árvore, no mesmo espírito do Obsidian.
            models.UniqueConstraint(
                fields=["campanha", "pasta_pai", "nome"],
                name="pasta_nome_unico_por_pai"
            ),
        ]

        indexes = [
            models.Index(fields=["campanha", "pasta_pai"]),
        ]


# ---------------------------------------------------------------------------
# Conexao / TipoConexao — relacionamento genérico entre quaisquer duas
# entidades de uma mesma Campanha, via ContentType + GenericForeignKey.
# Substitui RelacaoNPC e MembroOrganizacao (ver migrations 0008/0009: os
# dados existentes desses dois models são migrados para Conexao antes de
# serem removidos). Também é a base pensada para os futuros backlinks
# estilo Obsidian/Worldcraft (ver `conteudo` em Markdown + `[[wiki-links]]`
# futuros referenciando estas mesmas entidades).
# ---------------------------------------------------------------------------

class TipoConexao(models.Model):
    """
    Vocabulário de tipos de conexão (ex.: "Filho de", "Membro de", "Amigo
    de"). Não é escopado por Campanha — é um vocabulário compartilhado
    entre todas as campanhas, como uma lista de "verbos" reutilizáveis.

    `inverso` permite cadastrar o par orientado (ex.: "Filho de" ↔ "Mãe
    de"), mas a criação da Conexao inversa correspondente NÃO é automática
    (ver TipoConexaoSerializer/ConexaoSerializer): o sistema não trata toda
    conexão como bidirecional.
    """
    nome = models.CharField(max_length=100, unique=True)

    inverso = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tipos_inversos"
    )

    descricao = models.TextField(blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

    class Meta:
        ordering = ["nome"]
        verbose_name = "Tipo de Conexão"
        verbose_name_plural = "Tipos de Conexão"


# Modelos que podem participar de uma Conexao (allowlist — mesma lógica de
# segurança de `_MODELOS_NOTAVEIS` em serializers.py: sem isso, qualquer
# content_type do projeto, inclusive de outros apps, poderia ser
# referenciado). Definida aqui (e não em serializers.py) porque também é
# usada pela validação de campanha em `Conexao.clean()`.
def modelos_conectaveis():
    """
    Import tardio para evitar import circular com Personagem (Personagem
    não importa Campanha, mas é mais seguro resolver isso em tempo de uso
    do que em tempo de definição do módulo).
    """
    from Personagem.models import Personagem as _Personagem

    return [
        NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento,
        Documento, Imagem, Canva, Criatura, Divindade, Raca,
        _Personagem,
    ]


class Conexao(models.Model):
    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="conexoes"
    )

    entidade1_tipo = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+"
    )

    entidade1_id = models.PositiveIntegerField()

    entidade1 = GenericForeignKey(
        "entidade1_tipo",
        "entidade1_id"
    )

    entidade2_tipo = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+"
    )

    entidade2_id = models.PositiveIntegerField()

    entidade2 = GenericForeignKey(
        "entidade2_tipo",
        "entidade2_id"
    )

    tipo = models.ForeignKey(
        TipoConexao,
        on_delete=models.PROTECT,
        related_name="conexoes"
    )

    # Markdown livre — ex.: o antigo `cargo` de MembroOrganizacao vira
    # "## Cargo\n\nBibliotecário" aqui (ver migration de dados 0008).
    descricao = models.TextField(blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.entidade1} → {self.tipo.nome} → {self.entidade2}"

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Conexão"
        verbose_name_plural = "Conexões"

        constraints = [
            # Uma entidade não pode se conectar a si mesma.
            models.CheckConstraint(
                condition=~(
                    Q(entidade1_tipo=models.F("entidade2_tipo")) &
                    Q(entidade1_id=models.F("entidade2_id"))
                ),
                name="conexao_entidades_diferentes"
            ),

            # Evita duplicar a MESMA conexão (mesma origem, mesmo destino,
            # mesmo tipo) mais de uma vez.
            models.UniqueConstraint(
                fields=[
                    "entidade1_tipo", "entidade1_id",
                    "entidade2_tipo", "entidade2_id",
                    "tipo",
                ],
                name="conexao_unica_por_tipo"
            ),
        ]

        indexes = [
            models.Index(fields=["campanha"]),
            models.Index(fields=["entidade1_tipo", "entidade1_id"]),
            models.Index(fields=["entidade2_tipo", "entidade2_id"]),
        ]

# ---------------------------------------------------------------------------
# EntidadeMundo — base ABSTRATA das entidades de mundo criadas a partir daqui
# (Documento, Imagem, Canva, Criatura, Divindade, Raca).
#
# Os 7 models originais (NPC, Local, Organizacao, Mapa, Sessao, Missao,
# Evento) repetem, um a um, exatamente este mesmo bloco de campos. A base
# existe para que as entidades NOVAS não continuem multiplicando essa
# repetição — e para que qualquer campo comum futuro entre em um lugar só.
#
# Por que os models antigos NÃO foram migrados para cá: `abstract = True`
# gera exatamente as mesmas colunas, então a mudança seria cosmética no
# banco, mas obrigaria a reescrever 7 models já em produção (com risco de
# `AlterField` desnecessário em campanhas existentes) sem ganho funcional
# nenhum. A compatibilidade vem antes da simetria — ver seção 10 da tarefa.
#
# `campanha`/`pasta` ficam nos models CONCRETOS porque o `related_name`
# precisa do plural correto em português (`imagens`, não o `imagems` que
# `%(class)ss` produziria na base abstrata).
# ---------------------------------------------------------------------------

TAMANHO_CHOICES = [
    ("minusculo", "Minúsculo"),
    ("pequeno", "Pequeno"),
    ("medio", "Médio"),
    ("grande", "Grande"),
    ("enorme", "Enorme"),
    ("colossal", "Colossal"),
]


class EntidadeMundo(models.Model):

    nome = models.CharField(max_length=200, db_index=True)

    # Mesmo campo Markdown único das demais entidades (ver nota em NPC.conteudo).
    conteudo = models.TextField(blank=True)

    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'user', 'map-pin').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)

    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        # Diferente dos models antigos (ordenados só por nome nas views), as
        # entidades novas já nascem respeitando o campo `ordem`, com o nome
        # como desempate estável.
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Documento(EntidadeMundo):
    """
    Documento "in-fiction" da campanha: cartas, contratos, diários, panfletos,
    profecias. Diferente de Nota (que é um comentário PESSOAL de um
    participante sobre outro objeto), o Documento é uma entidade de mundo
    completa — tem pasta, ícone, cor, visibilidade e conteúdo em Markdown.
    """

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="documentos")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos"
    )

    imagem = CloudinaryField("Imagem", blank=True, null=True)

    tipo = models.CharField(max_length=100, blank=True, help_text="Ex.: Carta, Contrato, Diário, Profecia.")
    autor = models.CharField(max_length=200, blank=True, help_text="Quem escreveu o documento dentro da ficção.")
    data = models.CharField(max_length=200, blank=True, help_text="Data in-fiction (texto livre).")

    local = models.ForeignKey(
        Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos"
    )

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"


class Imagem(EntidadeMundo):
    """
    Imagem reutilizável da campanha. Além de ser uma entidade de mundo como
    as outras, é o alvo das REFERÊNCIAS de imagem no Markdown: qualquer
    entidade pode escrever `![[Nome da Imagem]]` no `conteudo` e o frontend
    resolve isso contra esta tabela (ver o endpoint
    `GET /campanha/<pk>/imagens/referencias/` em views.py), sem exigir um
    novo upload do mesmo arquivo.

    Consequências dessa escolha, todas intencionais:
      - PERMISSÃO: o endpoint de referências aplica a MESMA regra de
        visibilidade das listagens (`visivel_para_jogadores`), então uma
        imagem escondida do jogador não entra no índice dele e a referência
        aparece como "imagem não encontrada" — a URL do arquivo nunca é
        enviada para quem não pode vê-la.
      - EXCLUSÃO: apagar a Imagem não reescreve o Markdown de ninguém (isso
        exigiria varrer e mutar o conteúdo de todas as entidades). A
        referência deixa de resolver e é renderizada como um marcador
        visível de "imagem não encontrada", em vez de sumir em silêncio.
      - RENOMEAR: a referência é pelo NOME (mesma convenção dos
        `[[wiki-links]]` já existentes), por isso o nome é único por
        campanha. Renomear quebra as referências antigas, exatamente como já
        acontece com wiki-links.
    """

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="imagens")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="imagens"
    )

    imagem = CloudinaryField("Imagem", blank=True, null=True)

    legenda = models.CharField(max_length=300, blank=True)
    creditos = models.CharField(max_length=200, blank=True, help_text="Autoria/fonte da imagem.")

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Imagem"
        verbose_name_plural = "Imagens"

        constraints = [
            # A referência `![[Nome]]` no Markdown é resolvida pelo nome —
            # dois nomes iguais na mesma campanha tornariam a resolução
            # ambígua.
            models.UniqueConstraint(
                fields=["campanha", "nome"],
                name="imagem_nome_unico_por_campanha",
            ),
        ]


class Canva(EntidadeMundo):
    """
    Quadro visual livre (mapa mental, diagrama, organograma, mural de
    investigação). Todo o estado do editor mora em `dados` (JSON), num
    formato versionado pelo frontend — ver `src/types/canva.ts`:

        {
          "versao": 1,
          "fundo": { "cor": "#0e0f13", "padrao": "grade" },
          "viewport": { "x": 0, "y": 0, "zoom": 1 },
          "objetos": [ { "id", "tipo", "x", "y", "w", "h", "rotacao",
                         "z", "estilo", "conteudo", "entidade", "de", "para" } ]
        }

    Um JSONField único (em vez de uma tabela por tipo de objeto) é o que
    permite ao editor ganhar ferramentas novas sem uma migration por
    ferramenta; e o quadro inteiro é sempre lido e salvo de uma vez só,
    então não há ganho em normalizar. Objetos que apontam para uma entidade
    da campanha guardam `{"tipo": "npc", "id": 12}` em `entidade` — uma
    REFERÊNCIA, não uma cópia dos dados (nome/foto são resolvidos na
    leitura, então renomear a entidade reflete no quadro).
    """

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="canvas")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="canvas"
    )

    # Miniatura/exportação do quadro — opcional, preenchida pelo botão
    # "Exportar como imagem" do editor.
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    dados = models.JSONField(default=dict, blank=True)

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Canva"
        verbose_name_plural = "Canvas"


class Criatura(EntidadeMundo):
    """Bestiário da campanha — monstros, animais, aberrações."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="criaturas")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="criaturas"
    )

    foto = CloudinaryField("Foto", blank=True, null=True)

    tipo = models.CharField(max_length=100, blank=True, help_text="Ex.: Besta, Morto-vivo, Aberração.")
    habitat = models.CharField(max_length=200, blank=True)
    nivel = models.PositiveIntegerField(blank=True, null=True)
    tamanho = models.CharField(max_length=20, choices=TAMANHO_CHOICES, blank=True)

    comportamento = models.CharField(max_length=20, choices=[
        ("passivo", "Passivo"),
        ("defensivo", "Defensivo"),
        ("territorial", "Territorial"),
        ("agressivo", "Agressivo"),
        ("hostil", "Hostil"),
    ], blank=True)

    # Onde a criatura é encontrada, de forma ESTRUTURADA (`habitat` é o
    # texto livre) — mesmo padrão de NPC.localizacao.
    local = models.ForeignKey(
        Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="criaturas"
    )

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Criatura"
        verbose_name_plural = "Criaturas"


class Divindade(EntidadeMundo):
    """Panteão da campanha — deuses, entidades e forças cultuadas."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="divindades")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="divindades"
    )

    foto = CloudinaryField("Foto", blank=True, null=True)
    # Segunda imagem, independente da foto: o símbolo sagrado costuma ser
    # exibido JUNTO do retrato (ver EntidadePanel), não no lugar dele.
    simbolo = CloudinaryField("Símbolo", blank=True, null=True)

    dominio = models.CharField(max_length=200, blank=True, help_text="Ex.: Guerra, Morte, Colheita.")
    alinhamento = models.CharField(max_length=100, blank=True)
    categoria = models.CharField(max_length=100, blank=True, help_text="Ex.: Maior, Menor, Semideus.")
    adoradores = models.CharField(max_length=300, blank=True)
    plano = models.CharField(max_length=200, blank=True)

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Divindade"
        verbose_name_plural = "Divindades"


class Raca(EntidadeMundo):
    """Povos e raças (jogáveis ou não) da campanha."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="racas")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="racas"
    )

    imagem = CloudinaryField("Imagem", blank=True, null=True)

    tipo = models.CharField(max_length=100, blank=True, help_text="Ex.: Humanoide, Constructo, Feérico.")
    alinhamento = models.CharField(max_length=100, blank=True)
    tamanho = models.CharField(max_length=20, choices=TAMANHO_CHOICES, blank=True)
    expectativa_vida = models.CharField(max_length=100, blank=True)
    tipo_sociedade = models.CharField(max_length=200, blank=True)

    tendencias = models.TextField(blank=True)
    tracos_raciais = models.TextField(blank=True)

    class Meta(EntidadeMundo.Meta):
        verbose_name = "Raça"
        verbose_name_plural = "Raças"
