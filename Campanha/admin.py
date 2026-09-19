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
    Documento,
    Imagem,
    Canva,
    Criatura,
    Divindade,
    Raca,
    ItemCampanha,
    ArmaCampanha,
    ArmaduraCampanha,
    TecnicaCampanha,
    PoderCampanha,
    HabilidadeCampanha,
    AprimoramentoCampanha,
    Combate,
    ParticipanteCombate,
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
    filter_horizontal = ("jogadores", "moderadores", "personagens", "sistemas")
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


# ---------------------------------------------------------------------------
# Entidades de mundo novas — todas herdam de `EntidadeMundo`, então o admin
# também é o mesmo: a base abaixo cobre os campos comuns e cada registro só
# acrescenta o que é próprio do tipo.
# ---------------------------------------------------------------------------

class EntidadeMundoAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "campanha", "pasta", "ordem",
        "visivel_para_jogadores", "editavel_para_jogadores", "atualizado_em",
    )
    list_filter = ("campanha", "visivel_para_jogadores", "editavel_para_jogadores")
    search_fields = ("nome", "campanha__nome")
    autocomplete_fields = ["campanha", "pasta"]
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = [NotaInline]


@admin.register(Documento)
class DocumentoAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("tipo", "autor")
    autocomplete_fields = ["campanha", "pasta", "local"]


@admin.register(Imagem)
class ImagemAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("legenda",)


@admin.register(Canva)
class CanvaAdmin(EntidadeMundoAdmin):
    pass


@admin.register(Criatura)
class CriaturaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("tipo", "nivel", "tamanho")
    list_filter = EntidadeMundoAdmin.list_filter + ("tamanho", "comportamento")
    autocomplete_fields = ["campanha", "pasta", "local"]


@admin.register(Divindade)
class DivindadeAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("dominio", "categoria")


@admin.register(Raca)
class RacaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("tipo", "tamanho")
    list_filter = EntidadeMundoAdmin.list_filter + ("tamanho",)


# ---------------------------------------------------------------------------
# Equipamentos exclusivos da campanha — também são entidades de mundo, então
# reaproveitam a mesma base; cada um só acrescenta as colunas de jogo.
# ---------------------------------------------------------------------------

@admin.register(ItemCampanha)
class ItemCampanhaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("peso", "valor", "qualidade")
    list_filter = EntidadeMundoAdmin.list_filter + ("qualidade",)


@admin.register(ArmaCampanha)
class ArmaCampanhaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("dano", "tipo_dano", "valor")
    list_filter = EntidadeMundoAdmin.list_filter + ("qualidade", "empunhadura")


@admin.register(ArmaduraCampanha)
class ArmaduraCampanhaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("defesa", "peso", "valor")
    list_filter = EntidadeMundoAdmin.list_filter + ("qualidade",)


# ---------------------------------------------------------------------------
# Técnica/Poder/Habilidade exclusivos da campanha — mesma base de
# EntidadeMundo. `AprimoramentoCampanha` não é EntidadeMundo (ver model),
# então vira um inline da Habilidade, no mesmo molde de `NotaInline`.
# ---------------------------------------------------------------------------

@admin.register(TecnicaCampanha)
class TecnicaCampanhaAdmin(EntidadeMundoAdmin):
    pass


@admin.register(PoderCampanha)
class PoderCampanhaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("tag", "custo")


class AprimoramentoCampanhaInline(admin.TabularInline):
    model = AprimoramentoCampanha
    extra = 0
    fields = ("ordem", "nome", "custo", "descricao")


@admin.register(HabilidadeCampanha)
class HabilidadeCampanhaAdmin(EntidadeMundoAdmin):
    list_display = EntidadeMundoAdmin.list_display + ("tag", "nivel", "custo")
    inlines = [NotaInline, AprimoramentoCampanhaInline]


# ---------------------------------------------------------------------------
# Combate do Escudo do Mestre — só para inspeção/suporte. Editar por aqui não
# publica evento (ver `combate.py`): os clientes abertos só veem a mudança na
# próxima reconexão.
# ---------------------------------------------------------------------------

class ParticipanteCombateInline(admin.TabularInline):
    model = ParticipanteCombate
    fk_name = "combate"
    extra = 0
    fields = ("tipo", "personagem", "npc", "criatura", "iniciativa", "pv_atual", "pv_max", "versao")
    readonly_fields = ("versao",)
    raw_id_fields = ("personagem", "npc", "criatura")


@admin.register(Combate)
class CombateAdmin(admin.ModelAdmin):
    list_display = ("campanha", "rodada", "visivel_para_jogadores", "atualizado_em")
    raw_id_fields = ("campanha", "turno_participante")
    readonly_fields = ("versao",)
    inlines = [ParticipanteCombateInline]
