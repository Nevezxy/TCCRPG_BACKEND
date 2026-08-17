from django.shortcuts import render
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .serializers import RegistroSerializer, UsuarioSerializer

# Create your views here.
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
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):

    serializer = UsuarioSerializer(request.user)

    return Response(serializer.data)
