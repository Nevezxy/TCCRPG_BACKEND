from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import *


class CloudinaryUrlSerializerMixin:
    """
    Converte os CloudinaryField em URL completa na resposta,
    mas mantém os campos graváveis.
    """

    media_fields = []

    def to_representation(self, instance):
        data = super().to_representation(instance)

        for field in self.media_fields:
            value = getattr(instance, field)

            if value:
                data[field] = value.url
            else:
                data[field] = None

        return data


class PersonagemSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto", "banner"]

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


class ItemSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Item
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Arma
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaduraSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

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