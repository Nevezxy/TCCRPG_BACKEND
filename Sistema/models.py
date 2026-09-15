"""
As imagens destes models seguem o MESMO caminho de qualquer outra imagem do
projeto (app Midia): o upload e o enquadramento entram pelo
`CloudinaryUrlSerializerMixin` nos serializers, e a limpeza no Cloudinary é
ligada automaticamente — `Midia.signals.conectar()` varre todos os models do
projeto atrás de `CloudinaryField`, então nada precisou ser registrado lá.

O NOME do campo é o mesmo do model equivalente da ficha (`foto` em
Item/Arma/Armadura, `midia` em Poder/Habilidade) de propósito: é o que
permite às views `copiar_*` levarem a imagem para a ficha sem um mapa de
"campo de origem → campo de destino".
"""

from cloudinary.models import CloudinaryField
from django.db import models


class Sistema(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)

    def __str__(self):
        return self.nome
    
class Regra(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='regras')
    tag = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)

    def __str__(self):
        return f"{self.nome} ({self.sistema.nome})"
    
class ItemSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='itens')
    foto = CloudinaryField('Foto', blank=True, null=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    peso = models.DecimalField(default=0,max_digits=20, decimal_places=1)
    valor = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    qualidade = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.nome}"

class ArmaSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='armas')
    foto = CloudinaryField('Foto', blank=True, null=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    peso = models.DecimalField(default=0,max_digits=20, decimal_places=1)
    valor = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    qualidade = models.CharField(max_length=100, blank=True)
    ataque = models.IntegerField(default=0, blank=True)
    dano = models.CharField(default="1d4", max_length=30, blank=True)
    dano_extra = models.CharField(default="0", max_length=30, blank=True)
    margem_critico = models.CharField(default="20", max_length=30, blank=True)
    critico = models.CharField(default="+1d", max_length=30, blank=True)
    alcance = models.CharField(default="Adjacente", max_length=30, blank=True)
    tipo_dano = models.CharField(default="Cortante", max_length=30, blank=True)
    empunhadura = models.CharField(default="Leve", max_length=30, blank=True)
    
    def __str__(self):
        return f"{self.nome}"
    
class ArmaduraSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='armaduras')
    foto = CloudinaryField('Foto', blank=True, null=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    peso = models.DecimalField(default=0,max_digits=20, decimal_places=1)
    valor = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    qualidade = models.CharField(max_length=100, blank=True)
    defesa = models.IntegerField(default=0, blank=True)
    
    def __str__(self):
        return f"{self.nome}"
    
class Modificacao(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='modificacoes')
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    custo = models.IntegerField(default=1)
    
    def __str__(self):
        return f"{self.nome}"
    
class GrupoArmas(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='grupos_armas')
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    comum = models.TextField(blank=True)
    trabalhado = models.TextField(blank=True)
    obra_prima = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.nome}"
    
class PoderSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='poderes')
    midia = CloudinaryField('Mídia', blank=True, null=True)
    tag = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    custo = models.IntegerField(default=0)
    
    def __str__(self):
        return self.nome
    
class HabilidadeSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name='habilidades')
    midia = CloudinaryField('Mídia', blank=True, null=True)
    tag = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    custo = models.IntegerField(default=0)
    
    nivel = models.PositiveIntegerField(default=1)
    execucao = models.CharField(max_length=30, default="1 Ação", blank=True)
    alcance = models.CharField(max_length=30, default="Toque", blank=True)
    alvo_area = models.CharField(max_length=30, default="Um Alvo", blank=True)
    duracao = models.CharField(max_length=30, default="Instantânea", blank=True)
    resistencia = models.CharField(max_length=30, default="Nenhuma", blank=True)
    
    def __str__(self):
        return self.nome
    