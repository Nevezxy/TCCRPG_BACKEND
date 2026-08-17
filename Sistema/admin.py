from django.contrib import admin

from .models import (
    Sistema,
    PoderSistema,
    ItemSistema,
    ArmaSistema,
    ArmaduraSistema,
    HabilidadeSistema,
    Regra,
    Modificacao,
    GrupoArmas,
)


@admin.register(Sistema)
class SistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
    )

    search_fields = (
        "nome",
    )


@admin.register(PoderSistema)
class PoderSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "tag",
        "custo",
    )

    list_filter = (
        "sistema",
        "tag",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(ItemSistema)
class ItemSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "peso",
        "valor",
        "qualidade",
    )

    list_filter = (
        "sistema",
        "qualidade",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(ArmaSistema)
class ArmaSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "dano",
        "tipo_dano",
        "empunhadura",
    )

    list_filter = (
        "sistema",
        "tipo_dano",
        "empunhadura",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(ArmaduraSistema)
class ArmaduraSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "defesa",
        "peso",
        "valor",
    )

    list_filter = (
        "sistema",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(HabilidadeSistema)
class HabilidadeSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "tag",
        "nivel",
        "custo",
    )

    list_filter = (
        "sistema",
        "tag",
        "nivel",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(Regra)
class RegraAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sistema",
        "tag",
    )

    list_filter = (
        "sistema",
        "tag",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(Modificacao)
class ModificacaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "custo",
    )

    search_fields = (
        "nome",
        "descricao",
    )


@admin.register(GrupoArmas)
class GrupoArmasAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
    )

    search_fields = (
        "nome",
        "descricao",
    )