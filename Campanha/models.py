import random
import string

from django.db import models
from django.core.exceptions import ValidationError

from Personagem.models import Personagem
from Sistema.models import Sistema
from app import settings
from cloudinary.models import CloudinaryField

from django.db import models
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

    foto = CloudinaryField("Foto", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    apelido = models.CharField(max_length=200, blank=True, db_index=True)
    idade = models.PositiveIntegerField(blank=True, null=True)

    aparencia = models.TextField(blank=True)
    personalidade = models.TextField(blank=True)
    familia = models.TextField(blank=True)
    maior_desejo = models.TextField(blank=True)
    maior_prazer = models.TextField(blank=True)
    peculiaridade = models.TextField(blank=True)
    ocupacao = models.TextField(blank=True)
    status_social = models.TextField(blank=True)
    estado_atual = models.CharField(max_length=200, choices=[
        ("vivo", "Vivo"),
        ("morto", "Morto"),
        ("desaparecido", "Desaparecido"),
    ], blank=True)
    segredo = models.TextField(blank=True)
    anotacoes = models.TextField(blank=True)

    localizacao = models.ForeignKey('Local', on_delete=models.SET_NULL, null=True, blank=True, related_name="npcs_localizados")
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)
    
    ficha = models.JSONField(blank=True, null=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome
    
class RelacaoNPC(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="relacoes")

    personagem = models.ForeignKey(Personagem, null=True, blank=True, on_delete=models.CASCADE, related_name="relacoes_com_npcs")

    outro_npc = models.ForeignKey(NPC, null=True, blank=True, on_delete=models.CASCADE, related_name="relacoes_com_outros_npcs")

    tipo_relacao = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)

    @property
    def origem(self):
        return self.personagem or self.outro_npc

    def __str__(self):
        return f"{self.origem.nome} → {self.npc.nome} ({self.tipo_relacao})"

    class Meta:
        verbose_name = "Relação de NPC"
        verbose_name_plural = "Relações de NPC"

        constraints = [
            # A origem deve ser um Personagem OU um NPC
            models.CheckConstraint(
                condition=(
                    (Q(personagem__isnull=False) & Q(outro_npc__isnull=True)) |
                    (Q(personagem__isnull=True) & Q(outro_npc__isnull=False))
                ),
                name="relacaonpc_uma_origem"
            ),

            # Evita relações duplicadas Personagem -> NPC
            models.UniqueConstraint(
                fields=["personagem", "npc", "tipo_relacao"],
                condition=Q(personagem__isnull=False),
                name="relacaonpc_personagem_unica"
            ),

            # Evita relações duplicadas NPC -> NPC
            models.UniqueConstraint(
                fields=["outro_npc", "npc", "tipo_relacao"],
                condition=Q(outro_npc__isnull=False),
                name="relacaonpc_npc_unica"
            ),
        ]
    
class Local(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="locais")

    imagem = CloudinaryField("Imagem", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    descricao = models.TextField(blank=True)
    historia = models.TextField(blank=True)
    clima = models.TextField(blank=True)
    populacao = models.TextField(blank=True)
    governo = models.TextField(blank=True)
    nivel_perigo = models.IntegerField(blank=True, null=True)
    tesouros = models.TextField(blank=True)
    segredos = models.TextField(blank=True)
    peculiaridade = models.TextField(blank=True)
    status_atual = models.CharField(max_length=200, choices=[
        ("ativo", "Ativo"),
        ("abandonado", "Abandonado"),
        ("destruido", "Destruído"),
    ], blank=True)
    anotacoes = models.TextField(blank=True)
    
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

    descricao = models.TextField(blank=True)
    historia = models.TextField(blank=True)
    objetivos = models.TextField(blank=True)

    sede = models.ForeignKey(
        Local,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizacoes_sede"
    )

    recursos = models.TextField(blank=True)

    status_atual = models.CharField(
        max_length=20,
        choices=[
            ("ativa", "Ativa"),
            ("inativa", "Inativa"),
            ("destruida", "Destruída"),
        ],
        blank=True,
    )

    anotacoes = models.TextField(blank=True)
    
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
    
class MembroOrganizacao(models.Model):
    organizacao = models.ForeignKey(Organizacao, on_delete=models.CASCADE, related_name="membros")

    personagem = models.ForeignKey(Personagem, null=True, blank=True, on_delete=models.CASCADE)

    npc = models.ForeignKey(NPC, null=True, blank=True, on_delete=models.CASCADE)

    cargo = models.CharField(max_length=200, blank=True)

    @property
    def membro(self):
        return self.personagem or self.npc

    def __str__(self):
        return f"{self.membro.nome} - {self.organizacao.nome}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(personagem__isnull=False) & Q(npc__isnull=True)) |
                    (Q(personagem__isnull=True) & Q(npc__isnull=False))
                ),
                name="membro_organizacao_um_tipo"
            ),
            models.UniqueConstraint(
                fields=["organizacao", "personagem"],
                condition=Q(personagem__isnull=False),
                name="personagem_unico_na_organizacao"
            ),
            models.UniqueConstraint(
                fields=["organizacao", "npc"],
                condition=Q(npc__isnull=False),
                name="npc_unico_na_organizacao"
            ),
        ]

class Mapa(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="mapas")
    local = models.ForeignKey(Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="mapas")

    imagem = CloudinaryField("Imagem", blank=True, null=True)
    nome = models.CharField(max_length=200, db_index=True)
    tipo = models.CharField(max_length=200)
    largura = models.PositiveIntegerField(blank=True, null=True)
    altura = models.PositiveIntegerField(blank=True, null=True)
    descricao = models.TextField(blank=True)
    anotacoes = models.TextField(blank=True)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome
    
class Sessao(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="sessoes")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    numero = models.PositiveIntegerField()
    titulo = models.CharField(max_length=200, db_index=True)
    data = models.DateTimeField()
    resumo = models.TextField(blank=True)
    eventos_importantes = models.TextField(blank=True)
    anotacoes = models.TextField(blank=True)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
class Missao(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="missoes")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    titulo = models.CharField(max_length=200, db_index=True)
    descricao = models.TextField(blank=True)
    objetivo = models.TextField(blank=True)
    recompensas = models.TextField(blank=True)
    status = models.CharField(max_length=200, choices=[
        ("ativa", "Ativa"),
        ("concluida", "Concluída"),
        ("falha", "Falha"),
    ], blank=True)
    dificuldade = models.PositiveIntegerField(blank=True, null=True)
    local = models.ForeignKey(Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="missoes")
    anotacoes = models.TextField(blank=True)
    
    visivel_para_jogadores = models.BooleanField(default=True)
    editavel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
class Evento(models.Model):
    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="eventos")
    imagem = CloudinaryField("Imagem", blank=True, null=True)

    titulo = models.CharField(max_length=200, db_index=True)
    descricao = models.TextField(blank=True)
    data = models.CharField(max_length=200, blank=True)
    locais = models.ManyToManyField(Local, blank=True, related_name="eventos")
    organizacoes = models.ManyToManyField(Organizacao, blank=True, related_name="eventos")
    anotacoes = models.TextField(blank=True)
    
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