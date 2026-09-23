import json

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from Campanha.models import Campanha
from Campanha.serializers import CampanhaPerfilSerializer, CampanhaSerializer
from Personagem.models import Personagem, PoderUsuario
from Personagem.serializers import PersonagemSerializer, PoderUsuarioSerializer

from .models import Usuario
from .permissions import pode_ver_perfil
from .serializers import PerfilPublicoSerializer, PersonagemDeOutroSerializer, RegistroSerializer, UsuarioSerializer
from .utils import check_object_permission


@extend_schema(
    methods=["POST"],
    operation_id="registrar_usuario",
    request=RegistroSerializer,
    responses=RegistroSerializer,
)
@api_view(["POST"])
# AUDIT FIX: precisa ser explicitamente público agora que
# DEFAULT_PERMISSION_CLASSES passou a ser IsAuthenticated (ver
# app/settings.py). Antes disso, este endpoint já era público só porque o
# padrão global era AllowAny — comportamento mantido, agora declarado
# explicitamente.
@permission_classes([AllowAny])
def registrar(request):

    serializer = RegistroSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )
    
@extend_schema(
    methods=["GET"],
    operation_id="usuario_atual",
    responses=UsuarioSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_perfil",
    request=UsuarioSerializer,
    responses=UsuarioSerializer,
    description=(
        "Atualiza o perfil do próprio usuário. Aceita JSON ou multipart "
        "(para `foto`/`banner`). `links_sociais` em multipart vai como "
        "string JSON."
    ),
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):

    if request.method == "GET":
        return Response(UsuarioSerializer(request.user).data)

    dados = request.data
    # Multipart não tem lista de objetos: o formulário de perfil manda
    # `links_sociais` serializado, e aqui ele volta a ser lista antes da
    # validação (que continua sendo a do model — ver `validar_links_sociais`).
    if isinstance(dados.get("links_sociais"), str):
        # `.dict()` e não `.copy()`: o QueryDict do multipart carrega o
        # arquivo enviado, e `.copy()` faz deepcopy dele.
        dados = dados.dict() if hasattr(dados, "dict") else dict(dados)
        try:
            dados["links_sociais"] = json.loads(dados["links_sociais"])
        except ValueError:
            return Response(
                {"links_sociais": ["Envie uma lista de links em JSON."]},
                status=status.HTTP_400_BAD_REQUEST
            )

    serializer = UsuarioSerializer(request.user, data=dados, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_perfil_usuario",
    responses=PerfilPublicoSerializer,
    description="Perfil de outro usuário (sem e-mail). Visível para quem divide alguma campanha com ele.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def perfil(request, pk):

    try:
        usuario = Usuario.objects.get(pk=pk, is_active=True)

    except Usuario.DoesNotExist:
        return Response({"erro": "Usuário não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    # 404 em vez de 403 para quem não joga com a pessoa: um 403 confirmaria
    # que aquele id existe, e daria para enumerar as contas do sistema.
    if not pode_ver_perfil(request.user, usuario):
        return Response({"erro": "Usuário não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    return Response(PerfilPublicoSerializer(usuario).data)


@extend_schema(
    methods=["GET"],
    operation_id="listar_meus_personagens",
    responses=PersonagemSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_personagens(request):
    # Sempre os do PRÓPRIO usuário — diferente de `GET /personagem/`, que
    # para o superuser devolve os de todo mundo. A aba do perfil é "meus".
    personagens = (
        Personagem.objects.filter(usuario=request.user)
        .prefetch_related("campanhas", "sistemas")
        .order_by("-atualizado_em")
    )
    return Response(PersonagemSerializer(personagens, many=True).data)


@extend_schema(
    methods=["GET"],
    operation_id="listar_minhas_campanhas",
    responses=CampanhaPerfilSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_campanhas(request):
    campanhas = (
        Campanha.objects.filter(Q(mestre=request.user) | Q(jogadores=request.user))
        .distinct()
        .select_related("mestre")
        .prefetch_related("jogadores", "moderadores", "personagens__usuario", "sistemas")
        .order_by("-atualizado_em")
    )
    return Response(CampanhaPerfilSerializer(campanhas, many=True, context={"request": request}).data)


@extend_schema(
    methods=["GET"],
    operation_id="listar_meus_poderes",
    responses=PoderUsuarioSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_poder_usuario",
    request=PoderUsuarioSerializer,
    responses=PoderUsuarioSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def me_poderes(request):

    if request.method == "GET":
        poderes = PoderUsuario.objects.filter(usuario=request.user)
        return Response(PoderUsuarioSerializer(poderes, many=True).data)

    serializer = PoderUsuarioSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save(usuario=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(methods=["GET"], operation_id="detalhar_poder_usuario", responses=PoderUsuarioSerializer)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_poder_usuario",
    request=PoderUsuarioSerializer,
    responses=PoderUsuarioSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_poder_usuario",
    request=PoderUsuarioSerializer,
    responses=PoderUsuarioSerializer,
)
@extend_schema(methods=["DELETE"], operation_id="remover_poder_usuario", responses=None)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def me_poder_detalhe(request, pk):

    try:
        poder = PoderUsuario.objects.get(pk=pk)

    except PoderUsuario.DoesNotExist:
        return Response({"erro": "Poder não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    # `PoderUsuario` tem `usuario`: o ramo de dono do `IsOwnerOrAdmin` já
    # decide sozinho (só o dono, ou superuser) — nenhuma regra nova.
    check_object_permission(request, poder)

    if request.method == "GET":
        return Response(PoderUsuarioSerializer(poder).data)

    if request.method == "DELETE":
        # As fichas que já copiaram este poder ficam com a cópia delas.
        poder.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = PoderUsuarioSerializer(poder, data=request.data, partial=request.method == "PATCH")

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Aba "Outros usuários" do perfil — só superusuário.
#
# Antes, `GET /personagem/` e `GET /campanha/` devolviam TUDO do banco para o
# superusuário, e as listas "minhas" dele viravam a lista do sistema inteiro.
# O perfil agora separa as duas coisas: as abas pessoais usam `/me/...`
# (sempre só o que é dele) e o que é dos outros vem daqui, com o dono de
# cada item — sem ele, uma lista de 300 fichas não diz de quem é cada uma.
# ---------------------------------------------------------------------------

def _exige_superusuario(request):
    if not request.user.is_superuser:
        return Response(
            {"erro": "Disponível apenas para superusuários."},
            status=status.HTTP_403_FORBIDDEN
        )
    return None


@extend_schema(
    methods=["GET"],
    operation_id="listar_personagens_de_outros_usuarios",
    responses=PersonagemDeOutroSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def outros_personagens(request):
    negado = _exige_superusuario(request)
    if negado:
        return negado

    personagens = (
        Personagem.objects.exclude(usuario=request.user)
        .select_related("usuario")
        .prefetch_related("campanhas", "sistemas")
        .order_by("-atualizado_em")
    )
    return Response(PersonagemDeOutroSerializer(personagens, many=True).data)


@extend_schema(
    methods=["GET"],
    operation_id="listar_campanhas_de_outros_usuarios",
    responses=CampanhaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def outras_campanhas(request):
    negado = _exige_superusuario(request)
    if negado:
        return negado

    campanhas = (
        Campanha.objects.exclude(Q(mestre=request.user) | Q(jogadores=request.user))
        .distinct()
        .select_related("mestre")
        .prefetch_related("jogadores", "moderadores", "personagens__usuario", "sistemas")
        .order_by("-atualizado_em")
    )
    return Response(CampanhaSerializer(campanhas, many=True).data)
