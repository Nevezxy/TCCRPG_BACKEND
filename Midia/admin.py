from django.contrib import admin

from .models import AjusteImagem, ExclusaoImagemPendente


@admin.register(ExclusaoImagemPendente)
class ExclusaoImagemPendenteAdmin(admin.ModelAdmin):
    # Só leitura de propósito: a fila é processada por `processar_fila` e
    # pelo comando `limpar_imagens` — editar à mão quebraria a garantia de
    # rechecar o uso antes de apagar.
    list_display = ("public_id", "motivo", "criado_em", "tentativas", "ultimo_erro")
    list_filter = ("motivo",)
    search_fields = ("public_id",)
    readonly_fields = ("public_id", "motivo", "criado_em", "tentativas", "ultimo_erro")

    def has_add_permission(self, request):
        return False


@admin.register(AjusteImagem)
class AjusteImagemAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "campo", "atualizado_em")
    list_filter = ("content_type", "campo")
