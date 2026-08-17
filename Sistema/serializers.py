from rest_framework import serializers
from Sistema.models import *


class SistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sistema
        fields = "__all__"
        
class RegraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regra
        fields = "__all__"

class PoderSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoderSistema
        fields = "__all__"
        
class HabilidadeSistemaSerializer(serializers.ModelSerializer):
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
        
class ItemSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemSistema
        fields = "__all__"
        
class ArmaSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArmaSistema
        fields = "__all__"
        
class ArmaduraSistemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArmaduraSistema
        fields = "__all__"