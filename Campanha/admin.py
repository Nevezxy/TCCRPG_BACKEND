from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from .models import (
    Campanha,
    NPC,
    RelacaoNPC,
    Local,
    Organizacao,
    MembroOrganizacao,
    Mapa,
    Sessao,
    Missao,
    Evento,
    Nota,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class RelacaoNPCInline(admin.TabularInline):
    model = RelacaoNPC
    fk_name = "npc"
    extra = 0
    autocomplete_fields = ["outro_npc"]
    raw_id_fields = ["personagem"]
    fields = ("personagem", "outro_npc", "tipo_relacao", "descricao")


class MembroOrganizacaoInline(admin.TabularInline):
    model = MembroOrganizacao
    extra = 0
    autocomplete_fields = ["npc"]
    raw_id_fields = ["personagem"]
    fields = ("personagem", "npc", "cargo")


class NotaInline(GenericTabularInline):
    model = Nota
    extra = 0
    fields = ("usuario", "titulo", "conteudo")
    ct_field = "content_type"
    ct_fk_field = "object_id"


# ---------------------------------------------------------------------------
# Campanha
# ---------------------------------------------------------------------------

@admin.register(Campanha)
class CampanhaAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "mestre", "total_jogadores", "criado_em")
    list_filter = ("criado_em",)
    search_fields = ("nome", "codigo", "mestre__username")
    autocomplete_fields = ["mestre"]
    filter_horizontal = ("jogadores", "personagens")
    readonly_fields = ("codigo", "criado_em", "atualizado_em")

    @admin.display(description="Jogadores")
    def total_jogadores(self, obj):
        return obj.jogadores.count()


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------

@admin.register(NPC)
class NPCAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "apelido", "campanha", "estado_atual",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "estado_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "apelido", "campanha__nome")
    autocomplete_fields = ["campanha", "localizacao"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [RelacaoNPCInline, NotaInline]


@admin.register(RelacaoNPC)
class RelacaoNPCAdmin(admin.ModelAdmin):
    list_display = ("npc", "origem", "tipo_relacao")
    list_filter = ("tipo_relacao",)
    search_fields = ("npc__nome", "tipo_relacao")
    autocomplete_fields = ["npc", "outro_npc"]
    raw_id_fields = ["personagem"]


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "status_atual", "nivel_perigo",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "status_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [NotaInline]


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------

@admin.register(Organizacao)
class OrganizacaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "lider", "status_atual",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "status_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "lider_npc", "sede"]
    raw_id_fields = ["lider_personagem"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [MembroOrganizacaoInline, NotaInline]

    @admin.display(description="Líder")
    def lider(self, obj):
        return obj.lider.nome if obj.lider else "—"


@admin.register(MembroOrganizacao)
class MembroOrganizacaoAdmin(admin.ModelAdmin):
    list_display = ("organizacao", "membro", "cargo")
    list_filter = ("organizacao",)
    search_fields = ("organizacao__nome", "cargo")
    autocomplete_fields = ["organizacao", "npc"]
    raw_id_fields = ["personagem"]

    @admin.display(description="Membro")
    def membro(self, obj):
        return obj.membro.nome if obj.membro else "—"


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

@admin.register(Mapa)
class MapaAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "local", "tipo",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "tipo", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "local"]
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------

@admin.register(Sessao)
class SessaoAdmin(admin.ModelAdmin):
    list_display = (
        "numero", "titulo", "campanha", "data",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha"]
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-numero",)


# ---------------------------------------------------------------------------
# Missao
# ---------------------------------------------------------------------------

@admin.register(Missao)
class MissaoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo", "campanha", "status", "dificuldade", "local",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "status", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha", "local"]
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo", "campanha", "data",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha"]
    filter_horizontal = ("locais", "organizacoes")
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# Nota
# ---------------------------------------------------------------------------

@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "usuario", "personagem", "content_type", "object_id", "atualizado_em")
    list_filter = ("content_type",)
    search_fields = ("titulo", "conteudo", "usuario__username")
    autocomplete_fields = ["usuario"]
    raw_id_fields = ["content_type", "personagem"]
    readonly_fields = ("criado_em", "atualizado_em")