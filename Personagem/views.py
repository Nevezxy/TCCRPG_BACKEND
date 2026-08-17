from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from Personagem.utils import criar_dados_iniciais_personagem

from .models import *
from .serializers import *

from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from Usuario.utils import check_object_permission


@extend_schema(
    methods=["GET"],
    operation_id="listar_personagens",
    responses=PersonagemSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_personagem",
    request=PersonagemSerializer,
    responses=PersonagemSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def personagens(request):

    if request.method == "GET":

        if request.user.is_superuser:
            personagens = Personagem.objects.all()
        else:
            personagens = Personagem.objects.filter(
                usuario=request.user
            )
        serializer = PersonagemSerializer(personagens, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        modelo = request.query_params.get("modelo", "tcc")
        
        serializer = PersonagemSerializer(data=request.data)

        if serializer.is_valid():
            personagem = serializer.save(usuario=request.user)
            
            criar_dados_iniciais_personagem(personagem, modelo)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    methods=["GET"],
    operation_id="detalhar_personagem",
    responses=PersonagemSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_personagem",
    request=PersonagemSerializer,
    responses=PersonagemSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_personagem",
    request=PersonagemSerializer,
    responses=PersonagemSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_personagem",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def personagem(request, pk):

    try:
        personagem = Personagem.objects.get(pk=pk)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        serializer = PersonagemSerializer(personagem)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = PersonagemSerializer(
            personagem,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = PersonagemSerializer(
            personagem,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        personagem.delete()

        return Response(
            {"mensagem": "Personagem removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )
        
@extend_schema(
    methods=["GET"],
    operation_id="listar_status_personagem",
    responses=StatusSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_status_personagem",
    request=StatusSerializer,
    responses=StatusSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def status_lista(request, personagem_id):
    
    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )
        
    check_object_permission(request, personagem)

    if request.method == "GET":

        status_personagem = Status.objects.filter(personagem=personagem).order_by("ordem")

        serializer = StatusSerializer(
            status_personagem,
            many=True
        )

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = StatusSerializer(
            data=request.data
        )

        if serializer.is_valid():
            serializer.save(personagem=personagem)

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
    operation_id="detalhar_status",
    responses=StatusSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_status",
    request=StatusSerializer,
    responses=StatusSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_status",
    request=StatusSerializer,
    responses=StatusSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_status",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def status_detalhe(request, pk):

    try:
        status_personagem = Status.objects.get(pk=pk)

    except Status.DoesNotExist:

        return Response(
            {"erro": "Status não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )
        
    check_object_permission(request, status_personagem)

    if request.method == "GET":

        serializer = StatusSerializer(
            status_personagem
        )

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = StatusSerializer(
            status_personagem,
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

        serializer = StatusSerializer(
            status_personagem,
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

        status_personagem.delete()

        return Response(
            {"mensagem": "Status removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )
        
@extend_schema(
    methods=["GET"],
    operation_id="listar_atributos_personagem",
    responses=AtributoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_atributos_personagem",
    request=AtributoSerializer,
    responses=AtributoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def atributo_lista(request, personagem_id):
    
    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )
        
    check_object_permission(request, personagem)

    if request.method == "GET":

        atributos = Atributo.objects.filter(personagem=personagem).order_by("id")

        serializer = AtributoSerializer(atributos, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = AtributoSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    methods=["GET"],
    operation_id="detalhar_atributo",
    responses=AtributoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_atributo",
    request=AtributoSerializer,
    responses=AtributoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_atributo",
    request=AtributoSerializer,
    responses=AtributoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_atributo",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def atributo_detalhe(request, pk):

    try:
        atributo = Atributo.objects.get(pk=pk)

    except Atributo.DoesNotExist:
        return Response(
            {"erro": "Atributo não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, atributo)

    if request.method == "GET":

        serializer = AtributoSerializer(atributo)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = AtributoSerializer(atributo, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = AtributoSerializer(
            atributo,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        atributo.delete()

        return Response(
            {"mensagem": "Atributo removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_defesas_personagem",
    responses=DefesaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_defesas_personagem",
    request=DefesaSerializer,
    responses=DefesaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def defesa_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        defesas = Defesa.objects.filter(personagem=personagem).order_by("id")

        serializer = DefesaSerializer(defesas, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = DefesaSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

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
    operation_id="detalhar_defesa",
    responses=DefesaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_defesa",
    request=DefesaSerializer,
    responses=DefesaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_defesa",
    request=DefesaSerializer,
    responses=DefesaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_defesa",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def defesa_detalhe(request, pk):

    try:
        defesa = Defesa.objects.get(pk=pk)

    except Defesa.DoesNotExist:
        return Response(
            {"erro": "Defesa não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    check_object_permission(request, defesa)

    if request.method == "GET":

        serializer = DefesaSerializer(defesa)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = DefesaSerializer(defesa, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = DefesaSerializer(
            defesa,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        defesa.delete()

        return Response(
            {"mensagem": "Defesa removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_pericias_personagem",
    responses=PericiaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_pericias_personagem",
    request=PericiaSerializer,
    responses=PericiaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def pericia_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        pericias = Pericia.objects.filter(personagem=personagem).order_by("nome")

        serializer = PericiaSerializer(pericias, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = PericiaSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

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
    operation_id="detalhar_pericia",
    responses=PericiaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_pericia",
    request=PericiaSerializer,
    responses=PericiaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_pericia",
    request=PericiaSerializer,
    responses=PericiaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_pericia",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def pericia_detalhe(request, pk):

    try:
        pericia = Pericia.objects.get(pk=pk)

    except Pericia.DoesNotExist:
        return Response(
            {"erro": "Perícia não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, pericia)

    if request.method == "GET":

        serializer = PericiaSerializer(pericia)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = PericiaSerializer(pericia, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = PericiaSerializer(
            pericia,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        pericia.delete()

        return Response(
            {"mensagem": "Perícia removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_itens_personagem",
    responses=ItemSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_itens_personagem",
    request=ItemSerializer,
    responses=ItemSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def item_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        itens = Item.objects.filter(personagem=personagem).order_by("nome")

        serializer = ItemSerializer(itens, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = ItemSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@extend_schema(
    methods=["GET"],
    operation_id="detalhar_item",
    responses=ItemSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_item",
    request=ItemSerializer,
    responses=ItemSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_item",
    request=ItemSerializer,
    responses=ItemSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_item",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def item_detalhe(request, pk):
    
    try:
        item = Item.objects.get(pk=pk)
    except Item.DoesNotExist:
        return Response(
            {"erro": "Item não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, item)

    if request.method == "GET":

        serializer = ItemSerializer(item)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = ItemSerializer(item, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = ItemSerializer(item, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        item.delete()

        return Response(
            {"mensagem": "Item removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_armas_personagem",
    responses=ArmaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_armas_personagem",
    request=ArmaSerializer,
    responses=ArmaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def arma_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )
        
    check_object_permission(request, personagem)

    if request.method == "GET":

        armas = Arma.objects.filter(personagem=personagem)

        serializer = ArmaSerializer(armas, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = ArmaSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    methods=["GET"],
    operation_id="detalhar_arma",
    responses=ArmaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_arma",
    request=ArmaSerializer,
    responses=ArmaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_arma",
    request=ArmaSerializer,
    responses=ArmaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_arma",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def arma_detalhe(request, pk):

    try:
        arma = Arma.objects.get(pk=pk)
    except Arma.DoesNotExist:
        return Response(
            {"erro": "Arma não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, arma)

    if request.method == "GET":

        serializer = ArmaSerializer(arma)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = ArmaSerializer(arma, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = ArmaSerializer(arma, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        arma.delete()

        return Response(
            {"mensagem": "Arma removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_armaduras_personagem",
    responses=ArmaduraSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_armaduras_personagem",
    request=ArmaduraSerializer,
    responses=ArmaduraSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def armadura_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    check_object_permission(request, personagem)

    if request.method == "GET":

        armaduras = Armadura.objects.filter(personagem=personagem)

        serializer = ArmaduraSerializer(armaduras, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = ArmaduraSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    methods=["GET"],
    operation_id="detalhar_armadura",
    responses=ArmaduraSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_armadura",
    request=ArmaduraSerializer,
    responses=ArmaduraSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_armadura",
    request=ArmaduraSerializer,
    responses=ArmaduraSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_armadura",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def armadura_detalhe(request, pk):

    try:
        armadura = Armadura.objects.get(pk=pk)
    except Armadura.DoesNotExist:
        return Response(
            {"erro": "Armadura não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, armadura)

    if request.method == "GET":

        serializer = ArmaduraSerializer(armadura)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = ArmaduraSerializer(armadura, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = ArmaduraSerializer(armadura, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        armadura.delete()

        return Response(
            {"mensagem": "Armadura removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_tecnicas_personagem",
    responses=TecnicaSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_tecnicas_personagem",
    request=TecnicaSerializer,
    responses=TecnicaSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tecnica_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        tecnicas = Tecnica.objects.filter(personagem=personagem)

        serializer = TecnicaSerializer(tecnicas, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = TecnicaSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

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
    operation_id="detalhar_tecnica",
    responses=TecnicaSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_tecnica",
    request=TecnicaSerializer,
    responses=TecnicaSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_tecnica",
    request=TecnicaSerializer,
    responses=TecnicaSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_tecnica",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def tecnica_detalhe(request, pk):

    try:
        tecnica = Tecnica.objects.get(pk=pk)

    except Tecnica.DoesNotExist:
        return Response(
            {"erro": "Técnica não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, tecnica)

    if request.method == "GET":

        serializer = TecnicaSerializer(tecnica)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = TecnicaSerializer(tecnica, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = TecnicaSerializer(
            tecnica,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        tecnica.delete()

        return Response(
            {"mensagem": "Técnica removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_poderes_personagem",
    responses=PoderSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_poderes_personagem",
    request=PoderSerializer,
    responses=PoderSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def poder_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        poderes = Poder.objects.filter(
        personagem=personagem,
        habilidade__isnull=True
    ).order_by("nome")

        serializer = PoderSerializer(poderes, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = PoderSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

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
    operation_id="detalhar_poder",
    responses=PoderSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_poder",
    request=PoderSerializer,
    responses=PoderSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_poder",
    request=PoderSerializer,
    responses=PoderSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_poder",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def poder_detalhe(request, pk):

    try:
        poder = Poder.objects.get(pk=pk)

    except Poder.DoesNotExist:
        return Response(
            {"erro": "Poder não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, poder)

    if request.method == "GET":

        serializer = PoderSerializer(poder)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = PoderSerializer(poder, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = PoderSerializer(
            poder,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        poder.delete()

        return Response(
            {"mensagem": "Poder removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_habilidades_personagem",
    responses=HabilidadeSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_habilidades_personagem",
    request=HabilidadeSerializer,
    responses=HabilidadeSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def habilidade_lista(request, personagem_id):

    try:
        personagem = Personagem.objects.get(pk=personagem_id)

    except Personagem.DoesNotExist:
        return Response(
            {"erro": "Personagem não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, personagem)

    if request.method == "GET":

        habilidades = Habilidade.objects.filter(personagem=personagem).order_by("nivel", "nome")

        serializer = HabilidadeSerializer(habilidades, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = HabilidadeSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(personagem=personagem)

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
    operation_id="detalhar_habilidade",
    responses=HabilidadeSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_habilidade",
    request=HabilidadeSerializer,
    responses=HabilidadeSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_habilidade",
    request=HabilidadeSerializer,
    responses=HabilidadeSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_habilidade",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def habilidade_detalhe(request, pk):

    try:
        habilidade = Habilidade.objects.get(pk=pk)

    except Habilidade.DoesNotExist:
        return Response(
            {"erro": "Habilidade não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, habilidade)

    if request.method == "GET":

        serializer = HabilidadeSerializer(habilidade)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = HabilidadeSerializer(
            habilidade,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "PATCH":

        serializer = HabilidadeSerializer(
            habilidade,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":

        habilidade.delete()

        return Response(
            {"mensagem": "Habilidade removida com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )

@extend_schema(
    methods=["GET"],
    operation_id="listar_aprimoramentos_habilidade",
    responses=AprimoramentoSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_aprimoramentos_habilidade",
    request=AprimoramentoSerializer,
    responses=AprimoramentoSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def aprimoramento_lista(request, habilidade_id):

    try:
        habilidade = Habilidade.objects.get(pk=habilidade_id)

    except Habilidade.DoesNotExist:
        return Response(
            {"erro": "Habilidade não encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    check_object_permission(request, habilidade)

    if request.method == "GET":

        aprimoramentos = Aprimoramento.objects.filter(
            habilidade=habilidade
        )

        serializer = AprimoramentoSerializer(
            aprimoramentos,
            many=True
        )

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = AprimoramentoSerializer(
            data=request.data
        )

        if serializer.is_valid():

            serializer.save(
                habilidade=habilidade
            )

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
    operation_id="detalhar_aprimoramento",
    responses=AprimoramentoSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_aprimoramento",
    request=AprimoramentoSerializer,
    responses=AprimoramentoSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_aprimoramento",
    request=AprimoramentoSerializer,
    responses=AprimoramentoSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_aprimoramento",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def aprimoramento_detalhe(request, pk):

    try:
        aprimoramento = Aprimoramento.objects.select_related(
            "habilidade__personagem"
        ).get(pk=pk)

    except Aprimoramento.DoesNotExist:
        return Response(
            {"erro": "Aprimoramento não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    # FIX (BOLA/IDOR): a checagem de permissão estava totalmente ausente
    # aqui. Sem ela, qualquer usuário autenticado conseguia ler, editar ou
    # excluir o Aprimoramento de qualquer Habilidade de qualquer
    # Personagem, bastando adivinhar/enumerar o `pk`. `check_object_permission`
    # não sabe resolver Aprimoramento diretamente (não tem `personagem`
    # nem `campanha`), então delegamos para o objeto que ele sabe checar:
    # a Habilidade (que tem `personagem`).
    check_object_permission(request, aprimoramento.habilidade)

    if request.method == "GET":

        serializer = AprimoramentoSerializer(
            aprimoramento
        )

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = AprimoramentoSerializer(
            aprimoramento,
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

        serializer = AprimoramentoSerializer(
            aprimoramento,
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

        aprimoramento.delete()

        return Response(
            {"mensagem": "Aprimoramento removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )
        
MODELOS_BONUS = {
    "status": Status,
    "atributo": Atributo,
    "defesa": Defesa,
    "pericia": Pericia,
    "item": Item,
    "arma": Arma,
    "armadura": Armadura,
    "tecnica": Tecnica,
    "poder": Poder,
    "habilidade": Habilidade,
}

@extend_schema(
    methods=["GET"],
    operation_id="listar_bonus",
    responses=BonusSerializer(many=True),
)
@extend_schema(
    methods=["POST"],
    operation_id="criar_bonus",
    request=BonusSerializer,
    responses=BonusSerializer,
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bonus_lista(request, tipo, object_id):

    modelo = MODELOS_BONUS.get(tipo.lower())

    if modelo is None:
        return Response(
            {"erro": "Tipo de alvo inválido."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        alvo = modelo.objects.get(pk=object_id)

    except modelo.DoesNotExist:
        return Response(
            {"erro": "Objeto não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    # FIX (BOLA/IDOR): antes desta correção, esta view nunca chamava
    # `check_object_permission` sobre `alvo` — qualquer usuário autenticado
    # conseguia listar e criar Bonus em cima de Status/Atributo/Defesa/...
    # de QUALQUER personagem, só sabendo `tipo` e `object_id`. Todos os
    # models em MODELOS_BONUS têm `personagem`, então
    # `check_object_permission` já sabe validar (dono do personagem, ou
    # mestre/jogador da campanha em modo leitura).
    check_object_permission(request, alvo)

    content_type = ContentType.objects.get_for_model(modelo)

    if request.method == "GET":

        bonus = Bonus.objects.filter(
            content_type=content_type,
            object_id=object_id
        )

        serializer = BonusSerializer(bonus, many=True)

        return Response(serializer.data)

    elif request.method == "POST":

        serializer = BonusSerializer(data=request.data)

        if serializer.is_valid():

            serializer.save(
                content_type=content_type,
                object_id=object_id
            )

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
    operation_id="detalhar_bonus",
    responses=BonusSerializer,
)
@extend_schema(
    methods=["PUT"],
    operation_id="atualizar_bonus",
    request=BonusSerializer,
    responses=BonusSerializer,
)
@extend_schema(
    methods=["PATCH"],
    operation_id="atualizar_parcial_bonus",
    request=BonusSerializer,
    responses=BonusSerializer,
)
@extend_schema(
    methods=["DELETE"],
    operation_id="remover_bonus",
    responses=None,
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def bonus_detalhe(request, pk):

    try:
        bonus = Bonus.objects.select_related("content_type").get(pk=pk)

    except Bonus.DoesNotExist:

        return Response(
            {"erro": "Bônus não encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    # FIX (BOLA/IDOR): esta view não checava NENHUMA permissão — GET, PUT,
    # PATCH e DELETE estavam abertos para qualquer usuário autenticado em
    # qualquer Bonus do sistema. `bonus.alvo` resolve o objeto real via
    # GenericForeignKey (ex.: um Status de um Personagem); se o alvo ainda
    # existir, delegamos a checagem para ele. Se o alvo já tiver sido
    # excluído (bônus "órfão"), negamos por padrão em vez de liberar.
    alvo = bonus.alvo

    if alvo is None:
        return Response(
            {"erro": "Você não tem permissão para acessar este recurso."},
            status=status.HTTP_403_FORBIDDEN
        )

    check_object_permission(request, alvo)

    if request.method == "GET":

        serializer = BonusSerializer(bonus)

        return Response(serializer.data)

    elif request.method == "PUT":

        serializer = BonusSerializer(
            bonus,
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

        serializer = BonusSerializer(
            bonus,
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

        bonus.delete()

        return Response(
            {"mensagem": "Bônus removido com sucesso."},
            status=status.HTTP_204_NO_CONTENT
        )