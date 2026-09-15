from django.db import transaction
from rest_framework import serializers
from Sistema.serializers import SincronizaSistemasMixin
from drf_spectacular.utils import extend_schema_field

# O mixin mora no app Midia (upload seguro + enquadramento + limpeza do
# Cloudinary); reexportado aqui porque o Campanha já o importa deste módulo.
from Midia.serializers import CloudinaryUrlSerializerMixin  # noqa: F401

from .models import *


class PersonagemSerializer(SincronizaSistemasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto", "banner"]

    # Ids das campanhas das quais este personagem participa (M2M reverso de
    # `Campanha.personagens`). Só leitura: quem entra/sai de uma campanha é
    # decidido pelos endpoints da própria Campanha, nunca por um PATCH na
    # ficha. Exposto porque a Biblioteca precisa saber quais campanhas
    # consultar para oferecer os equipamentos exclusivos delas — mesmo papel
    # que `sistemas` já cumpre para as bibliotecas de regras.
    campanhas = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Personagem
        fields = "__all__"
        read_only_fields = ("usuario",)


class StatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Status
        fields = "__all__"
        read_only_fields = ("personagem",)


class AtributoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Atributo
        fields = "__all__"
        read_only_fields = ("personagem",)


class DefesaSerializer(serializers.ModelSerializer):

    class Meta:
        model = Defesa
        fields = "__all__"
        read_only_fields = ("personagem",)


class PericiaSerializer(serializers.ModelSerializer):

    class Meta:
        model = Pericia
        fields = "__all__"
        read_only_fields = ("personagem",)


class SincronizaVendasMixin:
    """
    Faz `Item.vendas` valer de verdade: marcado, o item é anunciado no
    Comércio Livre da campanha (preço = `valor`, quantidade = a que o
    personagem tem); desmarcado, é retirado da venda.

    Sem isto o booleano seria só decoração — a ficha diria "à venda" e não
    haveria anúncio nenhum para os outros jogadores comprarem.

    Só age quando o campo VEIO na requisição: um PATCH que mexe no peso não
    tem por que recriar (nem encerrar) um anúncio. O import é tardio porque
    `Campanha` importa `Personagem`, nunca o contrário.

    Uma regra de comércio violada (personagem sem campanha, ou em várias, e
    por isso ambígua) vira erro de validação no campo `vendas`. O save e a
    sincronização ficam na MESMA transação de propósito: sem ela o item já
    estaria gravado com `vendas=True` quando o erro subisse, e a ficha
    passaria a mentir — diria "à venda" sem existir anúncio nenhum.
    """

    def _com_sincronizacao(self, salvar, veio_no_payload):
        from Campanha.comercio import ErroComercio, sincronizar_vendas

        if not veio_no_payload:
            return salvar()

        try:
            with transaction.atomic():
                instance = salvar()
                sincronizar_vendas(instance)
        except ErroComercio as exc:
            raise serializers.ValidationError({"vendas": [exc.mensagem]}) from exc

        return instance

    def create(self, validated_data):
        return self._com_sincronizacao(
            lambda: super(SincronizaVendasMixin, self).create(validated_data),
            "vendas" in validated_data,
        )

    def update(self, instance, validated_data):
        return self._com_sincronizacao(
            lambda: super(SincronizaVendasMixin, self).update(instance, validated_data),
            "vendas" in validated_data,
        )


class ItemSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Item
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Arma
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaduraSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Armadura
        fields = "__all__"
        read_only_fields = ("personagem",)


class TecnicaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Tecnica
        fields = "__all__"
        read_only_fields = ("personagem",)


class PoderSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Poder
        fields = "__all__"
        read_only_fields = ("personagem",)


class HabilidadeSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Habilidade
        fields = "__all__"
        read_only_fields = ("personagem",)


class AprimoramentoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Aprimoramento
        fields = "__all__"
        read_only_fields = ("personagem", "habilidade")


class BonusSerializer(serializers.ModelSerializer):

    tipo = serializers.SerializerMethodField(read_only=True)
    alvo_nome = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bonus
        fields = [
            "id",
            "content_type",
            "object_id",
            "tipo",
            "alvo_nome",
            "nome",
            "valor",
            "ativo",
            "somente_teste",
        ]
        read_only_fields = [
            "content_type",
            # AUDIT FIX: `object_id` já é atribuído pela view a partir da
            # URL (`bonus_lista`, via `serializer.save(object_id=object_id)`),
            # exatamente como `content_type`. Sem isso no read_only_fields,
            # todo POST para criar um Bonus falhava com
            # `{"object_id": ["This field is required."]}` a menos que o
            # cliente reenviasse manualmente o mesmo `object_id` já
            # presente na URL — e mesmo assim o valor enviado era
            # ignorado, porque os kwargs de `.save()` sempre sobrescrevem
            # `validated_data`. Bug confirmado rodando a API de verdade
            # (POST em `/personagem/status/<id>/bonus/` retornava 400).
            "object_id",
            "tipo",
            "alvo_nome",
        ]

    @extend_schema_field(serializers.CharField())
    def get_tipo(self, obj):
        return obj.content_type.model

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_alvo_nome(self, obj):
        if obj.alvo is None:
            return None

        if hasattr(obj.alvo, "nome"):
            return obj.alvo.nome

        return str(obj.alvo)