from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cloudinary.models import CloudinaryField

from Midia.services import copiar_ajuste
from Personagem.models import Arma, Armadura, Item, Personagem
from Personagem.serializers import ArmaSerializer, ArmaduraSerializer, ItemSerializer, PersonagemSerializer

from django.contrib.contenttypes.models import ContentType
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q

from .models import (
    Campanha,
    NPC,
    FichaPreset,
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
    CategoriaLoja,
    ProdutoLoja,
    TransacaoLoja,
    AnuncioComercioLivre,
    modelos_vendaveis,
)
from Usuario.permissions import check_object_permission, pode_criar_ou_excluir, usuario_pode_ver_objeto
from .escudo import montar_snapshot
from . import comercio, loja
from .serializers import (
    CampanhaSerializer,
    NPCSerializer,
    FichaPresetSerializer,
    LocalSerializer,
    OrganizacaoSerializer,
    MapaSerializer,
    SessaoSerializer,
    MissaoSerializer,
    EventoSerializer,
    NotaSerializer,
    PastaSerializer,
    TipoConexaoSerializer,
    ConexaoSerializer,
    DocumentoSerializer,
    ImagemSerializer,
    CanvaSerializer,
    CriaturaSerializer,
    DivindadeSerializer,
    RacaSerializer,
    ItemCampanhaSerializer,
    ArmaCampanhaSerializer,
    ArmaduraCampanhaSerializer,
    CategoriaLojaSerializer,
    ProdutoLojaSerializer,
    TransacaoLojaSerializer,
    AnuncioComercioLivreSerializer,
    campanhas_do_objeto_notavel,
    conexoes_de_entidade,
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

            # A Loja já nasce com as prateleiras usuais (Armas, Armaduras,
            # Itens Gerais) — ver `loja.CATEGORIAS_PADRAO`.
            loja.criar_categorias_padrao(campanha)

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
    """
    Remove (desvincula) um Personagem desta Campanha.

    FIX (permissão): antes só o DONO do personagem conseguia se remover
    (o `.get(pk=personagem_pk, usuario=request.user)` original excluía
    silenciosamente qualquer personagem que não fosse do usuário logado,
    devolvendo 404 mesmo quando o personagem existia). Isso impedia o
    mestre de remover o personagem de outro jogador da própria campanha.

    Regra atual: o MESTRE (ou superuser) pode remover o personagem de
    QUALQUER jogador; um jogador comum só pode remover os PRÓPRIOS
    personagens — igual ao comportamento anterior para não-mestres.
    """

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    e_mestre = pode_criar_ou_excluir(request, campanha)

    if not e_mestre and not campanha.jogadores.filter(pk=request.user.pk).exists():
        return Response(
            {"erro": "Você não participa desta campanha."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        personagem = Personagem.objects.get(pk=personagem_pk)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not e_mestre and personagem.usuario_id != request.user.id:
        return Response(
            {"erro": "Você só pode remover os seus próprios personagens."},
            status=status.HTTP_403_FORBIDDEN
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
    methods=["DELETE"],
    operation_id="remover_jogador_campanha",
    responses=None,
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remover_jogador(request, pk, usuario_pk):
    """
    NOVO endpoint: o mestre remove (expulsa) um jogador da campanha —
    antes só existia a autorremoção (`sair_campanha`). Só o mestre (ou
    superuser) pode chamar isso, via `_exige_mestre`.

    Os personagens deste jogador vinculados a esta campanha também são
    desvinculados (mesmo comportamento já usado em `sair_campanha`), para
    não deixar personagens "órfãos" de um jogador que não está mais na
    mesa.
    """

    try:
        campanha = Campanha.objects.get(pk=pk)

    except Campanha.DoesNotExist:
        return Response(
            {"erro": "Campanha não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    try:
        usuario_pk_int = int(usuario_pk)
    except (TypeError, ValueError):
        return Response(
            {"erro": "Usuário inválido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if usuario_pk_int == campanha.mestre_id:
        return Response(
            {
                "erro": (
                    "O mestre não pode remover a si mesmo. "
                    "Exclua a campanha ou transfira a mestria."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if not campanha.jogadores.filter(pk=usuario_pk_int).exists():
        return Response(
            {"erro": "Este usuário não participa desta campanha."},
            status=status.HTTP_400_BAD_REQUEST
        )

    campanha.personagens.remove(
        *campanha.personagens.filter(usuario_id=usuario_pk_int)
    )

    campanha.jogadores.remove(usuario_pk_int)

    return Response(
        {"mensagem": "Jogador removido da campanha com sucesso."},
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
    Reaproveitado também por `remover_jogador` acima.
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
            .prefetch_related("organizacoes_lideradas")
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
            .prefetch_related("organizacoes_lideradas")
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
# Conexões de uma entidade específica (seção 11: "GET /.../npcs/12/conexoes/"
# ou equivalente). Fina camada em cima de `conexoes_de_entidade`
# (serializers.py), reaproveitada por um endpoint por tipo de entidade
# abaixo, no mesmo padrão de duplicação já usado pelo resto do arquivo
# (list/detalhe por model) em vez de uma view genérica parametrizada.
# ---------------------------------------------------------------------------

def _conexoes_da_entidade_view(request, modelo, pk, select_related=None):
    qs = modelo.objects.select_related(*(select_related or ["campanha"]))

    try:
        entidade = qs.get(pk=pk)

    except modelo.DoesNotExist:
        return Response(
            {"erro": f"{modelo.__name__} não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, entidade)

    return Response(conexoes_de_entidade(entidade))


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_npc",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def npc_conexoes(request, npc_pk):
    return _conexoes_da_entidade_view(request, NPC, npc_pk, select_related=["campanha"])


# ---------------------------------------------------------------------------
# FichaPreset — predefinições de ficha de NPC, por usuário (não por
# campanha: servem para reaproveitar a mesma ficha em qualquer campanha do
# usuário). Recurso "plano", no mesmo molde de `Personagem/views.py`
# (dono = usuário autenticado), não no molde aninhado-por-campanha do resto
# deste arquivo — por isso não usa `_busca_campanha_do_participante`/
# `check_object_permission` (pensados para objetos ligados a uma Campanha).
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_fichas_predefinidas",
    responses=FichaPresetSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_ficha_predefinida",
    request=FichaPresetSerializer,
    responses=FichaPresetSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ficha_preset_lista(request):

    if request.method == "GET":

        presets = FichaPreset.objects.filter(usuario=request.user)

        serializer = FichaPresetSerializer(presets, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = FichaPresetSerializer(data=request.data)

        if serializer.is_valid():
            preset = serializer.save(usuario=request.user)

            return Response(
                FichaPresetSerializer(preset).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_ficha_predefinida",
    responses=FichaPresetSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_ficha_predefinida",
    request=FichaPresetSerializer,
    responses=FichaPresetSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_ficha_predefinida",
    responses=None,
)
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def ficha_preset_detalhe(request, preset_pk):

    try:
        preset = FichaPreset.objects.get(pk=preset_pk, usuario=request.user)

    except FichaPreset.DoesNotExist:
        # 404 (não 403) mesmo quando o preset existe mas é de outro
        # usuário — não revela a existência de predefinições alheias.
        return Response(
            {"erro": "Predefinição não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":

        return Response(FichaPresetSerializer(preset).data)

    elif request.method == "PATCH":

        serializer = FichaPresetSerializer(preset, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        preset.delete()

        return Response(
            {"mensagem": "Predefinição removida com sucesso."},
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
# Conexões de Local / Organizacao (mesmo padrão de `npc_conexoes` acima)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_local",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def local_conexoes(request, local_pk):
    return _conexoes_da_entidade_view(request, Local, local_pk, select_related=["campanha"])


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_organizacao",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def organizacao_conexoes(request, organizacao_pk):
    return _conexoes_da_entidade_view(request, Organizacao, organizacao_pk, select_related=["campanha"])


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


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_mapa",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mapa_conexoes(request, mapa_pk):
    return _conexoes_da_entidade_view(request, Mapa, mapa_pk, select_related=["campanha"])


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


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_sessao",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sessao_conexoes(request, sessao_pk):
    return _conexoes_da_entidade_view(request, Sessao, sessao_pk, select_related=["campanha"])


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


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_missao",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missao_conexoes(request, missao_pk):
    return _conexoes_da_entidade_view(request, Missao, missao_pk, select_related=["campanha"])


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


@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes_evento",
    responses={200: {"type": "array", "items": {"type": "object"}}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def evento_conexoes(request, evento_pk):
    return _conexoes_da_entidade_view(request, Evento, evento_pk, select_related=["campanha"])


# ---------------------------------------------------------------------------
# Pasta — árvore de organização estilo Obsidian (seção 3 da refatoração)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_pastas",
    responses=PastaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_pasta",
    request=PastaSerializer,
    responses=PastaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def pasta_lista(request, pk):
    """
    Lista/cria pastas de uma campanha. A lista é sempre "flat" (não
    aninhada): cada Pasta já traz `pasta_pai`, e é responsabilidade do
    cliente (futuramente, a UI estilo Obsidian) montar a árvore a partir
    disso — o mesmo princípio usado pelo restante da API (sem aninhar
    payloads grandes).
    """

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        pastas = campanha.pastas.all().order_by("pasta_pai_id", "ordem", "nome")

        return Response(PastaSerializer(pastas, many=True).data)

    elif request.method == "POST":

        # Só o mestre organiza a árvore de pastas (seção 12: "o mestre da
        # campanha deve possuir controle completo sobre... criação de
        # pastas").
        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = PastaSerializer(
            data=request.data, context={"campanha": campanha}
        )

        if serializer.is_valid():
            pasta = serializer.save(campanha=campanha)

            return Response(
                PastaSerializer(pasta).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_pasta",
    responses=PastaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_pasta",
    request=PastaSerializer,
    responses=PastaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_pasta",
    request=PastaSerializer,
    responses=PastaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_pasta",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def pasta_detalhe(request, pasta_pk):
    """
    GET/PUT/PATCH cobrem leitura, renomeação e reordenação (`ordem`).
    Mover para outra pasta-pai também é um PATCH normal aqui (`pasta_pai`)
    — `pasta_mover` abaixo existe como um atalho semântico dedicado (seção
    11: "mover pasta" listado como capacidade própria), mas não é a única
    forma de mover.
    """

    try:
        pasta = Pasta.objects.select_related("campanha", "pasta_pai").get(pk=pasta_pk)

    except Pasta.DoesNotExist:
        return Response(
            {"erro": "Pasta não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, pasta)

    if request.method == "GET":

        return Response(PastaSerializer(pasta).data)

    # Pastas são geridas só pelo mestre (leitura já liberada pela
    # `check_object_permission` acima; escrita/exclusão exigem mestre
    # explicitamente, porque Pasta não tem `editavel_para_jogadores` — a
    # permission genérica trataria PUT/PATCH como bloqueados por padrão,
    # mas sermos explícitos aqui deixa a regra clara e à prova de mudanças
    # futuras no helper genérico).
    erro = _exige_mestre(request, pasta.campanha)

    if erro:
        return erro

    if request.method == "PUT":

        serializer = PastaSerializer(
            pasta, data=request.data, context={"campanha": pasta.campanha}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = PastaSerializer(
            pasta, data=request.data, partial=True, context={"campanha": pasta.campanha}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        pasta.delete()

        return Response(
            {"mensagem": "Pasta removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


@extend_schema(
    methods=["POST"],
    operation_id="mover_pasta",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "pasta_pai": {"type": "integer", "nullable": True},
                "ordem": {"type": "integer"},
            },
        }
    },
    responses=PastaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pasta_mover(request, pasta_pk):
    """
    Atalho dedicado para mover uma pasta (mudar `pasta_pai` e/ou `ordem`)
    — mesma validação de mesma-campanha e anti-ciclo do PATCH em
    `pasta_detalhe`, só que como uma ação nomeada, mais próxima do que uma
    futura UI drag-and-drop estilo Obsidian chamaria.
    """

    try:
        pasta = Pasta.objects.select_related("campanha").get(pk=pasta_pk)

    except Pasta.DoesNotExist:
        return Response(
            {"erro": "Pasta não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    erro = _exige_mestre(request, pasta.campanha)

    if erro:
        return erro

    dados = {}

    if "pasta_pai" in request.data:
        dados["pasta_pai"] = request.data["pasta_pai"]

    if "ordem" in request.data:
        dados["ordem"] = request.data["ordem"]

    serializer = PastaSerializer(
        pasta, data=dados, partial=True, context={"campanha": pasta.campanha}
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# TipoConexao — vocabulário compartilhado de tipos de conexão
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_tipos_conexao",
    responses=TipoConexaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_tipo_conexao",
    request=TipoConexaoSerializer,
    responses=TipoConexaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tipo_conexao_lista(request):
    """
    TipoConexao não é escopado por campanha (é um vocabulário
    compartilhado, ex.: "Filho de", "Membro de") — por isso este endpoint
    não é aninhado em `/campanha/<pk>/...`. Qualquer usuário autenticado
    pode listar e cadastrar novos tipos (é só um rótulo reutilizável, sem
    dado sensível de nenhuma campanha específica).
    """

    if request.method == "GET":

        return Response(TipoConexaoSerializer(TipoConexao.objects.all(), many=True).data)

    elif request.method == "POST":

        serializer = TipoConexaoSerializer(data=request.data)

        if serializer.is_valid():
            tipo = serializer.save()

            return Response(
                TipoConexaoSerializer(tipo).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_tipo_conexao",
    responses=TipoConexaoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_tipo_conexao",
    request=TipoConexaoSerializer,
    responses=TipoConexaoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_tipo_conexao",
    request=TipoConexaoSerializer,
    responses=TipoConexaoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_tipo_conexao",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def tipo_conexao_detalhe(request, tipo_pk):

    try:
        tipo = TipoConexao.objects.get(pk=tipo_pk)

    except TipoConexao.DoesNotExist:
        return Response(
            {"erro": "Tipo de conexão não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":

        return Response(TipoConexaoSerializer(tipo).data)

    elif request.method == "PUT":

        serializer = TipoConexaoSerializer(tipo, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = TipoConexaoSerializer(tipo, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        # `on_delete=PROTECT` em Conexao.tipo já impede a exclusão no
        # nível do banco se houver Conexoes usando este tipo; devolvemos
        # um erro amigável em vez de deixar vazar um IntegrityError.
        if tipo.conexoes.exists():
            return Response(
                {"erro": "Este tipo de conexão está em uso e não pode ser removido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Só superuser remove tipos (evita que qualquer jogador apague um
        # tipo em uso por outra campanha que não a sua).
        if not request.user.is_superuser:
            return Response(
                {"erro": "Apenas um administrador pode remover tipos de conexão."},
                status=status.HTTP_403_FORBIDDEN
            )

        tipo.delete()

        return Response(
            {"mensagem": "Tipo de conexão removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )


# ---------------------------------------------------------------------------
# Conexao — relacionamento genérico entre entidades de uma Campanha
# (substitui RelacaoNPC e MembroOrganizacao — seções 6 a 10 da refatoração)
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"],
    operation_id="listar_conexoes",
    responses=ConexaoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_conexao",
    request=ConexaoSerializer,
    responses=ConexaoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def conexao_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":

        conexoes = (
            campanha.conexoes.all()
            .select_related("tipo", "tipo__inverso", "entidade1_tipo", "entidade2_tipo")
            .order_by("-criado_em")
        )

        # Mestre (e superuser) veem tudo; jogador só vê conexões em que AS
        # DUAS entidades envolvidas são visíveis para ele — reaproveita a
        # mesma regra de visibilidade (`usuario_pode_ver_objeto`) já usada
        # para o objeto em si e para Notas, em vez de uma lógica própria.
        if not (request.user.is_superuser or campanha.mestre == request.user):
            conexoes = [
                conexao for conexao in conexoes
                if (conexao.entidade1 is None or usuario_pode_ver_objeto(request.user, conexao.entidade1))
                and (conexao.entidade2 is None or usuario_pode_ver_objeto(request.user, conexao.entidade2))
            ]

        return Response(ConexaoSerializer(conexoes, many=True).data)

    elif request.method == "POST":

        # Só o mestre cria conexões (seção 12: controle completo do
        # mestre sobre "criação de conexões").
        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = ConexaoSerializer(
            data=request.data, context={"campanha": campanha}
        )

        if serializer.is_valid():
            conexao = serializer.save(campanha=campanha)

            return Response(
                ConexaoSerializer(conexao).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    operation_id="detalhar_conexao",
    responses=ConexaoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_conexao",
    request=ConexaoSerializer,
    responses=ConexaoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_conexao",
    request=ConexaoSerializer,
    responses=ConexaoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_conexao",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def conexao_detalhe(request, conexao_pk):

    try:
        conexao = Conexao.objects.select_related(
            "campanha", "tipo", "tipo__inverso", "entidade1_tipo", "entidade2_tipo"
        ).get(pk=conexao_pk)

    except Conexao.DoesNotExist:
        return Response(
            {"erro": "Conexão não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":

        # Leitura: mestre sempre vê; jogador só se enxergar AMBAS as
        # entidades (mesma regra usada em `conexao_lista`).
        e_mestre = request.user.is_superuser or conexao.campanha.mestre == request.user

        if not e_mestre:
            e_jogador = conexao.campanha.jogadores.filter(pk=request.user.pk).exists()

            pode_ver = (
                (conexao.entidade1 is None or usuario_pode_ver_objeto(request.user, conexao.entidade1))
                and (conexao.entidade2 is None or usuario_pode_ver_objeto(request.user, conexao.entidade2))
            )

            if not e_jogador or not pode_ver:
                return Response(
                    {"erro": "Você não tem permissão para acessar este recurso."},
                    status=status.HTTP_403_FORBIDDEN
                )

        return Response(ConexaoSerializer(conexao).data)

    # Escrita/exclusão: só o mestre (seção 12).
    erro = _exige_mestre(request, conexao.campanha)

    if erro:
        return erro

    if request.method == "PUT":

        serializer = ConexaoSerializer(
            conexao, data=request.data, context={"campanha": conexao.campanha}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = ConexaoSerializer(
            conexao, data=request.data, partial=True, context={"campanha": conexao.campanha}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        conexao.delete()

        return Response(
            {"mensagem": "Conexão removida com sucesso."},
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

            modelos_com_campanha = [
                Campanha, NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento,
                Documento, Imagem, Canva, Criatura, Divindade, Raca,
            ]
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


# ---------------------------------------------------------------------------
# Busca global dentro de uma campanha (layout estilo Obsidian — coluna de
# pesquisa da árvore). Procura o termo no NOME e no `conteudo` (Markdown)
# de cada tipo de entidade + no nome dos Personagens. Respeita a mesma
# regra de visibilidade das listagens: jogador só acha o que é visível.
# ---------------------------------------------------------------------------

_BUSCA_MODELOS = [
    ("npc", NPC, "nome"),
    ("local", Local, "nome"),
    ("organizacao", Organizacao, "nome"),
    ("mapa", Mapa, "nome"),
    ("sessao", Sessao, "titulo"),
    ("missao", Missao, "titulo"),
    ("evento", Evento, "titulo"),
    ("documento", Documento, "nome"),
    ("imagem", Imagem, "nome"),
    ("canva", Canva, "nome"),
    ("criatura", Criatura, "nome"),
    ("divindade", Divindade, "nome"),
    ("raca", Raca, "nome"),
    ("itemcampanha", ItemCampanha, "nome"),
    ("armacampanha", ArmaCampanha, "nome"),
    ("armaduracampanha", ArmaduraCampanha, "nome"),
]


def _snippet(texto, termo, contexto=60):
    """Um trecho curto do `conteudo` ao redor do primeiro match (ou o
    começo do texto, se o match foi só no nome)."""
    if not texto:
        return ""

    i = texto.lower().find(termo.lower())

    if i == -1:
        return texto[:120].strip().replace("\n", " ")

    ini = max(0, i - contexto)
    fim = min(len(texto), i + len(termo) + contexto)
    trecho = texto[ini:fim].strip().replace("\n", " ")

    return ("…" if ini > 0 else "") + trecho + ("…" if fim < len(texto) else "")


@extend_schema(
    methods=["GET"],
    operation_id="buscar_na_campanha",
    responses=None,
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def busca_campanha(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    termo = (request.query_params.get("q") or "").strip()

    if len(termo) < 2:
        return Response([])

    resultados = []

    for tipo, modelo, campo_nome in _BUSCA_MODELOS:

        qs = _filtra_visiveis(
            request,
            campanha,
            modelo.objects.filter(campanha=campanha).filter(
                Q(**{f"{campo_nome}__icontains": termo}) | Q(conteudo__icontains=termo)
            ),
        )[:20]

        for obj in qs:
            resultados.append({
                "tipo": tipo,
                "id": obj.pk,
                "nome": getattr(obj, campo_nome, "") or "",
                "snippet": _snippet(getattr(obj, "conteudo", "") or "", termo),
            })

    for personagem in campanha.personagens.filter(nome__icontains=termo)[:20]:
        resultados.append({
            "tipo": "personagem",
            "id": personagem.pk,
            "nome": personagem.nome,
            "snippet": "",
        })

    return Response(resultados)


@extend_schema(
    methods=["GET"],
    operation_id="escudo_campanha",
    responses=None,
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def escudo_campanha(request, pk):
    """
    Carga completa do Escudo do Mestre numa requisição só (ver
    `escudo.montar_snapshot`). Depois dela, o cliente só recebe eventos
    incrementais pelo WebSocket — esta rota volta a ser chamada apenas numa
    reconexão, para cobrir o que possa ter mudado enquanto estava offline.
    Mesma regra de acesso de antes (qualquer participante da campanha: o
    Escudo sempre foi visível para a mesa toda, não só para o mestre).
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    return Response(montar_snapshot(campanha))


# ---------------------------------------------------------------------------
# "Fazer uma cópia" — duplicação de entidade de mundo e de pasta (com todo o
# seu conteúdo). Reaproveita `_BUSCA_MODELOS` (tipo -> Modelo -> campo-título)
# e os serializers já existentes (toda a validação de mesma-campanha, número
# de sessão único, etc. continua valendo, pois a criação passa pelo
# serializer). Só o mestre pode duplicar (mesma regra de criar).
# ---------------------------------------------------------------------------

_SERIALIZER_POR_TIPO = {
    "npc": NPCSerializer,
    "local": LocalSerializer,
    "organizacao": OrganizacaoSerializer,
    "mapa": MapaSerializer,
    "sessao": SessaoSerializer,
    "missao": MissaoSerializer,
    "evento": EventoSerializer,
    "documento": DocumentoSerializer,
    "imagem": ImagemSerializer,
    "canva": CanvaSerializer,
    "criatura": CriaturaSerializer,
    "divindade": DivindadeSerializer,
    "raca": RacaSerializer,
    "itemcampanha": ItemCampanhaSerializer,
    "armacampanha": ArmaCampanhaSerializer,
    "armaduracampanha": ArmaduraCampanhaSerializer,
}

# tipo -> (Modelo, SerializerClass, campo_titulo)
_DUP = {
    tipo: (modelo, _SERIALIZER_POR_TIPO[tipo], campo_titulo)
    for tipo, modelo, campo_titulo in _BUSCA_MODELOS
}


def _nome_copia_unico(modelo, campanha, campo, base, pasta_pai=None):
    """
    "<base> (cópia)", com sufixo numérico se já existir — respeita os
    UniqueConstraint de Organizacao (campanha, nome) e Pasta (campanha,
    pasta_pai, nome). Inofensivo para os tipos sem restrição de nome.
    """
    base = (base or "").strip() or "Sem nome"
    candidato = f"{base} (cópia)"
    n = 2
    while True:
        filtro = {"campanha": campanha, campo: candidato}
        if modelo._meta.model_name == "pasta":
            filtro["pasta_pai"] = pasta_pai
        if not modelo.objects.filter(**filtro).exists():
            return candidato
        candidato = f"{base} (cópia {n})"
        n += 1


def _dados_copia(origem):
    """
    Campos escalares/relacionais concretos de `origem` prontos para
    recriar o objeto via serializer. Ignora pk, campanha (vem do save),
    timestamps, campos não-editáveis e imagens (CloudinaryField) — a cópia
    nasce sem imagem, o mestre reanexa se quiser. Inclui M2M como lista de
    ids (ex.: Evento.locais / Evento.organizacoes).
    """
    ignorar = {"id", "campanha", "criado_em", "atualizado_em"}
    dados = {}
    for f in origem._meta.fields:
        if f.name in ignorar or f.auto_created or not f.editable:
            continue
        if isinstance(f, CloudinaryField):
            continue
        dados[f.name] = getattr(origem, f.attname)  # FK -> _id, demais -> valor
    for f in origem._meta.many_to_many:
        dados[f.name] = list(getattr(origem, f.name).values_list("pk", flat=True))
    return dados


def _duplica_entidade(campanha, tipo, origem, pasta_id="__keep__"):
    modelo, serializer_cls, campo_titulo = _DUP[tipo]

    dados = _dados_copia(origem)
    dados[campo_titulo] = _nome_copia_unico(
        modelo, campanha, campo_titulo, getattr(origem, campo_titulo)
    )

    if pasta_id != "__keep__":
        dados["pasta"] = pasta_id

    # Sessao.numero é único por campanha — a cópia recebe o próximo número.
    if tipo == "sessao":
        ultimo = modelo.objects.filter(campanha=campanha).order_by("-numero").first()
        dados["numero"] = (ultimo.numero if ultimo else 0) + 1

    serializer = serializer_cls(data=dados, context={"campanha": campanha})
    serializer.is_valid(raise_exception=True)
    return serializer.save(campanha=campanha)


@extend_schema(
    methods=["POST"],
    operation_id="duplicar_entidade",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string"},
                "id": {"type": "integer"},
            },
            "required": ["tipo", "id"],
        }
    },
    responses=None,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def duplicar_entidade(request, pk):
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    tipo = request.data.get("tipo")
    obj_id = request.data.get("id")

    if tipo not in _DUP:
        return Response(
            {"erro": "Tipo de entidade inválido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    modelo, serializer_cls, _ = _DUP[tipo]

    try:
        origem = modelo.objects.get(pk=obj_id, campanha=campanha)
    except (modelo.DoesNotExist, ValueError, TypeError):
        return Response(
            {"erro": "Entidade não encontrada nesta campanha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        novo = _duplica_entidade(campanha, tipo, origem)
    except ValidationError as exc:
        return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    return Response(serializer_cls(novo).data, status=status.HTTP_201_CREATED)


def _duplica_pasta_recursivo(campanha, origem, novo_pai_id, primeiro=False):
    pai = Pasta.objects.filter(pk=novo_pai_id).first() if novo_pai_id else None

    nome = (
        _nome_copia_unico(Pasta, campanha, "nome", origem.nome, pasta_pai=pai)
        if primeiro
        else origem.nome
    )

    nova = Pasta.objects.create(
        campanha=campanha,
        nome=nome,
        pasta_pai=pai,
        icone=origem.icone,
        cor=origem.cor,
        ordem=origem.ordem,
        visivel_para_jogadores=origem.visivel_para_jogadores,
        editavel_para_jogadores=origem.editavel_para_jogadores,
    )

    for tipo, (modelo, _serializer, _campo) in _DUP.items():
        for ent in modelo.objects.filter(campanha=campanha, pasta=origem):
            try:
                _duplica_entidade(campanha, tipo, ent, pasta_id=nova.id)
            except ValidationError:
                # Uma entidade problemática não deve abortar a cópia inteira.
                pass

    for sub in origem.subpastas.all():
        _duplica_pasta_recursivo(campanha, sub, nova.id)

    return nova


@extend_schema(methods=["POST"], operation_id="duplicar_pasta", responses=PastaSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def duplicar_pasta(request, pasta_pk):
    try:
        pasta = Pasta.objects.select_related("campanha").get(pk=pasta_pk)
    except Pasta.DoesNotExist:
        return Response(
            {"erro": "Pasta não encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    erro = _exige_mestre(request, pasta.campanha)

    if erro:
        return erro

    nova = _duplica_pasta_recursivo(
        pasta.campanha, pasta, pasta.pasta_pai_id, primeiro=True
    )

    return Response(PastaSerializer(nova).data, status=status.HTTP_201_CREATED)

# ---------------------------------------------------------------------------
# Entidades de mundo novas — CRUD gerado a partir de uma fábrica única
#
# Os 7 tipos antigos têm uma dupla `<tipo>_lista` / `<tipo>_detalhe` escrita
# à mão (cada uma com validações próprias). As 6 entidades novas
# (Documento, Imagem, Canva, Criatura, Divindade, Raca) compartilham
# EXATAMENTE o mesmo fluxo — participante lista, mestre cria/exclui,
# `check_object_permission` no detalhe —, então repetir ~130 linhas seis
# vezes só criaria seis lugares para o mesmo bug. A fábrica abaixo devolve
# as três views (lista, detalhe, conexões) já decoradas, com os mesmos
# `operation_id` que o resto da API expõe ao drf-spectacular.
# ---------------------------------------------------------------------------

def _crud_mundo(tipo, plural, modelo, serializer_cls, rotulo):

    def lista(request, pk):
        campanha, erro = _busca_campanha_do_participante(request, pk)

        if erro:
            return erro

        if request.method == "GET":
            # A ordenação vem do Meta do model (`ordem`, depois `nome`) —
            # ver EntidadeMundo em models.py.
            itens = _filtra_visiveis(request, campanha, modelo.objects.filter(campanha=campanha))

            return Response(serializer_cls(itens, many=True).data)

        erro = _exige_mestre(request, campanha)

        if erro:
            return erro

        serializer = serializer_cls(
            data=request.data, context={"campanha": campanha, "request": request}
        )

        if serializer.is_valid():
            obj = serializer.save(campanha=campanha)

            return Response(serializer_cls(obj).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def detalhe(request, obj_pk):
        try:
            obj = modelo.objects.select_related("campanha").get(pk=obj_pk)

        except modelo.DoesNotExist:
            return Response(
                {"erro": f"{rotulo} não encontrado(a)."},
                status=status.HTTP_404_NOT_FOUND
            )

        check_object_permission(request, obj)

        if request.method == "GET":
            return Response(serializer_cls(obj).data)

        if request.method in ("PUT", "PATCH"):
            serializer = serializer_cls(
                obj,
                data=request.data,
                partial=request.method == "PATCH",
                context={"campanha": obj.campanha, "request": request},
            )

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # DELETE — só o mestre, igual aos demais recursos de mundo.
        erro = _exige_mestre(request, obj.campanha)

        if erro:
            return erro

        obj.delete()

        return Response(
            {"mensagem": f"{rotulo} removido(a) com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

    def conexoes(request, obj_pk):
        return _conexoes_da_entidade_view(request, modelo, obj_pk, select_related=["campanha"])

    lista.__name__ = f"{tipo}_lista"
    detalhe.__name__ = f"{tipo}_detalhe"
    conexoes.__name__ = f"{tipo}_conexoes"

    # `permission_classes` precisa ser aplicado ANTES de `api_view` (no
    # empilhamento de decoradores, é o de baixo) — o DRF valida essa ordem.
    lista = api_view(["GET", "POST"])(permission_classes([IsAuthenticated])(lista))
    lista = extend_schema(
        methods=["GET"], operation_id=f"listar_{plural}", responses=serializer_cls(many=True)
    )(lista)
    lista = extend_schema(
        methods=["POST"], operation_id=f"criar_{tipo}", request=serializer_cls, responses=serializer_cls
    )(lista)

    detalhe = api_view(["GET", "PUT", "PATCH", "DELETE"])(permission_classes([IsAuthenticated])(detalhe))
    detalhe = extend_schema(methods=["GET"], operation_id=f"detalhar_{tipo}", responses=serializer_cls)(detalhe)
    detalhe = extend_schema(
        methods=["PUT"], operation_id=f"atualizar_{tipo}", request=serializer_cls, responses=serializer_cls
    )(detalhe)
    detalhe = extend_schema(
        methods=["PATCH"], operation_id=f"atualizar_parcial_{tipo}", request=serializer_cls, responses=serializer_cls
    )(detalhe)
    detalhe = extend_schema(methods=["DELETE"], operation_id=f"remover_{tipo}", responses=None)(detalhe)

    conexoes = api_view(["GET"])(permission_classes([IsAuthenticated])(conexoes))
    conexoes = extend_schema(
        methods=["GET"],
        operation_id=f"listar_conexoes_{tipo}",
        responses={200: {"type": "array", "items": {"type": "object"}}},
    )(conexoes)

    return lista, detalhe, conexoes


documento_lista, documento_detalhe, documento_conexoes = _crud_mundo(
    "documento", "documentos", Documento, DocumentoSerializer, "Documento"
)
imagem_lista, imagem_detalhe, imagem_conexoes = _crud_mundo(
    "imagem", "imagens", Imagem, ImagemSerializer, "Imagem"
)
canva_lista, canva_detalhe, canva_conexoes = _crud_mundo(
    "canva", "canvas", Canva, CanvaSerializer, "Canva"
)
criatura_lista, criatura_detalhe, criatura_conexoes = _crud_mundo(
    "criatura", "criaturas", Criatura, CriaturaSerializer, "Criatura"
)
divindade_lista, divindade_detalhe, divindade_conexoes = _crud_mundo(
    "divindade", "divindades", Divindade, DivindadeSerializer, "Divindade"
)
raca_lista, raca_detalhe, raca_conexoes = _crud_mundo(
    "raca", "racas", Raca, RacaSerializer, "Raça"
)
itemcampanha_lista, itemcampanha_detalhe, itemcampanha_conexoes = _crud_mundo(
    "itemcampanha", "itens_campanha", ItemCampanha, ItemCampanhaSerializer, "Item"
)
armacampanha_lista, armacampanha_detalhe, armacampanha_conexoes = _crud_mundo(
    "armacampanha", "armas_campanha", ArmaCampanha, ArmaCampanhaSerializer, "Arma"
)
armaduracampanha_lista, armaduracampanha_detalhe, armaduracampanha_conexoes = _crud_mundo(
    "armaduracampanha", "armaduras_campanha", ArmaduraCampanha, ArmaduraCampanhaSerializer, "Armadura"
)


# ---------------------------------------------------------------------------
# Cópia equipamento da campanha -> ficha
#
# Mesmo contrato das cópias do app Sistema (`Sistema/views.py`): o item
# ORIGINAL nunca é tocado, a imagem vai por referência (mesmo public_id) com
# o enquadramento junto, e a ficha recebe uma linha nova e independente.
#
# A diferença é a checagem extra de escopo: além de poder editar a ficha, o
# personagem precisa PARTICIPAR da campanha dona do equipamento — sem isso,
# qualquer um com um id em mãos copiaria itens de uma campanha que não é
# sua. Jogador também só copia o que enxerga (`visivel_para_jogadores`).
# ---------------------------------------------------------------------------

_MODELO_EQUIPAMENTO = {
    "item": (ItemCampanha, "Item"),
    "arma": (ArmaCampanha, "Arma"),
    "armadura": (ArmaduraCampanha, "Armadura"),
}


def _copiar_equipamento_campanha(request, personagem_id, equipamento_id, tipo):
    modelo, rotulo = _MODELO_EQUIPAMENTO[tipo]

    try:
        personagem = Personagem.objects.get(pk=personagem_id)
    except Personagem.DoesNotExist:
        return Response({"erro": "Personagem não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    check_object_permission(request, personagem)

    try:
        origem = modelo.objects.select_related("campanha").get(pk=equipamento_id)
    except modelo.DoesNotExist:
        return Response({"erro": f"{rotulo} não encontrado(a)."}, status=status.HTTP_404_NOT_FOUND)

    # Copiar exige ENXERGAR o equipamento, não editá-lo — por isso
    # `usuario_pode_ver_objeto` (que ignora o método HTTP) e não
    # `check_object_permission`: esta requisição é um POST, e para a
    # permission um POST sobre um objeto de mundo existente é coisa de
    # mestre. A regra de visibilidade aplicada é a mesma das listagens
    # (mestre vê tudo; jogador só o que é `visivel_para_jogadores`).
    if not usuario_pode_ver_objeto(request.user, origem):
        return Response(
            {"erro": "Você não tem acesso a este equipamento."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not personagem.campanhas.filter(pk=origem.campanha_id).exists():
        return Response(
            {"erro": "Este personagem não participa da campanha deste equipamento."},
            status=status.HTTP_403_FORBIDDEN,
        )

    copia = loja.copiar_para_ficha(origem, personagem)

    return Response(
        loja.serializer_da_ficha(loja.classe_de(origem))(copia).data,
        status=status.HTTP_201_CREATED,
    )


@extend_schema(methods=["POST"], operation_id="copiar_item_campanha", request=None, responses=ItemSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_item_campanha(request, personagem_id, item_id):
    return _copiar_equipamento_campanha(request, personagem_id, item_id, "item")


@extend_schema(methods=["POST"], operation_id="copiar_arma_campanha", request=None, responses=ArmaSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_arma_campanha(request, personagem_id, arma_id):
    return _copiar_equipamento_campanha(request, personagem_id, arma_id, "arma")


@extend_schema(methods=["POST"], operation_id="copiar_armadura_campanha", request=None, responses=ArmaduraSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_armadura_campanha(request, personagem_id, armadura_id):
    return _copiar_equipamento_campanha(request, personagem_id, armadura_id, "armadura")


# ---------------------------------------------------------------------------
# Loja da campanha
#
# Categorias e produtos são administrados SÓ pelo mestre; os jogadores
# consomem a vitrine (`loja_vitrine`), que já vem com a seleção da rotação
# aplicada. Por isso a listagem de produtos é do mestre: ela mostra o
# estoque inteiro, inclusive o que está fora de venda — não é o que o
# jogador deve ver.
# ---------------------------------------------------------------------------

@extend_schema(
    methods=["GET"], operation_id="listar_categorias_loja", responses=CategoriaLojaSerializer(many=True)
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_categoria_loja",
    request=CategoriaLojaSerializer,
    responses=CategoriaLojaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def categoria_loja_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":
        categorias = _filtra_visiveis(request, campanha, campanha.categorias_loja.all())

        return Response(CategoriaLojaSerializer(categorias, many=True).data)

    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    serializer = CategoriaLojaSerializer(data=request.data, context={"campanha": campanha, "request": request})

    if serializer.is_valid():
        categoria = serializer.save(campanha=campanha)

        return Response(CategoriaLojaSerializer(categoria).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(methods=["GET"], operation_id="detalhar_categoria_loja", responses=CategoriaLojaSerializer)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_categoria_loja",
    request=CategoriaLojaSerializer,
    responses=CategoriaLojaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_categoria_loja",
    request=CategoriaLojaSerializer,
    responses=CategoriaLojaSerializer,
)
@extend_schema(methods=["DELETE"], operation_id="remover_categoria_loja", responses=None)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def categoria_loja_detalhe(request, categoria_pk):

    try:
        categoria = CategoriaLoja.objects.select_related("campanha").get(pk=categoria_pk)

    except CategoriaLoja.DoesNotExist:
        return Response({"erro": "Categoria não encontrada."}, status=status.HTTP_404_NOT_FOUND)

    check_object_permission(request, categoria)

    if request.method == "GET":
        return Response(CategoriaLojaSerializer(categoria).data)

    erro = _exige_mestre(request, categoria.campanha)

    if erro:
        return erro

    if request.method in ("PUT", "PATCH"):
        serializer = CategoriaLojaSerializer(
            categoria,
            data=request.data,
            partial=request.method == "PATCH",
            context={"campanha": categoria.campanha, "request": request},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Excluir a categoria NÃO exclui os produtos: eles continuam na loja,
    # só ficam sem prateleira (o M2M some junto com a categoria).
    categoria.delete()

    return Response({"mensagem": "Categoria removida com sucesso."}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(methods=["GET"], operation_id="listar_produtos_loja", responses=ProdutoLojaSerializer(many=True))
@extend_schema(
    methods=["POST"],
    operation_id="criar_produto_loja",
    request=ProdutoLojaSerializer,
    responses=ProdutoLojaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def produto_loja_lista(request, pk):

    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    # Gestão do estoque — inclusive o que está fora de venda. O jogador usa
    # `loja_vitrine`, que só mostra o que está à venda agora.
    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    if request.method == "GET":
        produtos = campanha.produtos_loja.select_related("content_type").prefetch_related("categorias")

        return Response(ProdutoLojaSerializer(produtos, many=True).data)

    serializer = ProdutoLojaSerializer(data=request.data, context={"campanha": campanha, "request": request})

    if serializer.is_valid():
        try:
            produto = serializer.save(campanha=campanha)
        except IntegrityError:
            # A UniqueConstraint (campanha, content_type, object_id) — dois
            # cliques no mesmo "Adicionar" chegam aqui.
            return Response(
                {"origem_id": ["Este equipamento já está na loja desta campanha."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ProdutoLojaSerializer(produto).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["POST"],
    operation_id="criar_produtos_loja_em_lote",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "produtos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "origem_tipo": {"type": "string"},
                            "origem_id": {"type": "integer"},
                            "preco": {"type": "string"},
                        },
                        "required": ["origem_tipo", "origem_id"],
                    },
                },
                "quantidade_disponivel": {"type": "integer", "nullable": True},
                "categorias": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["produtos"],
        }
    },
    responses=None,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def produto_loja_lote(request, pk):
    """
    Põe VÁRIOS equipamentos à venda de uma vez.

    Existe para o mestre montar a loja de uma tacada: selecionar trinta
    itens no catálogo e mandar um POST, em vez de trinta. `categorias` e
    `quantidade_disponivel` valem para todos; `preco` é por item (o padrão
    sugerido é o valor do próprio equipamento).

    Cada item entra no seu próprio savepoint: um equipamento inválido — ou
    já presente na loja — é REPORTADO e os outros são gravados. Abortar as
    trinta inserções porque uma esbarrou na UniqueConstraint seria pior
    para quem está montando a prateleira.
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    entradas = request.data.get("produtos")

    if not isinstance(entradas, list) or not entradas:
        return Response(
            {"produtos": ["Informe a lista de equipamentos a adicionar."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    comuns = {
        "quantidade_disponivel": request.data.get("quantidade_disponivel"),
        "categorias": request.data.get("categorias") or [],
    }

    criados, ignorados, erros = [], [], {}

    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue

        chave = f"{entrada.get('origem_tipo')}:{entrada.get('origem_id')}"
        dados = {**comuns, **entrada}

        serializer = ProdutoLojaSerializer(
            data=dados, context={"campanha": campanha, "request": request}
        )

        if not serializer.is_valid():
            erros[chave] = serializer.errors
            continue

        try:
            # Savepoint por item: o IntegrityError de um não desfaz os
            # anteriores nem impede os seguintes.
            with transaction.atomic():
                produto = serializer.save(campanha=campanha)
        except IntegrityError:
            ignorados.append(chave)
            continue

        criados.append(ProdutoLojaSerializer(produto).data)

    return Response(
        {"criados": criados, "ignorados": ignorados, "erros": erros},
        status=status.HTTP_201_CREATED if criados else status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(methods=["GET"], operation_id="detalhar_produto_loja", responses=ProdutoLojaSerializer)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_produto_loja",
    request=ProdutoLojaSerializer,
    responses=ProdutoLojaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_produto_loja",
    request=ProdutoLojaSerializer,
    responses=ProdutoLojaSerializer,
)
@extend_schema(methods=["DELETE"], operation_id="remover_produto_loja", responses=None)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def produto_loja_detalhe(request, produto_pk):

    try:
        produto = ProdutoLoja.objects.select_related("campanha", "content_type").get(pk=produto_pk)

    except ProdutoLoja.DoesNotExist:
        return Response({"erro": "Produto não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    erro = _exige_mestre(request, produto.campanha)

    if erro:
        return erro

    if request.method == "GET":
        return Response(ProdutoLojaSerializer(produto).data)

    if request.method in ("PUT", "PATCH"):
        serializer = ProdutoLojaSerializer(
            produto,
            data=request.data,
            partial=request.method == "PATCH",
            context={"campanha": produto.campanha, "request": request},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    produto.delete()

    return Response({"mensagem": "Produto removido da loja."}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(methods=["GET"], operation_id="vitrine_loja", responses=None)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def loja_vitrine(request, pk):
    """
    A loja pronta para exibir, com a rotação de cada categoria já aplicada
    pelo SERVIDOR — é o que garante que a mesa inteira vê a mesma seleção.
    `proxima_rotacao_em` diz quando ela muda, para o cliente agendar um
    único refetch em vez de ficar perguntando.
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    return Response(loja.montar_vitrine(campanha, request.user))


@extend_schema(methods=["GET"], operation_id="equipamentos_disponiveis_loja", responses=None)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def loja_disponiveis(request, pk):
    """
    O que o mestre PODE colocar à venda: os equipamentos das bibliotecas de
    regras da campanha mais os exclusivos dela — as mesmas seis origens que
    o serializer aceita, listadas com a mesma regra de escopo, para o
    formulário nunca oferecer algo que a validação recusaria.

    `ja_na_loja` evita o vaivém de tentar adicionar um item repetido.
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    erro = _exige_mestre(request, campanha)

    if erro:
        return erro

    sistemas_ids = list(campanha.sistemas.values_list("id", flat=True))

    objetos = []
    for modelo in modelos_vendaveis():
        if hasattr(modelo, "campanha"):
            objetos.extend(modelo.objects.filter(campanha=campanha))
        elif sistemas_ids:
            objetos.extend(modelo.objects.filter(sistema_id__in=sistemas_ids))

    ja_na_loja = {
        (ct.model, object_id)
        for ct, object_id in (
            (p.content_type, p.object_id)
            for p in campanha.produtos_loja.select_related("content_type")
        )
    }

    resumos = loja.resumos_de_origens(objetos)

    return Response([
        {**resumo, "ja_na_loja": chave in ja_na_loja}
        for chave, resumo in sorted(resumos.items(), key=lambda par: (par[1]["classe"], par[1]["nome"]))
    ])


# ---------------------------------------------------------------------------
# Compra na loja do mestre
# ---------------------------------------------------------------------------

def _personagem_da_compra(request, campanha):
    """
    Resolve e autoriza o personagem que vai comprar. Devolve
    (personagem, None) ou (None, Response).

    `check_object_permission` aqui é a regra certa (diferente da cópia da
    biblioteca, que é leitura): comprar ALTERA a ficha — desconta dinheiro e
    acrescenta item —, então quem pode fazer isso é o dono da ficha ou o
    mestre da mesa, exatamente o que a permission já define.
    """
    personagem_id = request.data.get("personagem")

    try:
        personagem = Personagem.objects.get(pk=personagem_id)
    except (Personagem.DoesNotExist, ValueError, TypeError):
        return None, Response({"personagem": ["Personagem não encontrado."]}, status=status.HTTP_400_BAD_REQUEST)

    check_object_permission(request, personagem)

    if not campanha.personagens.filter(pk=personagem.pk).exists():
        return None, Response(
            {"personagem": ["Este personagem não participa desta campanha."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return personagem, None


def _quantidade_pedida(request):
    try:
        quantidade = int(request.data.get("quantidade", 1))
    except (TypeError, ValueError):
        return None, Response({"quantidade": ["Quantidade inválida."]}, status=status.HTTP_400_BAD_REQUEST)

    if quantidade < 1:
        return None, Response(
            {"quantidade": ["A quantidade precisa ser pelo menos 1."]}, status=status.HTTP_400_BAD_REQUEST
        )

    return quantidade, None


@extend_schema(
    methods=["POST"],
    operation_id="comprar_produto_loja",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "personagem": {"type": "integer"},
                "quantidade": {"type": "integer"},
                "chave_idempotencia": {"type": "string"},
            },
            "required": ["personagem"],
        }
    },
    responses=TransacaoLojaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def comprar_produto_loja(request, produto_pk):
    """
    Compra de um produto da loja do mestre.

    Tudo o que pode dar errado é checado DENTRO da transação, com as linhas
    do produto e do personagem travadas (`select_for_update`): é o que
    impede dois cliques simultâneos de comprarem o mesmo último item ou de
    gastarem o mesmo dinheiro duas vezes. Fora da transação, entre o "tem
    saldo?" e o "desconta", cabe outra requisição inteira.

    A checagem de rotação não é decorativa: sem ela bastaria guardar o id de
    um produto e comprá-lo enquanto a rotação o esconde, o que esvaziaria a
    rotação como mecânica — e é exatamente o tipo de coisa que o cliente não
    pode decidir.
    """
    try:
        produto = ProdutoLoja.objects.select_related("campanha").get(pk=produto_pk)
    except ProdutoLoja.DoesNotExist:
        return Response({"erro": "Produto não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    campanha, erro = _busca_campanha_do_participante(request, produto.campanha_id)

    if erro:
        return erro

    personagem, erro = _personagem_da_compra(request, campanha)

    if erro:
        return erro

    quantidade, erro = _quantidade_pedida(request)

    if erro:
        return erro

    chave = (request.data.get("chave_idempotencia") or "").strip() or None

    if chave:
        # Retry de rede, duplo toque, reenvio depois de reconectar: a compra
        # já aconteceu, devolve a mesma transação em vez de cobrar de novo.
        ja_feita = TransacaoLoja.objects.filter(chave_idempotencia=chave).first()
        if ja_feita is not None:
            return Response(TransacaoLojaSerializer(ja_feita).data, status=status.HTTP_200_OK)

    try:
        with transaction.atomic():
            # `of=("self",)`: sem ele o Postgres travaria também a linha de
            # `django_content_type` trazida pelo JOIN — uma tabela
            # compartilhada por todo o projeto, que viraria ponto de
            # contenção de qualquer compra em qualquer campanha.
            produto = (
                ProdutoLoja.objects.select_for_update(of=("self",))
                .select_related("content_type")
                .get(pk=produto.pk)
            )
            personagem = Personagem.objects.select_for_update().get(pk=personagem.pk)

            origem = produto.origem

            if origem is None:
                return Response(
                    {"erro": "O equipamento deste produto não existe mais."},
                    status=status.HTTP_409_CONFLICT,
                )

            if not loja.produto_a_venda(produto, request.user, campanha):
                return Response(
                    {"erro": "Este produto não está à venda no momento."},
                    status=status.HTTP_409_CONFLICT,
                )

            if produto.quantidade_disponivel is not None and produto.quantidade_disponivel < quantidade:
                return Response(
                    {
                        "erro": "Não há essa quantidade disponível.",
                        "quantidade_disponivel": produto.quantidade_disponivel,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            total = produto.preco * quantidade

            # ATENÇÃO: daqui para cima só há LEITURA. Um `return` dentro de
            # `atomic()` não desfaz nada (não há exceção), então toda recusa
            # precisa acontecer ANTES da primeira gravação abaixo — se um dia
            # entrar uma validação nova, ela vem para cá, não para depois.
            if personagem.dinheiro < total:
                return Response(
                    {
                        "erro": "Dinheiro insuficiente.",
                        "necessario": str(total),
                        "disponivel": str(personagem.dinheiro),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            personagem.dinheiro = personagem.dinheiro - total
            personagem.save(update_fields=["dinheiro"])

            if produto.quantidade_disponivel is not None:
                produto.quantidade_disponivel -= quantidade
                produto.save(update_fields=["quantidade_disponivel"])

            item = loja.copiar_para_ficha(origem, personagem, quantidade)

            transacao = TransacaoLoja.objects.create(
                campanha=campanha,
                tipo="loja",
                comprador_personagem=personagem,
                produto=produto,
                nome_item=origem.nome,
                preco_unitario=produto.preco,
                quantidade=quantidade,
                total=total,
                chave_idempotencia=chave,
            )

    except IntegrityError:
        # Duas requisições com a MESMA chave chegaram juntas e a segunda
        # esbarrou no índice único: a compra da primeira vale.
        ja_feita = TransacaoLoja.objects.filter(chave_idempotencia=chave).first() if chave else None
        if ja_feita is not None:
            return Response(TransacaoLojaSerializer(ja_feita).data, status=status.HTTP_200_OK)
        raise

    return Response(
        {
            "transacao": TransacaoLojaSerializer(transacao).data,
            # A ficha e a vitrine se atualizam com o que volta daqui, sem
            # recarregar a página nem pedir tudo de novo.
            "item": loja.serializer_da_ficha(loja.classe_de(origem))(item).data,
            "dinheiro": str(personagem.dinheiro),
            "quantidade_disponivel": produto.quantidade_disponivel,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    methods=["GET"], operation_id="listar_transacoes_loja", responses=TransacaoLojaSerializer(many=True)
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transacao_loja_lista(request, pk):
    """
    Extrato da loja. O mestre vê a mesa inteira; o jogador vê só o que
    envolve os personagens dele.
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    transacoes = campanha.transacoes_loja.select_related(
        "comprador_personagem", "vendedor_personagem"
    )

    if not (request.user.is_superuser or campanha.mestre_id == request.user.pk):
        meus = list(campanha.personagens.filter(usuario=request.user).values_list("id", flat=True))
        transacoes = transacoes.filter(
            Q(comprador_personagem_id__in=meus) | Q(vendedor_personagem_id__in=meus)
        )

    return Response(TransacaoLojaSerializer(transacoes[:200], many=True).data)


# ---------------------------------------------------------------------------
# Comércio Livre
# ---------------------------------------------------------------------------

def _erro_comercio(exc):
    return Response({"erro": exc.mensagem}, status=exc.status)


@extend_schema(
    methods=["GET"], operation_id="listar_anuncios", responses=AnuncioComercioLivreSerializer(many=True)
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_anuncio",
    request=AnuncioComercioLivreSerializer,
    responses=AnuncioComercioLivreSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def anuncio_lista(request, pk):
    """
    GET: as ofertas ativas da campanha (é o que todo mundo na mesa vê).
    POST: o jogador põe um item do PRÓPRIO inventário à venda.

    `?meus=1` filtra para os anúncios dos personagens de quem está pedindo —
    é a visão "meus anúncios".
    """
    campanha, erro = _busca_campanha_do_participante(request, pk)

    if erro:
        return erro

    if request.method == "GET":
        anuncios = campanha.anuncios.filter(ativo=True).select_related(
            "vendedor_personagem", "item"
        )

        if request.query_params.get("meus") in ("1", "true", "True"):
            anuncios = anuncios.filter(vendedor_personagem__usuario=request.user)

        return Response(AnuncioComercioLivreSerializer(anuncios, many=True).data)

    try:
        item = Item.objects.select_related("personagem").get(pk=request.data.get("item"))
    except (Item.DoesNotExist, ValueError, TypeError):
        return Response({"item": ["Item não encontrado."]}, status=status.HTTP_400_BAD_REQUEST)

    # Vender ALTERA a ficha (o item sai do inventário), então a regra é a
    # mesma de editar: o dono, ou o mestre da mesa.
    check_object_permission(request, item)

    serializer = AnuncioComercioLivreSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        anuncio = comercio.anunciar(
            item,
            campanha=campanha,
            preco=serializer.validated_data.get("preco"),
            quantidade=serializer.validated_data.get("quantidade"),
        )
    except comercio.ErroComercio as exc:
        return _erro_comercio(exc)

    return Response(AnuncioComercioLivreSerializer(anuncio).data, status=status.HTTP_201_CREATED)


@extend_schema(methods=["GET"], operation_id="detalhar_anuncio", responses=AnuncioComercioLivreSerializer)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_anuncio",
    request=AnuncioComercioLivreSerializer,
    responses=AnuncioComercioLivreSerializer,
)
@extend_schema(methods=["DELETE"], operation_id="retirar_anuncio", responses=None)
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def anuncio_detalhe(request, anuncio_pk):
    """
    PATCH ajusta preço/quantidade; DELETE retira o item da venda (o anúncio
    é encerrado, não apagado — as transações continuam apontando para ele).
    """
    try:
        anuncio = AnuncioComercioLivre.objects.select_related(
            "campanha", "item", "vendedor_personagem"
        ).get(pk=anuncio_pk)
    except AnuncioComercioLivre.DoesNotExist:
        return Response({"erro": "Anúncio não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    campanha, erro = _busca_campanha_do_participante(request, anuncio.campanha_id)

    if erro:
        return erro

    if request.method == "GET":
        return Response(AnuncioComercioLivreSerializer(anuncio).data)

    # Mexer no anúncio é mexer no item — mesma permissão de editar a ficha.
    check_object_permission(request, anuncio.item)

    if request.method == "PATCH":
        serializer = AnuncioComercioLivreSerializer(anuncio, data=request.data, partial=True)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            atualizado = comercio.anunciar(
                anuncio.item,
                campanha=campanha,
                preco=serializer.validated_data.get("preco", anuncio.preco),
                quantidade=serializer.validated_data.get("quantidade", anuncio.quantidade),
            )
        except comercio.ErroComercio as exc:
            return _erro_comercio(exc)

        return Response(AnuncioComercioLivreSerializer(atualizado).data)

    comercio.retirar(anuncio.item)

    return Response({"mensagem": "Item retirado da venda."}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    methods=["POST"],
    operation_id="comprar_anuncio",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "personagem": {"type": "integer"},
                "quantidade": {"type": "integer"},
                "chave_idempotencia": {"type": "string"},
            },
            "required": ["personagem"],
        }
    },
    responses=TransacaoLojaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def comprar_anuncio(request, anuncio_pk):
    """
    Compra de um item anunciado por outro jogador. O dinheiro e o item
    trocam de mãos na MESMA transação, com as quatro linhas envolvidas
    travadas — ver `Campanha/comercio.py`.
    """
    try:
        anuncio = AnuncioComercioLivre.objects.select_related("campanha").get(pk=anuncio_pk)
    except AnuncioComercioLivre.DoesNotExist:
        return Response({"erro": "Anúncio não encontrado."}, status=status.HTTP_404_NOT_FOUND)

    campanha, erro = _busca_campanha_do_participante(request, anuncio.campanha_id)

    if erro:
        return erro

    comprador, erro = _personagem_da_compra(request, campanha)

    if erro:
        return erro

    quantidade, erro = _quantidade_pedida(request)

    if erro:
        return erro

    chave = (request.data.get("chave_idempotencia") or "").strip() or None

    if chave:
        ja_feita = TransacaoLoja.objects.filter(chave_idempotencia=chave).first()
        if ja_feita is not None:
            return Response(TransacaoLojaSerializer(ja_feita).data, status=status.HTTP_200_OK)

    try:
        transacao, item, anuncio = comercio.comprar(
            anuncio.pk, comprador, request.user, quantidade=quantidade, chave=chave
        )
    except comercio.ErroComercio as exc:
        return _erro_comercio(exc)
    except IntegrityError:
        ja_feita = TransacaoLoja.objects.filter(chave_idempotencia=chave).first() if chave else None
        if ja_feita is not None:
            return Response(TransacaoLojaSerializer(ja_feita).data, status=status.HTTP_200_OK)
        raise

    comprador.refresh_from_db()

    return Response(
        {
            "transacao": TransacaoLojaSerializer(transacao).data,
            "item": loja.serializer_da_ficha(comercio.classe_do_item(item))(item).data,
            "dinheiro": str(comprador.dinheiro),
            "anuncio": AnuncioComercioLivreSerializer(anuncio).data,
        },
        status=status.HTTP_201_CREATED,
    )
