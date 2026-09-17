from django.db import models
from django.db.models import F
from cloudinary.models import CloudinaryField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from Sistema.models import GrupoArmas, Modificacao, Sistema


class Versionado(models.Model):
    """
    Contador de revisão da linha, usado pela sincronização em tempo real do
    Escudo do Mestre (ver `Campanha/escudo.py`): cada evento leva a `versao`
    da linha, e o cliente descarta qualquer evento com versão menor ou igual
    à que já tem. É o que impede uma mensagem atrasada (duas gravações quase
    simultâneas publicadas por threads/processos diferentes) de sobrescrever
    na tela um valor mais novo com um mais antigo.

    O incremento é feito PELO BANCO (`F("versao") + 1` dentro do próprio
    UPDATE), não em Python: duas gravações concorrentes da mesma linha são
    serializadas pelo lock da linha e recebem versões distintas, na ordem em
    que de fato foram gravadas. No Django 6 + PostgreSQL o valor resultante
    volta pelo `RETURNING` do mesmo UPDATE — nenhuma consulta extra.

    `db_default` (e não só `default`) de propósito: se o banco for
    compartilhado com uma versão antiga do código que ainda não conhece este
    campo, os INSERTs dela continuam válidos.
    """

    versao = models.PositiveBigIntegerField(default=1, db_default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.versao = F("versao") + 1
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                # Sem isto, um `save(update_fields=[...])` deixaria a expressão
                # F() presa na instância (não seria enviada nem resolvida).
                kwargs["update_fields"] = {*update_fields, "versao"}
        super().save(*args, **kwargs)


class Personagem(Versionado):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='personagens')
    foto = CloudinaryField('Foto', blank=True)
    banner = CloudinaryField('Banner', blank=True)
    nome = models.CharField(max_length=100, db_index=True)
    nivel = models.PositiveIntegerField(default=1)
    idade = models.CharField(max_length=10, blank=True, null=True)
    origem = models.CharField(max_length=50, blank=True, null=True)
    raca = models.CharField(max_length=50, blank=True, null=True)
    peso_atual = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    peso_maximo = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    
    classe1 = models.CharField(max_length=40, default='combatente')
    classe2 = models.CharField(max_length=40, default='combatente')
    classe3 = models.CharField(max_length=40, default='combatente')
    classe4 = models.CharField(max_length=40, default='combatente')

    dinheiro = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    anotacoes = models.TextField(blank=True)
    aparencia = models.TextField(blank=True)
    personalidade = models.TextField(blank=True)
    historia = models.TextField(blank=True)
    relacionamentos = models.TextField(blank=True)
    objetivos = models.TextField(blank=True)

    # `sistema` (FK) = sistema PRINCIPAL do personagem — o que campanhas e
    # fichas antigas já têm gravado e o que `systemConfig` usa para decidir
    # features. `sistemas` (M2M) = todas as bibliotecas de regras que este
    # personagem pode consultar (ex.: o sistema base + um suplemento).
    # Mantidos em sincronia pelo PersonagemSerializer; a migration de dados
    # 0019 popula `sistemas` a partir de `sistema`.
    sistema = models.ForeignKey(Sistema, on_delete=models.SET_NULL, related_name='personagens', blank=True, null=True)
    sistemas = models.ManyToManyField(Sistema, related_name='personagens_bibliotecas', blank=True)
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.nome}"
    
