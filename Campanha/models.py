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

    sistema = models.ForeignKey(Sistema, on_delete=models.SET_NULL, related_name='campanhas', blank=True, null=True)

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

    return [NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento, _Personagem]


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