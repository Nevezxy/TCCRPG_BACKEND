from rest_framework import serializers

from drf_spectacular.utils import extend_schema_field

from Campanha.serializers import UsuarioResumoSerializer
from Midia.serializers import CloudinaryUrlSerializerMixin
from Personagem.serializers import PersonagemSerializer

from .models import Usuario


# Campos de perfil que qualquer pessoa que pode ver o perfil enxerga. `email`
# fica de fora: é dado de conta, não de perfil, e só volta para o próprio
# usuário (`UsuarioSerializer`).
_CAMPOS_PERFIL = (
    "id",
    "username",
    "first_name",
    "last_name",
    "foto",
    "banner",
    "descricao",
    "cor_perfil",
    "links_sociais",
    "date_joined",
    "data_atualizacao",
)


class PerfilPublicoSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):
    """Perfil de OUTRO usuário (`GET /usuario/<id>/`) — só leitura, sem e-mail."""

    media_fields = ["foto", "banner"]

    class Meta:
        model = Usuario
        fields = _CAMPOS_PERFIL
        read_only_fields = _CAMPOS_PERFIL


class UsuarioSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):
    """
    O próprio usuário (`GET/PATCH /usuario/me/`). Continua sendo o
    serializer do login (`AuthContext` do frontend lê `id`/`username`/
    `first_name` daqui), então só GANHA campos — nenhum foi renomeado.

    `foto`/`banner` seguem o contrato do `CloudinaryUrlSerializerMixin`:
    arquivo em multipart para enviar, null para remover, `<campo>_ajuste`
    para o enquadramento.

    `username` fica somente leitura: é a credencial de login, e trocá-la
    por um PATCH de perfil pegaria o usuário de surpresa na próxima entrada.
    """

    media_fields = ["foto", "banner"]

    # Contadores das abas do perfil. Vêm junto do perfil para o cabeçalho
    # mostrar "5 Personagens · 4 Campanhas" antes de cada aba carregar a
    # própria lista.
    totais = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        # `is_superuser` diz ao frontend se mostra a aba "Outros usuários"
        # do perfil — só leitura, claro; a checagem de verdade é no backend
        # (`outros_personagens`/`outras_campanhas`).
        fields = _CAMPOS_PERFIL + ("email", "totais", "is_superuser")
        read_only_fields = ("id", "username", "date_joined", "data_atualizacao", "is_superuser")

    def get_totais(self, obj) -> dict:
        from Campanha.models import Campanha
        from django.db.models import Q

        return {
            "personagens": obj.personagens.count(),
            "campanhas": Campanha.objects.filter(Q(mestre=obj) | Q(jogadores=obj)).distinct().count(),
            "poderes": obj.poderes_usuario.count(),
        }

    def validate_descricao(self, valor):
        return valor.strip()

    def validate_cor_perfil(self, valor):
        return valor.lower()


class PersonagemDeOutroSerializer(PersonagemSerializer):
    """Ficha vista na aba "Outros usuários" (superusuário): a ficha de
    sempre mais quem é o dono."""

    dono = serializers.SerializerMethodField()

    @extend_schema_field(UsuarioResumoSerializer)
    def get_dono(self, obj):
        return UsuarioResumoSerializer(obj.usuario, context=self.context).data


class RegistroSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)

    class Meta:
        model = Usuario
        fields = (
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
        )

    def create(self, validated_data):

        return Usuario.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", "")
        )