class Atributo(Versionado):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='atributos')
    cor = models.CharField(max_length=7, default="#FF0000")
    icone = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    valor = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Status(Versionado):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='status')
    nome = models.CharField(max_length=100)
    barra = models.BooleanField(default=False)
    cor = models.CharField(max_length=7, default="#FF0000")
    valor_max = models.PositiveIntegerField(default=0)
    valor_atual = models.PositiveIntegerField(default=0)
    valor_temp = models.IntegerField(default=0, blank=False)
    atributo = models.ForeignKey(Atributo, on_delete=models.SET_NULL, related_name='status', blank=True, null=True)
    atributo_nivel = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)
    sub_status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Defesa(Versionado):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='defesas')
    icone = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    atributo = models.ForeignKey(Atributo, on_delete=models.SET_NULL, related_name='defesas', blank=True, null=True)
    valor = models.IntegerField(default=0)
    ordem = models.PositiveIntegerField(default=0)
    # Defesa exibida em destaque na ficha (ocupa a linha inteira, como
    # Classe de Armadura/DT) — antes decidido por nome fixo no frontend,
    # agora escolhido pelo jogador no modal de edição.
    destaque = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Pericia(models.Model):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='pericias')
    atributo = models.ForeignKey(Atributo, on_delete=models.SET_NULL, related_name='pericias', blank=True, null=True)
    nome = models.CharField(max_length=100)
    treinamento = models.IntegerField(default=0)
    somar_atributo = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Item(models.Model):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='itens')
    foto = CloudinaryField('Foto_item', blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    peso = models.DecimalField(default=0,max_digits=20, decimal_places=1)
    valor = models.DecimalField(default=0, max_digits=20, decimal_places=2)
    qualidade = models.CharField(max_length=100, blank=True)
    quantidade = models.PositiveIntegerField(default=1)
    consumivel = models.BooleanField(default=False)

    # Está à venda no Comércio Livre da campanha? Fica em `Item` (e não nos
    # três models) porque `Arma` e `Armadura` herdam dele por herança
    # multi-tabela — um campo e uma migration cobrem os três itens da ficha.
    #
    # É a fonte única de verdade do anúncio: marcar aqui CRIA o anúncio na
    # campanha do personagem (preço = `valor`, quantidade = `quantidade`, que
    # o jogador refina depois na aba Loja); desmarcar o retira. Quem mantém
    # os dois lados em sincronia é `Campanha.comercio`.
    vendas = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Arma(Item):
    ataque = models.IntegerField(default=0, blank=True)
    dano = models.CharField(default="1d4", max_length=30, blank=True)
    dano_extra = models.CharField(default="0", max_length=30, blank=True)
    margem_critico = models.CharField(default="20", max_length=30, blank=True)
    critico = models.CharField(default="+1d", max_length=30, blank=True)
    alcance = models.CharField(default="Adjacente", max_length=30, blank=True)
    tipo_dano = models.CharField(default="Cortante", max_length=30, blank=True)
    empunhadura = models.CharField(default="Leve", max_length=30, blank=True)
    grupo = models.ManyToManyField(GrupoArmas, blank=True, related_name='armas')
    modificacoes = models.ManyToManyField(Modificacao, blank=True, related_name='armas')
    ordem = models.PositiveIntegerField(default=0)
    
class Armadura(Item):
    defesa = models.IntegerField(default=0, blank=True)
    modificacoes = models.ManyToManyField(Modificacao, blank=True, related_name='armaduras')
    
class Tecnica(models.Model):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='tecnicas')
    midia = CloudinaryField('Mídia_tecnica', blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    mecanica = models.TextField(blank=True)
    limitacoes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"

class Poder(models.Model):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='poderes')
    tecnica = models.ForeignKey(Tecnica, on_delete=models.SET_NULL, related_name='poderes', blank=True, null=True)
    midia = CloudinaryField('Mídia_poder', blank=True)
    tag = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, related_name='poderes', blank=True, null=True)
    custo = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"
    
class Habilidade(Poder):
    nivel = models.PositiveIntegerField(default=1)
    execucao = models.CharField(max_length=30, default="1 Ação", blank=True)
    alcance = models.CharField(max_length=30, default="Toque", blank=True)
    alvo_area = models.CharField(max_length=30, default="Um Alvo", blank=True)
    duracao = models.CharField(max_length=30, default="Instantânea", blank=True)
    resistencia = models.CharField(max_length=30, default="Nenhuma", blank=True)
    
class Aprimoramento(models.Model):
    habilidade = models.ForeignKey(Habilidade, on_delete=models.CASCADE, related_name='aprimoramentos')
    ordem = models.PositiveIntegerField(default=1)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    custo = models.IntegerField(default=0)
    
class Bonus(Versionado):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    alvo = GenericForeignKey("content_type", "object_id")
    nome = models.CharField(max_length=100)
    valor = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)
    somente_teste = models.BooleanField(default=False)