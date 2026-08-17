from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from Personagem.models import Personagem
from Personagem.serializers import PersonagemSerializer

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

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
from Usuario.permissions import check_object_permission, pode_criar_ou_excluir, usuario_pode_ver_objeto
from .serializers import (
    CampanhaSerializer,
    NPCSerializer,
    RelacaoNPCSerializer,
    LocalSerializer,
    OrganizacaoSerializer,
    MembroOrganizacaoSerializer,
    MapaSerializer,
    SessaoSerializer,
    MissaoSerializer,
    EventoSerializer,
    NotaSerializer,
    campanhas_do_objeto_notavel,
)


# ---------------------------------------------------------------------------
# Campanha (views originais, sem alterações de comportamento)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_campanhas",
    responses=CampanhaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_campanha",
    request=CampanhaSerializer,
    responses=CampanhaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def campanhas(request):

    if request.method == "GET":

        if request.user.is_superuser:
            campanhas = Campanha.objects.all()

        else:
            campanhas = Campanha.objects.filter(
                Q(mestre=request.user) |
                Q(jogadores=request.user)
            ).distinct()

        serializer = CampanhaSerializer(
            campanhas,
            many=True
        )

        return Response(serializer.data)


    elif request.method == "POST":

        serializer = CampanhaSerializer(
            data=request.data
        )

        if serializer.is_valid():

            campanha = serializer.save(
                mestre=request.user
            )

            campanha.jogadores.add(
                request.user
            )

            return Response(
                CampanhaSerializer(campanha).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

@extend_schema(
    methods=["GET"],
    operation_id="detalhar_campanha",
    responses=CampanhaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_campanha",
    request=CampanhaSerializer,
    responses=CampanhaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_campanha",
    request=CampanhaSerializer,
    responses=CampanhaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_campanha",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def campanha(request, pk):

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, campanha)

    if request.method == "GET":

        serializer = CampanhaSerializer(campanha)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = CampanhaSerializer(
            campanha,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == "PATCH":

        serializer = CampanhaSerializer(
            campanha,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == "DELETE":

        campanha.delete()

        return Response(
            {"mensagem": "Campanha removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


@extend_schema(
    methods=["POST"],
    operation_id="entrar_campanha",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "codigo": {
                    "type": "string"
                }
            },
            "required": ["codigo"]
        }
    },
    responses=CampanhaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def entrar_campanha(request):

    codigo = request.data.get("codigo")

    if not codigo:
        return Response(
            {"erro": "Informe o código da campanha."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        campanha = Campanha.objects.get(codigo=codigo.upper())

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if campanha.jogadores.filter(pk=request.user.pk).exists():
        return Response(
            {"erro": "Você já participa desta campanha."},
            status=status.HTTP_400_BAD_REQUEST
        )

    campanha.jogadores.add(request.user)

    return Response(
        CampanhaSerializer(campanha).data,
        status=status.HTTP_200_OK
    )

# AUDIT FIX: `manage.py spectacular` falhava com "unable to guess
# serializer" nesta view (ela lê `request.data` diretamente, sem
# serializer). Declarar `request`/`responses` explicitamente resolve o
# erro na geração do schema OpenAPI sem alterar o comportamento da view.
@extend_schema(
    methods=["POST"],
    operation_id="adicionar_personagens_campanha",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "personagens": {
                    "type": "array",
                    "items": {"type": "integer"},
                }
            },
        }
    },
    responses=CampanhaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def adicionar_personagens(request, pk):

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not campanha.jogadores.filter(pk=request.user.pk).exists():
        return Response(
            {"erro": "Você não participa desta campanha."},
            status=status.HTTP_403_FORBIDDEN
        )

    ids = request.data.get("personagens", [])

    personagens = Personagem.objects.filter(
        id__in=ids,
        usuario=request.user
    )

    campanha.personagens.add(*personagens)

    return Response(
        CampanhaSerializer(campanha).data,
        status=status.HTTP_200_OK
    )

# AUDIT FIX: mesma razão de `adicionar_personagens_campanha` acima — esta
# view não recebe corpo de requisição, então só precisa de `responses`
# explícito para o gerador de schema parar de falhar.
@extend_schema(
    methods=["POST"],
    operation_id="sair_campanha",
    request=None,
    responses={200: {"type": "object", "properties": {"mensagem": {"type": "string"}}}},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sair_campanha(request, pk):

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if campanha.mestre == request.user:
        return Response(
            {
                "erro": (
                    "O mestre não pode sair da campanha. "
                    "Exclua a campanha ou transfira a mestria."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    campanha.personagens.remove(
        *campanha.personagens.filter(usuario=request.user)
    )

    campanha.jogadores.remove(request.user)

    return Response(
        {"mensagem": "Você saiu da campanha com sucesso."},
        status=status.HTTP_200_OK
    )

@extend_schema(
    methods=["DELETE"],
    operation_id="remover_personagem_campanha",
    responses=None,
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remover_personagem(request, pk, personagem_pk):

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not campanha.jogadores.filter(pk=request.user.pk).exists():
        return Response(
            {"erro": "Você não participa desta campanha."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        personagem = Personagem.objects.get(
            pk=personagem_pk,
            usuario=request.user
        )

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not campanha.personagens.filter(pk=personagem.pk).exists():
        return Response(
            {"erro": "Este personagem não está na campanha."},
            status=status.HTTP_400_BAD_REQUEST
        )

    campanha.personagens.remove(personagem)

    return Response(
        {"mensagem": "Personagem removido da campanha com sucesso."},
        status=status.HTTP_200_OK
    )

@extend_schema(
    methods=["GET"],
    operation_id="listar_personagens_disponiveis",
    responses=PersonagemSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def personagens_disponiveis(request, pk):

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )


    if not campanha.jogadores.filter(
        pk=request.user.pk
    ).exists():

        return Response(
            {
                "erro": "Você não participa desta campanha."
            },
            status=status.HTTP_403_FORBIDDEN
        )


    personagens = Personagem.objects.filter(
        usuario=request.user
    ).exclude(
        campanhas=campanha
    )


    serializer = PersonagemSerializer(
        personagens,
        many=True
    )

    return Response(
        serializer.data
    )


# ---------------------------------------------------------------------------
# Helpers comuns às views "de mundo" abaixo (NPC, Local, Organizacao, ...)
# ---------------------------------------------------------------------------

def _busca_campanha_do_participante(request, pk):
    """
    Busca a campanha e garante que o usuário logado participa dela (como
    mestre ou jogador). Retorna (campanha, None) em caso de sucesso, ou
    (None, Response) com o erro já pronto para ser devolvido pela view.
    """
    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return None, Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    e_participante = (
        request.user.is_superuser
        or campanha.mestre == request.user
        or campanha.jogadores.filter(pk=request.user.pk).exists()
    )

    if not e_participante:
        return None, Response(
            {"erro": "Você não participa desta campanha."},
            status=status.HTTP_403_FORBIDDEN
        )

    return campanha, None


def _filtra_visiveis(request, campanha, queryset):
    """
    Mestre (e superuser) enxergam tudo; jogador só enxerga registros com
    visivel_para_jogadores=True.
    """
    if request.user.is_superuser or campanha.mestre == request.user:
        return queryset

    return queryset.filter(visivel_para_jogadores=True)


def _exige_mestre(request, campanha):
    """
    Retorna uma Response de erro se o usuário não puder criar/excluir
    recursos "de mundo" desta campanha (só mestre ou superuser podem).
    """
    if not pode_criar_ou_excluir(request, campanha):
        return Response(
            {"erro": "Apenas o mestre da campanha pode fazer isso."},
            status=status.HTTP_403_FORBIDDEN
        )

    return None


def _resolve_notavel_object(content_type_model, object_id):
    """
    Resolve o objeto real referenciado por uma Nota a partir do nome do
    model (ex.: "npc") e do id — o mesmo par usado como `content_type`/
    `object_id`. Retorna (content_type, objeto); `content_type` é None se o
    nome do model não existir, `objeto` é None se o id não existir (ou o
    valor não for um número válido).

    Usado tanto para checar permissão de leitura de notas de um objeto
    (reaproveitando `check_object_permission`, a mesma regra de
    visivel_para_jogadores usada para o objeto em si) quanto na criação de
    uma nota nova.
    """
    try:
        content_type = ContentType.objects.get(model=content_type_model)

    except ContentType.DoesNotExist:
        return None, None

    modelo = content_type.model_class()

    try:
        objeto = modelo.objects.get(pk=object_id)

    except (modelo.DoesNotExist, ValueError, TypeError):
        return content_type, None

    return content_type, objeto


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_npcs",
    responses=NPCSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_npc",
    request=NPCSerializer,
    responses=NPCSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def npc_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        npcs = _filtra_visiveis(
            request, campanha,
            campanha.npcs.all()
            .prefetch_related(
                "organizacoes_lideradas", "membroorganizacao_set__organizacao",
                "relacoes_com_outros_npcs__npc"
            )
            .order_by("nome")
        )

        serializer = NPCSerializer(npcs, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = NPCSerializer(
            data=request.data,
            context={"campanha": campanha}
        )

        if serializer.is_valid():
            npc = serializer.save(campanha=campanha)

            return Response(
                NPCSerializer(npc).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_npc",
    responses=NPCSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_npc",
    request=NPCSerializer,
    responses=NPCSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_npc",
    request=NPCSerializer,
    responses=NPCSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_npc",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def npc_detalhe(request, npc_pk):

    try:
        npc = (
            NPC.objects.select_related("campanha")
            .prefetch_related(
                "organizacoes_lideradas", "membroorganizacao_set__organizacao",
                "relacoes_com_outros_npcs__npc"
            )
            .get(pk=npc_pk)
        )

    except NPC.DoesNotExist:
        return Response(
            {"erro": "NPC não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, npc)

    if request.method == "GET":

        return Response(NPCSerializer(npc).data)

    elif request.method == "PUT":

        serializer = NPCSerializer(
            npc, data=request.data, context={"campanha": npc.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = NPCSerializer(
            npc, data=request.data, partial=True, context={"campanha": npc.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, npc.campanha)

        if erro:
            return erro

        npc.delete()

        return Response(
            {"mensagem": "NPC removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# RelacaoNPC (aninhado em NPC)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_relacoes_npc",
    responses=RelacaoNPCSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_relacao_npc",
    request=RelacaoNPCSerializer,
    responses=RelacaoNPCSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def relacao_npc_lista(request, npc_pk):

    try:
        npc = NPC.objects.select_related("campanha").get(pk=npc_pk)

    except NPC.DoesNotExist:
        return Response(
            {"erro": "NPC não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, npc)

    if request.method == "GET":

        relacoes = npc.relacoes.all().order_by("id")

        return Response(RelacaoNPCSerializer(relacoes, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, npc.campanha)

        if erro:
            return erro

        serializer = RelacaoNPCSerializer(
            data=request.data, context={"npc": npc}
        )

        if serializer.is_valid():
            relacao = serializer.save(npc=npc)

            return Response(
                RelacaoNPCSerializer(relacao).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_relacao_npc",
    responses=RelacaoNPCSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_relacao_npc",
    request=RelacaoNPCSerializer,
    responses=RelacaoNPCSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_relacao_npc",
    request=RelacaoNPCSerializer,
    responses=RelacaoNPCSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_relacao_npc",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def relacao_npc_detalhe(request, relacao_pk):

    try:
        relacao = RelacaoNPC.objects.select_related("npc__campanha").get(
            pk=relacao_pk
        )

    except RelacaoNPC.DoesNotExist:
        return Response(
            {"erro": "Relação não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, relacao)

    if request.method == "GET":

        return Response(RelacaoNPCSerializer(relacao).data)

    elif request.method == "PUT":

        serializer = RelacaoNPCSerializer(
            relacao, data=request.data, context={"npc": relacao.npc}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = RelacaoNPCSerializer(
            relacao, data=request.data, partial=True, context={"npc": relacao.npc}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, relacao.npc.campanha)

        if erro:
            return erro

        relacao.delete()

        return Response(
            {"mensagem": "Relação removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_locais",
    responses=LocalSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_local",
    request=LocalSerializer,
    responses=LocalSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def local_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        locais = _filtra_visiveis(
            request, campanha,
            campanha.locais.all()
            .prefetch_related("npcs_localizados", "organizacoes_sede", "missoes", "mapas", "eventos")
            .order_by("nome")
        )

        return Response(LocalSerializer(locais, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = LocalSerializer(data=request.data)

        if serializer.is_valid():
            local = serializer.save(campanha=campanha)

            return Response(
                LocalSerializer(local).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_local",
    responses=LocalSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_local",
    request=LocalSerializer,
    responses=LocalSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_local",
    request=LocalSerializer,
    responses=LocalSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_local",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def local_detalhe(request, local_pk):

    try:
        local = (
            Local.objects.select_related("campanha")
            .prefetch_related("npcs_localizados", "organizacoes_sede", "missoes", "mapas", "eventos")
            .get(pk=local_pk)
        )

    except Local.DoesNotExist:
        return Response(
            {"erro": "Local não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, local)

    if request.method == "GET":

        return Response(LocalSerializer(local).data)

    elif request.method == "PUT":

        serializer = LocalSerializer(local, data=request.data, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = LocalSerializer(local, data=request.data, partial=True, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, local.campanha)

        if erro:
            return erro

        local.delete()

        return Response(
            {"mensagem": "Local removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_organizacoes",
    responses=OrganizacaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_organizacao",
    request=OrganizacaoSerializer,
    responses=OrganizacaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def organizacao_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        organizacoes = _filtra_visiveis(
            request, campanha, campanha.organizacoes.all().prefetch_related("eventos").order_by("nome")
        )

        return Response(OrganizacaoSerializer(organizacoes, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = OrganizacaoSerializer(
            data=request.data, context={"campanha": campanha}
        )

        if serializer.is_valid():
            organizacao = serializer.save(campanha=campanha)

            return Response(
                OrganizacaoSerializer(organizacao).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_organizacao",
    responses=OrganizacaoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_organizacao",
    request=OrganizacaoSerializer,
    responses=OrganizacaoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_organizacao",
    request=OrganizacaoSerializer,
    responses=OrganizacaoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_organizacao",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def organizacao_detalhe(request, organizacao_pk):

    try:
        organizacao = Organizacao.objects.select_related("campanha").prefetch_related("eventos").get(
            pk=organizacao_pk
        )

    except Organizacao.DoesNotExist:
        return Response(
            {"erro": "Organização não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, organizacao)

    if request.method == "GET":

        return Response(OrganizacaoSerializer(organizacao).data)

    elif request.method == "PUT":

        serializer = OrganizacaoSerializer(
            organizacao, data=request.data, context={"campanha": organizacao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = OrganizacaoSerializer(
            organizacao, data=request.data, partial=True,
            context={"campanha": organizacao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, organizacao.campanha)

        if erro:
            return erro

        organizacao.delete()

        return Response(
            {"mensagem": "Organização removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# MembroOrganizacao (aninhado em Organizacao)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_membros_organizacao",
    responses=MembroOrganizacaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_membro_organizacao",
    request=MembroOrganizacaoSerializer,
    responses=MembroOrganizacaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def membro_organizacao_lista(request, organizacao_pk):

    try:
        organizacao = Organizacao.objects.select_related("campanha").get(
            pk=organizacao_pk
        )

    except Organizacao.DoesNotExist:
        return Response(
            {"erro": "Organização não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, organizacao)

    if request.method == "GET":

        membros = organizacao.membros.all().order_by("id")

        return Response(MembroOrganizacaoSerializer(membros, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, organizacao.campanha)

        if erro:
            return erro

        serializer = MembroOrganizacaoSerializer(
            data=request.data, context={"organizacao": organizacao}
        )

        if serializer.is_valid():
            membro = serializer.save(organizacao=organizacao)

            return Response(
                MembroOrganizacaoSerializer(membro).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["DELETE"],
    operation_id="remover_membro_organizacao",
    responses=None,
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def membro_organizacao_detalhe(request, membro_pk):

    try:
        membro = MembroOrganizacao.objects.select_related("organizacao__campanha").get(
            pk=membro_pk
        )

    except MembroOrganizacao.DoesNotExist:
        return Response(
            {"erro": "Membro não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    erro = _exige_mestre(request, membro.organizacao.campanha)

    if erro:
        return erro

    membro.delete()

    return Response(
        {"mensagem": "Membro removido da organização com sucesso."},
        status=status.HTTP_204_NO_CONTENT
    )


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_mapas",
    responses=MapaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_mapa",
    request=MapaSerializer,
    responses=MapaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def mapa_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        mapas = _filtra_visiveis(
            request, campanha, campanha.mapas.all().order_by("nome")
        )

        return Response(MapaSerializer(mapas, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = MapaSerializer(data=request.data, context={"campanha": campanha})

        if serializer.is_valid():
            mapa = serializer.save(campanha=campanha)

            return Response(
                MapaSerializer(mapa).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_mapa",
    responses=MapaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_mapa",
    request=MapaSerializer,
    responses=MapaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_mapa",
    request=MapaSerializer,
    responses=MapaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_mapa",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def mapa_detalhe(request, mapa_pk):

    try:
        mapa = Mapa.objects.select_related("campanha").get(pk=mapa_pk)

    except Mapa.DoesNotExist:
        return Response(
            {"erro": "Mapa não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, mapa)

    if request.method == "GET":

        return Response(MapaSerializer(mapa).data)

    elif request.method == "PUT":

        serializer = MapaSerializer(
            mapa, data=request.data, context={"campanha": mapa.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = MapaSerializer(
            mapa, data=request.data, partial=True, context={"campanha": mapa.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, mapa.campanha)

        if erro:
            return erro

        mapa.delete()

        return Response(
            {"mensagem": "Mapa removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_sessoes",
    responses=SessaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_sessao",
    request=SessaoSerializer,
    responses=SessaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def sessao_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        sessoes = _filtra_visiveis(
            request, campanha, campanha.sessoes.all().order_by("-numero")
        )

        return Response(SessaoSerializer(sessoes, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = SessaoSerializer(data=request.data, context={"campanha": campanha})

        if serializer.is_valid():
            sessao = serializer.save(campanha=campanha)

            return Response(
                SessaoSerializer(sessao).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_sessao",
    responses=SessaoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_sessao",
    request=SessaoSerializer,
    responses=SessaoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_sessao",
    request=SessaoSerializer,
    responses=SessaoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_sessao",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def sessao_detalhe(request, sessao_pk):

    try:
        sessao = Sessao.objects.select_related("campanha").get(pk=sessao_pk)

    except Sessao.DoesNotExist:
        return Response(
            {"erro": "Sessão não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, sessao)

    if request.method == "GET":

        return Response(SessaoSerializer(sessao).data)

    elif request.method == "PUT":

        serializer = SessaoSerializer(
            sessao, data=request.data, context={"campanha": sessao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = SessaoSerializer(
            sessao, data=request.data, partial=True, context={"campanha": sessao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, sessao.campanha)

        if erro:
            return erro

        sessao.delete()

        return Response(
            {"mensagem": "Sessão removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Missao
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_missoes",
    responses=MissaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_missao",
    request=MissaoSerializer,
    responses=MissaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def missao_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        missoes = _filtra_visiveis(
            request, campanha, campanha.missoes.all().order_by("titulo")
        )

        return Response(MissaoSerializer(missoes, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = MissaoSerializer(data=request.data, context={"campanha": campanha})

        if serializer.is_valid():
            missao = serializer.save(campanha=campanha)

            return Response(
                MissaoSerializer(missao).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_missao",
    responses=MissaoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_missao",
    request=MissaoSerializer,
    responses=MissaoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_missao",
    request=MissaoSerializer,
    responses=MissaoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_missao",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def missao_detalhe(request, missao_pk):

    try:
        missao = Missao.objects.select_related("campanha").get(pk=missao_pk)

    except Missao.DoesNotExist:
        return Response(
            {"erro": "Missão não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, missao)

    if request.method == "GET":

        return Response(MissaoSerializer(missao).data)

    elif request.method == "PUT":

        serializer = MissaoSerializer(
            missao, data=request.data, context={"campanha": missao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = MissaoSerializer(
            missao, data=request.data, partial=True, context={"campanha": missao.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, missao.campanha)

        if erro:
            return erro

        missao.delete()

        return Response(
            {"mensagem": "Missão removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_eventos",
    responses=EventoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_evento",
    request=EventoSerializer,
    responses=EventoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def evento_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        eventos = _filtra_visiveis(
            request, campanha, campanha.eventos.all().prefetch_related("locais", "organizacoes").order_by("titulo")
        )

        return Response(EventoSerializer(eventos, many=True).data)

    elif request.method == "POST":

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = EventoSerializer(data=request.data, context={"campanha": campanha})

        if serializer.is_valid():
            evento = serializer.save(campanha=campanha)

            return Response(
                EventoSerializer(evento).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_evento",
    responses=EventoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_evento",
    request=EventoSerializer,
    responses=EventoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_evento",
    request=EventoSerializer,
    responses=EventoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_evento",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def evento_detalhe(request, evento_pk):

    try:
        evento = Evento.objects.select_related("campanha").prefetch_related("locais", "organizacoes").get(pk=evento_pk)

    except Evento.DoesNotExist:
        return Response(
            {"erro": "Evento não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, evento)

    if request.method == "GET":

        return Response(EventoSerializer(evento).data)

    elif request.method == "PUT":

        serializer = EventoSerializer(
            evento, data=request.data, context={"campanha": evento.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = EventoSerializer(
            evento, data=request.data, partial=True, context={"campanha": evento.campanha, "request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        erro = _exige_mestre(request, evento.campanha)

        if erro:
            return erro

        evento.delete()

        return Response(
            {"mensagem": "Evento removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Nota (genérica — não está aninhada em Campanha, pois pode apontar para
# qualquer objeto "notável" dentro de qualquer campanha do usuário)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_notas",
    responses=NotaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_nota",
    request=NotaSerializer,
    responses=NotaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def nota_lista(request):

    if request.method == "GET":

        content_type_param = request.query_params.get("content_type")
        object_id_param = request.query_params.get("object_id")
        campanha_param = request.query_params.get("campanha")

        if content_type_param and object_id_param:
            # Notas são PÚBLICAS para toda a mesa: quem pode VER o objeto
            # (mestre sempre; jogador conforme visivel_para_jogadores)
            # também pode ver todas as notas escritas sobre ele por
            # qualquer participante — não só as próprias. Reaproveita a
            # mesma checagem de permissão usada para o objeto em si.
            content_type, objeto = _resolve_notavel_object(content_type_param, object_id_param)

            if content_type is None:
                return Response(
                    {"erro": "Tipo de objeto inválido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if objeto is None:
                return Response(
                    {"erro": "Objeto não encontrado."},
                    status=status.HTTP_404_NOT_FOUND
                )

            check_object_permission(request, objeto)

            notas = Nota.objects.filter(
                content_type=content_type, object_id=object_id_param
            ).select_related("usuario", "personagem").order_by("-atualizado_em")

            return Response(NotaSerializer(notas, many=True).data)

        elif campanha_param:
            # "Minhas Notas": só as que EU escrevi, sobre qualquer objeto
            # desta campanha (índice pessoal — diferente do painel acima,
            # que é público). Como Nota não tem uma FK direta para
            # Campanha, resolvemos isso coletando, para cada tipo de
            # objeto "notável" que tem campanha (direta ou via
            # personagem), os ids que pertencem a esta campanha, e
            # filtrando por (content_type, object_id) nessa lista.
            try:
                campanha_id = int(campanha_param)

            except (TypeError, ValueError):
                return Response(
                    {"erro": "O parâmetro `campanha` precisa ser um número."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            notas = Nota.objects.filter(usuario=request.user).select_related("usuario", "personagem").order_by("-atualizado_em")

            modelos_com_campanha = [Campanha, NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento]
            filtro_por_tipo = Q(pk__in=[])

            for modelo in modelos_com_campanha:
                content_type = ContentType.objects.get_for_model(modelo)

                if modelo is Campanha:
                    ids = [campanha_id] if Campanha.objects.filter(pk=campanha_id).exists() else []
                else:
                    ids = list(modelo.objects.filter(campanha_id=campanha_id).values_list("pk", flat=True))

                if ids:
                    filtro_por_tipo |= Q(content_type=content_type, object_id__in=ids)

            personagem_content_type = ContentType.objects.get_for_model(Personagem)
            personagem_ids = list(
                Personagem.objects.filter(campanhas__id=campanha_id).values_list("pk", flat=True)
            )

            if personagem_ids:
                filtro_por_tipo |= Q(content_type=personagem_content_type, object_id__in=personagem_ids)

            notas = notas.filter(filtro_por_tipo)

            return Response(NotaSerializer(notas, many=True).data)

        return Response(
            {"erro": "Informe `content_type`+`object_id` (notas de um objeto) ou `campanha` (suas notas na campanha)."},
            status=status.HTTP_400_BAD_REQUEST
        )

    elif request.method == "POST":

        content_type_param = request.data.get("content_type")
        object_id_param = request.data.get("object_id")

        if content_type_param and object_id_param:
            # Qualquer participante da campanha pode CRIAR uma nota em
            # qualquer objeto que consiga VER — as permissões de EDIÇÃO do
            # objeto (`editavel_para_jogadores`) não entram aqui; notas são
            # como comentários, independentes de quem pode editar a ficha.
            # `usuario_pode_ver_objeto` é a mesma regra de visibilidade do
            # GET (mestre sempre; jogador conforme `visivel_para_jogadores`),
            # mas sem depender do método HTTP da requisição atual — ao
            # contrário de `check_object_permission`, que trataria este
            # POST como uma tentativa de EDITAR o objeto e bloquearia
            # qualquer jogador, mesmo um com `editavel_para_jogadores=True`.
            _, objeto = _resolve_notavel_object(content_type_param, object_id_param)

            if objeto is not None and not usuario_pode_ver_objeto(request.user, objeto):
                return Response(
                    {"erro": "Você não tem permissão para ver este objeto."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # Se `objeto` for None aqui, deixamos o NotaSerializer.validate()
            # abaixo devolver o erro de "objeto não encontrado" de forma
            # consistente com o resto da validação de campos.

        serializer = NotaSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            nota = serializer.save(usuario=request.user)

            return Response(
                NotaSerializer(nota).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_nota",
    responses=NotaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_nota",
    request=NotaSerializer,
    responses=NotaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_nota",
    request=NotaSerializer,
    responses=NotaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_nota",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def nota_detalhe(request, pk):

    try:
        nota = Nota.objects.select_related("usuario", "personagem", "content_type").get(pk=pk)

    except Nota.DoesNotExist:
        return Response(
            {"erro": "Nota não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    e_autor = nota.usuario == request.user or request.user.is_superuser

    # Resolve o objeto anotado uma única vez — usado tanto para checar
    # visibilidade (GET) quanto para saber se quem está pedindo é o MESTRE
    # da campanha do objeto (que agora também pode editar/excluir notas de
    # qualquer jogador, além do próprio autor).
    _, objeto = _resolve_notavel_object(nota.content_type.model, nota.object_id)
    e_mestre_do_objeto = False

    if objeto is not None and not e_autor:
        campanhas_do_objeto = campanhas_do_objeto_notavel(objeto)
        e_mestre_do_objeto = any(c.mestre_id == request.user.id for c in campanhas_do_objeto)

    if request.method == "GET":

        # Leitura é pública para quem pode ver o objeto ao qual a nota se
        # refere (mesma regra de visivel_para_jogadores usada no objeto em
        # si) — não só para o autor da nota.
        if not e_autor and not e_mestre_do_objeto:

            if objeto is None:
                # O objeto referenciado não existe mais (foi excluído) —
                # sem ele não há como checar visibilidade, então a nota
                # "órfã" volta a ser só do autor.
                return Response(
                    {"erro": "Você não tem permissão para acessar esta nota."},
                    status=status.HTTP_403_FORBIDDEN
                )

            check_object_permission(request, objeto)

        return Response(NotaSerializer(nota).data)

    # PUT/PATCH/DELETE: o autor (ou superuser) sempre pode; o MESTRE da
    # campanha do objeto anotado também pode (ex.: moderar um comentário
    # inadequado) — mas nenhum outro jogador.
    if not e_autor and not e_mestre_do_objeto:
        return Response(
            {"erro": "Você só pode editar ou remover as suas próprias notas (ou, sendo mestre, notas desta campanha)."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "PUT":

        serializer = NotaSerializer(nota, data=request.data, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = NotaSerializer(nota, data=request.data, partial=True, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        nota.delete()

        return Response(
            {"mensagem": "Nota removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )