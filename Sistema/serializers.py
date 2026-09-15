from rest_framework import serializers

from Midia.serializers import CloudinaryUrlSerializerMixin
from Sistema.models import *


class SistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sistema
        fields = "__all__"
        
class RegraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regra
        fields = "__all__"

class PoderSistemaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = PoderSistema
        fields = "__all__"
        
class HabilidadeSistemaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = HabilidadeSistema
        fields = "__all__"
        
class ModificacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modificacao
        fields = "__all__"


class GrupoArmasSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrupoArmas
        fields = "__all__"
        
class ItemSistemaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = ItemSistema
        fields = "__all__"
        
class ArmaSistemaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = ArmaSistema
        fields = "__all__"
        
class ArmaduraSistemaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = ArmaduraSistema
        fields = "__all__"

# ---------------------------------------------------------------------------
# Múltiplas bibliotecas de regras (seção 1 da tarefa)
# ---------------------------------------------------------------------------

class SincronizaSistemasMixin:
    """
    Mantém `sistema` (FK, sistema PRINCIPAL) e `sistemas` (M2M, todas as
    bibliotecas de regras em uso) coerentes entre si, tanto em Campanha
    quanto em Personagem.

    Por que os dois campos coexistem: `sistema` já está gravado em toda
    campanha/ficha existente e é lido por vários pontos do app que precisam
    de UM sistema só (features de `systemConfig`, rótulo no cabeçalho). Em
    vez de removê-lo — o que exigiria migrar e reescrever esses pontos, com
    risco para dados existentes (seção 10) — ele passa a ser "o primeiro da
    lista", e este mixin garante que nunca diverge:

      - se vier `sistemas` sem `sistema`, o principal vira o primeiro da lista;
      - se vier `sistema` (fluxos antigos, ex.: o PATCH do seletor de
        sistema), ele é adicionado a `sistemas` automaticamente;
      - se o principal for removido da lista, ele é substituído pelo
        primeiro que sobrou (ou por `None`, se a lista ficou vazia).

    Assim, campanhas antigas que só têm `sistema` continuam funcionando, e
    qualquer cliente novo pode trabalhar só com `sistemas`.
    """

    def _sincroniza_sistemas(self, instance, sistemas_enviados, sistema_enviado=False):
        # `sistemas_enviados is None` = o campo não veio na requisição (PATCH
        # parcial): nada a reconciliar do lado da lista.
        if sistemas_enviados is not None:
            instance.sistemas.set(sistemas_enviados)

        atuais = list(instance.sistemas.all())

        if sistema_enviado and instance.sistema_id:
            # Fluxo antigo (PATCH { "sistema": X }): o principal entra na lista.
            if all(s.id != instance.sistema_id for s in atuais):
                instance.sistemas.add(instance.sistema)
                atuais.append(instance.sistema)

        principal_valido = instance.sistema_id and any(s.id == instance.sistema_id for s in atuais)

        if not principal_valido:
            novo_principal = atuais[0] if atuais else None

            if instance.sistema_id != (novo_principal.id if novo_principal else None):
                instance.sistema = novo_principal
                instance.save(update_fields=["sistema"])

    def create(self, validated_data):
        sistemas = validated_data.pop("sistemas", None)
        sistema_enviado = "sistema" in validated_data
        instance = super().create(validated_data)
        self._sincroniza_sistemas(instance, sistemas, sistema_enviado)
        return instance

    def update(self, instance, validated_data):
        sistemas = validated_data.pop("sistemas", None)
        sistema_enviado = "sistema" in validated_data
        instance = super().update(instance, validated_data)
        self._sincroniza_sistemas(instance, sistemas, sistema_enviado)
        return instance
