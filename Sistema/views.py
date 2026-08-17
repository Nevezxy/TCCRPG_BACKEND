from django.shortcuts import render
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from Personagem.models import Arma, Armadura, Habilidade, Item, Personagem, Poder
from Sistema.models import *
from Sistema.serializers import *
from Personagem.serializers import ArmaSerializer, ArmaduraSerializer, HabilidadeSerializer, ItemSerializer, PoderSerializer
from Usuario.permissions import check_object_permission

@extend_schema(
    methods=["GET"],
    operation_id="listar_sistemas",
    responses=SistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sistema_lista(request):

    sistemas = Sistema.objects.all().order_by("nome")

    serializer = SistemaSerializer(
        sistemas,
        many=True
    )

    return Response(serializer.data)


@extend_schema(
    methods=["GET"],
    operation_id="listar_poderes_sistema",
    responses=PoderSistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def poder_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    poderes = PoderSistema.objects.filter(
        sistema=sistema
    ).order_by("tag", "nome")

    serializer = PoderSistemaSerializer(
        poderes,
        many=True
    )

    return Response(serializer.data)


@extend_schema(
    methods=["POST"],
    operation_id="copiar_poder_sistema",
    request=None,
    responses=PoderSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_poder_sistema(request, personagem_id, pk):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    try:
        poder_sistema = PoderSistema.objects.get(pk=pk)

    except PoderSistema.DoesNotExist:
        return Response(
            {"erro": "Poder da biblioteca não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    poder = Poder.objects.create(
        personagem=personagem,
        tag=poder_sistema.tag,
        nome=poder_sistema.nome,
        descricao=poder_sistema.descricao,
        custo=poder_sistema.custo,
    )

    serializer = PoderSerializer(poder)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )
    
@extend_schema(
    methods=["GET"],
    operation_id="listar_modificacoes",
    responses=ModificacaoSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def modificacao_lista(request):

    modificacoes = Modificacao.objects.all().order_by("nome")

    serializer = ModificacaoSerializer(
        modificacoes,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["GET"],
    operation_id="listar_grupos_armas",
    responses=GrupoArmasSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def grupo_arma_lista(request):

    grupos = GrupoArmas.objects.all().order_by("nome")

    serializer = GrupoArmasSerializer(
        grupos,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["GET"],
    operation_id="listar_regras_sistema",
    responses=RegraSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def regra_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    regras = Regra.objects.filter(
        sistema=sistema
    ).order_by("tag", "nome")

    serializer = RegraSerializer(
        regras,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["GET"],
    operation_id="listar_itens_sistema",
    responses=ItemSistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def item_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    itens = ItemSistema.objects.filter(
        sistema=sistema
    ).order_by("nome")

    serializer = ItemSistemaSerializer(
        itens,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["POST"],
    operation_id="copiar_item_sistema",
    request=None,
    responses=ItemSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_item_sistema(request, personagem_id, item_id):

    try:
        personagem = Personagem.objects.get(
            pk=personagem_id
        )

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(
        request,
        personagem
    )


    try:
        item_sistema = ItemSistema.objects.get(
            pk=item_id
        )

    except ItemSistema.DoesNotExist:
        return Response(
            {"erro": "Item não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )


    item = Item.objects.create(
        personagem=personagem,
        nome=item_sistema.nome,
        descricao=item_sistema.descricao,
        peso=item_sistema.peso,
        valor=item_sistema.valor,
        qualidade=item_sistema.qualidade,
    )


    serializer = ItemSerializer(item)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )
    
@extend_schema(
    methods=["GET"],
    operation_id="listar_armas_sistema",
    responses=ArmaSistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def arma_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    armas = ArmaSistema.objects.filter(
        sistema=sistema
    ).order_by("nome")

    serializer = ArmaSistemaSerializer(
        armas,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["POST"],
    operation_id="copiar_arma_sistema",
    request=None,
    responses=ArmaSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_arma_sistema(request, personagem_id, arma_id):

    try:
        personagem = Personagem.objects.get(
            pk=personagem_id
        )

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(
        request,
        personagem
    )


    try:
        arma_sistema = ArmaSistema.objects.get(
            pk=arma_id
        )

    except ArmaSistema.DoesNotExist:
        return Response(
            {"erro": "Arma não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )


    arma = Arma.objects.create(
        personagem=personagem,
        nome=arma_sistema.nome,
        descricao=arma_sistema.descricao,
        peso=arma_sistema.peso,
        valor=arma_sistema.valor,
        qualidade=arma_sistema.qualidade,
        ataque=arma_sistema.ataque,
        dano=arma_sistema.dano,
        dano_extra=arma_sistema.dano_extra,
        margem_critico=arma_sistema.margem_critico,
        critico=arma_sistema.critico,
        alcance=arma_sistema.alcance,
        tipo_dano=arma_sistema.tipo_dano,
        empunhadura=arma_sistema.empunhadura,
    )


    serializer = ArmaSerializer(arma)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )

@extend_schema(
    methods=["GET"],
    operation_id="listar_armaduras_sistema",
    responses=ArmaduraSistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def armadura_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    armaduras = ArmaduraSistema.objects.filter(
        sistema=sistema
    ).order_by("nome")

    serializer = ArmaduraSistemaSerializer(
        armaduras,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["POST"],
    operation_id="copiar_armadura_sistema",
    request=None,
    responses=ArmaduraSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_armadura_sistema(request, personagem_id, armadura_id):

    try:
        personagem = Personagem.objects.get(
            pk=personagem_id
        )

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(
        request,
        personagem
    )


    try:
        armadura_sistema = ArmaduraSistema.objects.get(
            pk=armadura_id
        )

    except ArmaduraSistema.DoesNotExist:
        return Response(
            {"erro": "Armadura não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )


    armadura = Armadura.objects.create(
        personagem=personagem,
        nome=armadura_sistema.nome,
        descricao=armadura_sistema.descricao,
        peso=armadura_sistema.peso,
        valor=armadura_sistema.valor,
        qualidade=armadura_sistema.qualidade,
        defesa=armadura_sistema.defesa,
    )


    serializer = ArmaduraSerializer(armadura)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )
    
@extend_schema(
    methods=["GET"],
    operation_id="listar_habilidades_sistema",
    responses=HabilidadeSistemaSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def habilidade_sistema_lista(request, sistema_id):

    try:
        sistema = Sistema.objects.get(pk=sistema_id)

    except Sistema.DoesNotExist:
        return Response(
            {"erro": "Sistema não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    habilidades = HabilidadeSistema.objects.filter(
        sistema=sistema
    ).order_by("tag", "nome")

    serializer = HabilidadeSistemaSerializer(
        habilidades,
        many=True
    )

    return Response(serializer.data)

@extend_schema(
    methods=["POST"],
    operation_id="copiar_habilidade_sistema",
    request=None,
    responses=HabilidadeSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def copiar_habilidade_sistema(request, personagem_id, habilidade_id):

    try:
        personagem = Personagem.objects.get(
            pk=personagem_id
        )

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(
        request,
        personagem
    )


    try:
        habilidade_sistema = HabilidadeSistema.objects.get(
            pk=habilidade_id
        )

    except HabilidadeSistema.DoesNotExist:
        return Response(
            {"erro": "Habilidade não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )


    habilidade = Habilidade.objects.create(
        personagem=personagem,
        tag=habilidade_sistema.tag,
        nome=habilidade_sistema.nome,
        descricao=habilidade_sistema.descricao,
        custo=habilidade_sistema.custo,
        nivel=habilidade_sistema.nivel,
        execucao=habilidade_sistema.execucao,
        alcance=habilidade_sistema.alcance,
        alvo_area=habilidade_sistema.alvo_area,
        duracao=habilidade_sistema.duracao,
        resistencia=habilidade_sistema.resistencia,
    )


    serializer = HabilidadeSerializer(habilidade)

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED
    )