import random
import string

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from Personagem.models import Item, Personagem, Versionado
from Sistema.models import Sistema
from app import settings
from cloudinary.models import CloudinaryField

from django.db.models import Q

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Campanha(models.Model):
    mestre = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campanhas_criadas")
    jogadores = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="campanhas", blank=True)
    # Jogadores promovidos a Moderador pelo mestre — sempre um SUBCONJUNTO de
    # `jogadores` (a UI só deixa promover quem já está na campanha). Um
    # moderador tem todos os poderes do mestre sobre a campanha (ver
    # `Usuario.permissions.pode_gerenciar_campanha`), MENOS excluir a
    # campanha e remover jogadores — essas duas ações continuam checando
    # `mestre` diretamente, nunca este campo.
    moderadores = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="campanhas_moderadas", blank=True)
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

class FichaPreset(models.Model):
    """
    Modelo reutilizável de ficha de NPC ("predefinição"), salvo pelo
    usuário a partir do editor de ficha (NPC.ficha) para recriar NPCs
    parecidos depois — inclusive em outras campanhas.

    Propositalmente SEM ForeignKey para Campanha: é só isso que permite
    reaproveitar a mesma predefinição ("Goblin", "Guarda da Cidade"...) em
    qualquer campanha do usuário, não apenas na campanha onde foi criada.
    Isolado por `usuario` — nunca compartilhado entre usuários, nem quando
    são mestre/jogador da mesma campanha.

    `dados` guarda uma cópia integral de `NPC.ficha` (que já inclui o
    `template`/modelo usado) — mesmo princípio de JSON livre já usado em
    `Canva.dados`, sem duplicar campos de ficha um a um.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fichas_predefinidas"
    )
    nome = models.CharField(max_length=200)
    dados = models.JSONField(default=dict, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "nome"], name="ficha_preset_nome_unico_por_usuario"
            )
        ]

    def __str__(self):
        return self.nome

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
        ItemCampanha, ArmaCampanha, ArmaduraCampanha,
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

    # Mesmo mecanismo de NPC.ficha: JSON livre editado pelo mesmo editor de
    # ficha (`ficha-rpg-editor.html`), reaproveitado aqui sem duplicar o
    # formato — a criatura também é um "bloco de personagem" jogável (ex.:
    # para virar um monstro controlável ou ser usada como referência de
    # combate pelo mestre).
    ficha = models.JSONField(blank=True, null=True)

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


# ---------------------------------------------------------------------------
# Equipamentos exclusivos da campanha
#
# São entidades de MUNDO (herdam `EntidadeMundo`), não um catálogo à parte:
# ficam na árvore de pastas junto com NPCs e Locais, entram na busca global,
# podem ser duplicadas, conectadas e anotadas — tudo herdado, sem código por
# tipo. O que o mestre cria aqui pertence só a esta campanha e NUNCA toca nos
# itens originais do Sistema.
#
# Os campos de jogo são os mesmos do trio equivalente do app Sistema
# (`ItemSistema`/`ArmaSistema`/`ArmaduraSistema`), para a cópia para a ficha
# ser campo a campo, sem conversão.
#
# Por que `descricao` ALÉM do `conteudo` herdado — são coisas diferentes:
#   `descricao` é o texto do equipamento, o que VIAJA para a ficha ao copiar
#     (e `Item.descricao` lá é richtext, o mesmo formato daqui);
#   `conteudo` é o Markdown de lore da campanha, que toda entidade de mundo
#     tem e que fica no Mundo — mandá-lo para a ficha entregaria os `##`
#     literais dentro do editor richtext de lá.
# ---------------------------------------------------------------------------

class EquipamentoCampanha(EntidadeMundo):

    foto = CloudinaryField("Foto", blank=True, null=True)
    descricao = models.TextField(blank=True)
    peso = models.DecimalField(default=0, max_digits=20, decimal_places=1)
    valor = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    qualidade = models.CharField(max_length=100, blank=True)

    class Meta(EntidadeMundo.Meta):
        abstract = True


class ItemCampanha(EquipamentoCampanha):
    """Item exclusivo desta campanha."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="itens_campanha")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_campanha"
    )

    class Meta(EquipamentoCampanha.Meta):
        verbose_name = "Item"
        verbose_name_plural = "Itens"


