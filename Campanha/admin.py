from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from .models import (
    Campanha,
    NPC,
    Local,
    Organizacao,
    Mapa,
    Sessao,
    Missao,
    Evento,
    Nota,
    Pasta,
    TipoConexao,
    Conexao,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

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
# Pasta
# ---------------------------------------------------------------------------

@admin.register(Pasta)
class PastaAdmin(admin.ModelAdmin):
    list_display = ("nome", "campanha", "pasta_pai", "ordem", "atualizado_em")
    list_filter = ("campanha",)
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "pasta_pai"]
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------

@admin.register(NPC)
class NPCAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "apelido", "campanha", "pasta", "estado_atual",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "estado_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "apelido", "campanha__nome")
    autocomplete_fields = ["campanha", "localizacao", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [NotaInline]


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "pasta", "status_atual", "nivel_perigo",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "status_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [NotaInline]


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------

@admin.register(Organizacao)
class OrganizacaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "pasta", "lider", "status_atual",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "status_atual", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "lider_npc", "sede", "pasta"]
    raw_id_fields = ["lider_personagem"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [NotaInline]

    @admin.display(description="Líder")
    def lider(self, obj):
        return obj.lider.nome if obj.lider else "—"


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

@admin.register(Mapa)
class MapaAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "pasta", "local", "tipo",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "tipo", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "local", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------

@admin.register(Sessao)
class SessaoAdmin(admin.ModelAdmin):
    list_display = (
        "numero", "titulo", "campanha", "pasta", "data",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")
    ordering = ("-numero",)


# ---------------------------------------------------------------------------
# Missao
# ---------------------------------------------------------------------------

@admin.register(Missao)
class MissaoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo", "campanha", "pasta", "status", "dificuldade", "local",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "status", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha", "local", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo", "campanha", "pasta", "data",
        "visivel_para_jogadores", "editavel_para_jogadores",
    )
    list_filter = ("campanha", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("titulo", "campanha__nome")
    autocomplete_fields = ["campanha", "pasta"]
    filter_horizontal = ("locais", "organizacoes")
    readonly_fields = ("criado_em", "atualizado_em")


# ---------------------------------------------------------------------------
# TipoConexao / Conexao
# ---------------------------------------------------------------------------

@admin.register(TipoConexao)
class TipoConexaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "inverso", "criado_em")
    search_fields = ("nome",)
    autocomplete_fields = ["inverso"]


@admin.register(Conexao)
class ConexaoAdmin(admin.ModelAdmin):
    list_display = (
        "campanha", "entidade1_tipo", "entidade1_id", "tipo",
        "entidade2_tipo", "entidade2_id", "atualizado_em",
    )
    list_filter = ("campanha", "tipo", "entidade1_tipo", "entidade2_tipo")
    search_fields = ("descricao",)
    autocomplete_fields = ["campanha", "tipo"]
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