class ArmaCampanha(EquipamentoCampanha):
    """Arma exclusiva desta campanha."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="armas_campanha")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="armas_campanha"
    )

    ataque = models.IntegerField(default=0, blank=True)
    dano = models.CharField(default="1d4", max_length=30, blank=True)
    dano_extra = models.CharField(default="0", max_length=30, blank=True)
    margem_critico = models.CharField(default="20", max_length=30, blank=True)
    critico = models.CharField(default="+1d", max_length=30, blank=True)
    alcance = models.CharField(default="Adjacente", max_length=30, blank=True)
    tipo_dano = models.CharField(default="Cortante", max_length=30, blank=True)
    empunhadura = models.CharField(default="Leve", max_length=30, blank=True)

    class Meta(EquipamentoCampanha.Meta):
        verbose_name = "Arma"
        verbose_name_plural = "Armas"


class ArmaduraCampanha(EquipamentoCampanha):
    """Armadura exclusiva desta campanha."""

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="armaduras_campanha")

    pasta = models.ForeignKey(
        "Pasta", on_delete=models.SET_NULL, null=True, blank=True, related_name="armaduras_campanha"
    )

    defesa = models.IntegerField(default=0, blank=True)

    class Meta(EquipamentoCampanha.Meta):
        verbose_name = "Armadura"
        verbose_name_plural = "Armaduras"


# ---------------------------------------------------------------------------
# Loja da campanha
#
# Duas peças: CATEGORIAS criadas pelo mestre (com rotação opcional) e
# PRODUTOS, que são uma referência a algo que já existe — um equipamento do
# Sistema usado pela campanha ou um exclusivo dela — mais preço, estoque e
# disponibilidade.
#
# O produto aponta para a origem por GenericForeignKey (mesmo padrão de
# Nota/Bonus/Conexao) em vez de seis FKs anuláveis, e `modelos_vendaveis()`
# é a allowlist que impede qualquer outro content_type de entrar. Referência,
# não cópia: mudar o nome de uma arma do Sistema muda o que a loja mostra, e
# a loja nunca altera o original.
# ---------------------------------------------------------------------------

def modelos_vendaveis():
    """
    O que pode virar produto: os três equipamentos do app Sistema e os três
    exclusivos da campanha. Import tardio pelo mesmo motivo de
    `modelos_conectaveis()`.
    """
    from Sistema.models import ArmaduraSistema, ArmaSistema, ItemSistema

    return [
        ItemSistema, ArmaSistema, ArmaduraSistema,
        ItemCampanha, ArmaCampanha, ArmaduraCampanha,
    ]


def _semente_aleatoria():
    # Só precisa ser estável e diferente entre categorias — não é segredo.
    return random.randint(1, 2_000_000_000)


class CategoriaLoja(models.Model):
    """
    Prateleira da loja ("Armas", "Consumíveis", "Itens mágicos"...), criada
    e nomeada pelo mestre. Um produto pode estar em mais de uma.

    ROTAÇÃO: em vez de um job agendado girando o estoque (o projeto não tem
    fila nem cron), a seleção é uma FUNÇÃO PURA do relógio — ver
    `Campanha/loja.py`. Os campos abaixo são os parâmetros dessa função:
    `rotacao_inicio` ancora as janelas, `rotacao_semente` decide o sorteio.
    Isso dá as três garantias pedidas de uma vez: todo mundo na mesa vê a
    MESMA seleção (é a mesma conta, feita no servidor), a loja sobrevive a
    restart/deploy (não há estado guardado) e o cliente não precisa ficar
    perguntando — a resposta já diz quando vira.
    """

    METODOS_ROTACAO = [
        ("aleatorio", "Aleatório"),
        ("ordem", "Por ordem"),
    ]

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="categorias_loja")

    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)

    icone = models.CharField(max_length=100, blank=True, help_text="Nome do ícone lucide (ex.: 'sword').")
    cor = models.CharField(max_length=7, blank=True, help_text="Cor hexadecimal (ex.: '#FF0000').")

    ordem = models.PositiveIntegerField(default=0)
    visivel_para_jogadores = models.BooleanField(default=True)

    rotacao_ativa = models.BooleanField(default=False)
    rotacao_quantidade = models.PositiveIntegerField(
        default=3, help_text="Quantos produtos ficam à mostra por vez."
    )
    rotacao_intervalo_minutos = models.PositiveIntegerField(
        default=60, help_text="De quanto em quanto tempo a seleção troca."
    )
    rotacao_metodo = models.CharField(max_length=20, choices=METODOS_ROTACAO, default="aleatorio")
    # Âncora das janelas: a seleção da categoria é decidida por
    # `floor((agora - rotacao_inicio) / intervalo)`.
    rotacao_inicio = models.DateTimeField(default=timezone.now)
    # Trocar a semente re-sorteia a vitrine sem mexer no relógio (é o
    # "embaralhar de novo" do mestre).
    rotacao_semente = models.PositiveBigIntegerField(default=_semente_aleatoria)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "Categoria da loja"
        verbose_name_plural = "Categorias da loja"
        constraints = [
            models.UniqueConstraint(
                fields=["campanha", "nome"], name="categoria_loja_nome_unico_por_campanha"
            )
        ]
        indexes = [models.Index(fields=["campanha", "ordem"])]

    def __str__(self):
        return self.nome


class ProdutoLoja(models.Model):
    """
    Um equipamento à venda na loja do mestre, com preço e estoque próprios.

    `campanha` é redundante com a campanha da origem (para os exclusivos) e
    NÃO é para os do Sistema, que são compartilhados entre mesas — é
    justamente por isso que existe: é ela que diz de qual loja este produto
    é, e é por ela que todo filtro e toda permissão passam.

    `quantidade_disponivel` nulo = estoque ilimitado. Zero = esgotado, e o
    produto deixa de ser comprável (ver a validação da compra).
    """

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="produtos_loja")

    categorias = models.ManyToManyField(CategoriaLoja, blank=True, related_name="produtos")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    object_id = models.PositiveIntegerField()
    origem = GenericForeignKey("content_type", "object_id")

    preco = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    quantidade_disponivel = models.PositiveIntegerField(
        null=True, blank=True, help_text="Vazio = estoque ilimitado."
    )
    disponivel = models.BooleanField(default=True)

    ordem = models.PositiveIntegerField(default=0)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Produto da loja"
        verbose_name_plural = "Produtos da loja"
        constraints = [
            # O mesmo equipamento não entra duas vezes na loja da mesma
            # campanha — preço e estoque dele são um só.
            models.UniqueConstraint(
                fields=["campanha", "content_type", "object_id"],
                name="produto_loja_unico_por_campanha",
            )
        ]
        indexes = [
            models.Index(fields=["campanha", "disponivel"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.origem} ({self.preco})"

    @property
    def esgotado(self):
        return self.quantidade_disponivel is not None and self.quantidade_disponivel <= 0


class TransacaoLoja(models.Model):
    """
    Registro imutável de uma compra — é o "registrar corretamente a operação"
    do requisito, e a base do extrato que o mestre consulta.

    Os dados do item são um SNAPSHOT (nome, preço unitário, total): a
    transação precisa continuar legível depois que o produto sai da loja ou
    o equipamento de origem é excluído, e por isso as FKs são SET_NULL.

    `chave_idempotencia` é a proteção real contra compra duplicada. O botão
    desabilitado no cliente não cobre retry de rede, dois toques no celular
    nem uma reconexão que reenvia o POST; com a chave, o segundo pedido
    encontra a transação já gravada e devolve ELA, sem cobrar de novo. É
    `unique` no banco, então nem duas requisições simultâneas passam.
    """

    TIPOS = [
        ("loja", "Loja da campanha"),
        ("comercio_livre", "Comércio livre"),
    ]

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="transacoes_loja")
    tipo = models.CharField(max_length=20, choices=TIPOS, default="loja")

    comprador_personagem = models.ForeignKey(
        Personagem, on_delete=models.SET_NULL, null=True, blank=True, related_name="compras"
    )
    # Nulo nas compras da loja do mestre — lá não há vendedor.
    vendedor_personagem = models.ForeignKey(
        Personagem, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendas"
    )

    produto = models.ForeignKey(
        ProdutoLoja, on_delete=models.SET_NULL, null=True, blank=True, related_name="transacoes"
    )
    # Preenchido nas vendas do Comércio Livre; nulo nas da loja do mestre.
    anuncio = models.ForeignKey(
        "AnuncioComercioLivre", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacoes"
    )

    nome_item = models.CharField(max_length=200)
    preco_unitario = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    quantidade = models.PositiveIntegerField(default=1)
    total = models.DecimalField(default=0, max_digits=20, decimal_places=2)

    chave_idempotencia = models.CharField(max_length=64, null=True, blank=True, unique=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Transação da loja"
        verbose_name_plural = "Transações da loja"
        indexes = [models.Index(fields=["campanha", "-criado_em"])]

    def __str__(self):
        return f"{self.nome_item} x{self.quantidade} ({self.total})"


# ---------------------------------------------------------------------------
# Comércio Livre — jogadores vendendo entre si
# ---------------------------------------------------------------------------

class AnuncioComercioLivre(models.Model):
    """
    Um item do inventário de um jogador posto à venda para os outros da
    mesma mesa.

    `item` é uma FK para `Personagem.Item` e isso já cobre os três tipos:
    `Arma` e `Armadura` são subclasses por herança multi-tabela e
    compartilham o mesmo pk, então uma FK só aponta para qualquer um deles —
    não é preciso GenericForeignKey aqui (diferente de `ProdutoLoja`, cujas
    seis origens não têm ancestral comum).

    O anúncio é sempre o espelho de `Item.vendas`: um anúncio ativo por
    item, garantido por constraint parcial, e os dois lados são mantidos
    em sincronia por `Campanha.comercio`.
    """

    campanha = models.ForeignKey(Campanha, on_delete=models.CASCADE, related_name="anuncios")

    vendedor_personagem = models.ForeignKey(
        Personagem, on_delete=models.CASCADE, related_name="anuncios"
    )

    # SET_NULL, e não CASCADE: vender TODAS as unidades apaga a linha do
    # inventário do vendedor, e com cascata o anúncio sumiria junto —
    # levando embora o registro para o qual a transação recém-criada aponta
    # (e o histórico de quem vendeu o quê). O anúncio encerrado sobrevive ao
    # item; `item_dados` volta nulo e o card mostra só o que foi negociado.
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="anuncios"
    )

    quantidade = models.PositiveIntegerField(default=1)
    preco = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    ativo = models.BooleanField(default=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Anúncio do comércio livre"
        verbose_name_plural = "Anúncios do comércio livre"
        constraints = [
            # Um item não pode estar à venda duas vezes ao mesmo tempo. A
            # constraint é PARCIAL (só sobre os ativos) para que o histórico
            # de anúncios encerrados do mesmo item continue possível.
            models.UniqueConstraint(
                fields=["item"],
                condition=Q(ativo=True),
                name="anuncio_ativo_unico_por_item",
            )
        ]
        indexes = [models.Index(fields=["campanha", "ativo"])]

    def __str__(self):
        return f"{self.item.nome} x{self.quantidade} ({self.preco})"


# ---------------------------------------------------------------------------
# Combate (Escudo do Mestre) — ordem de iniciativa, PV de combate e turno.
# Ver `Campanha/combate.py` para as operações e os eventos em tempo real.
# ---------------------------------------------------------------------------

class Combate(Versionado):
    """
    O combate da campanha — UM por campanha, criado sob demanda. Não existe
    "encerrar e criar outro": o mestre esvazia a lista e reinicia a rodada.
    Guardar só o combate corrente é o que a mesa usa; histórico de combates
    seria um requisito novo, não um efeito colateral deste modelo.

    `Versionado` porque rodada/turno/visibilidade também chegam por evento:
    dois "próximo turno" publicados fora de ordem não podem fazer a tela
    voltar um turno.
    """

    campanha = models.OneToOneField(Campanha, on_delete=models.CASCADE, related_name="combate")
    rodada = models.PositiveIntegerField(default=1)
    # SET_NULL: o participante que está agindo pode sumir numa cascata (o
    # NPC foi excluído em outra aba). As remoções feitas pelo próprio
    # combate já passam a vez adiante antes de apagar (ver `combate.remover`).
    turno_participante = models.ForeignKey(
        "ParticipanteCombate", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Desligado por padrão: PV de inimigo e ordem de ação são informação do
    # mestre até ele decidir mostrar.
    visivel_para_jogadores = models.BooleanField(default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Combate"
        verbose_name_plural = "Combates"

    def __str__(self):
        return f"Combate de {self.campanha} (rodada {self.rodada})"


class ParticipanteCombate(Versionado):
    """
    Uma entrada na lista de iniciativa. A mesma entidade pode aparecer várias
    vezes (três goblins a partir de uma única Criatura), e cada entrada tem o
    PRÓPRIO PV — por isso o PV de combate mora aqui, e não na `ficha` do
    NPC/Criatura (que, além disso, guarda o PV como texto livre: "45 / 45").

    Três FKs reais em vez de GenericForeignKey: a lista resolve nome e foto
    com `select_related` (sem N+1), e excluir a entidade apaga a entrada no
    próprio banco — nunca sobra participante apontando para nada.

    Desempate da iniciativa pelo `id`: ids só crescem, então empatados ficam
    na ordem em que entraram no combate, igual em qualquer cliente.
    """

    TIPO_CHOICES = [
        ("personagem", "Personagem"),
        ("npc", "NPC"),
        ("criatura", "Criatura"),
    ]

    combate = models.ForeignKey(Combate, on_delete=models.CASCADE, related_name="participantes")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    personagem = models.ForeignKey(
        Personagem, on_delete=models.CASCADE, null=True, blank=True, related_name="participacoes_combate"
    )
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, null=True, blank=True, related_name="participacoes_combate")
    criatura = models.ForeignKey(
        Criatura, on_delete=models.CASCADE, null=True, blank=True, related_name="participacoes_combate"
    )

    iniciativa = models.IntegerField(default=0)
    # Nulos para personagens: o PV deles é o Status da ficha, que o Escudo já
    # sincroniza — duplicar aqui criaria duas "vidas" divergentes.
    pv_atual = models.PositiveIntegerField(null=True, blank=True)
    pv_max = models.PositiveIntegerField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-iniciativa", "id"]
        verbose_name = "Participante de combate"
        verbose_name_plural = "Participantes de combate"
        constraints = [
            # Exatamente a FK correspondente ao `tipo` preenchida — o banco
            # garante o que o serializer valida.
            models.CheckConstraint(
                condition=(
                    Q(tipo="personagem", personagem__isnull=False, npc__isnull=True, criatura__isnull=True)
                    | Q(tipo="npc", personagem__isnull=True, npc__isnull=False, criatura__isnull=True)
                    | Q(tipo="criatura", personagem__isnull=True, npc__isnull=True, criatura__isnull=False)
                ),
                name="participante_combate_uma_entidade",
            )
        ]
        indexes = [models.Index(fields=["combate", "-iniciativa", "id"])]

    @property
    def entidade(self):
        return self.personagem or self.npc or self.criatura

    def __str__(self):
        entidade = self.entidade
        return f"{entidade} ({self.iniciativa})" if entidade else f"Participante {self.pk}"
