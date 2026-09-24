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

    # Preferências do cálculo do Peso Atual, guardadas AQUI (e não no navegador)
    # para valerem em qualquer aparelho. O total em si continua sendo calculado
    # pelo frontend (soma do inventário) e gravado em `peso_atual`; estes dois
    # campos são o que ele precisa para calcular igual em todo lugar.
    #
    # `peso_multiplica_quantidade`: o peso de cada item/arma/armadura é
    # multiplicado pela sua `quantidade`? Ligado por padrão — é o que a ficha
    # sempre fez, então as fichas existentes não mudam de comportamento.
    #
    # `peso_ajuste_manual`: diferença entre o Peso Atual digitado à mão e a
    # soma do inventário (ex.: peso de algo que não está cadastrado como item).
    # É somada ao total a cada recálculo, então uma edição manual acompanha as
    # mudanças do inventário em vez de ser desfeita. NULL = "nunca definido": a
    # ficha ainda não foi aberta com este recurso, e o frontend adota o
    # `peso_atual` já salvo como ponto de partida sem sobrescrevê-lo (0 significa
    # "sem ajuste", que é outra coisa).
    #
    # `db_default` (e não só `default`), como em `Versionado.versao`: se o banco
    # for compartilhado com uma versão antiga do código, os INSERTs dela seguem
    # válidos.
    peso_multiplica_quantidade = models.BooleanField(default=True, db_default=True)
    peso_ajuste_manual = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=None)
    
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
    # Posição na ordenação manual da aba de Perícias, gravada pelo arraste
    # (o mesmo campo e o mesmo PATCH que Status, Defesa e Arma já usam).
    # Nasce 0 em toda ficha existente: enquanto ninguém arrastar nada, o
    # desempate por `nome` mantém a lista exatamente como estava.
    ordem = models.PositiveIntegerField(default=0)
    
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

    # Valor final do item, DIGITADO pelo jogador — não é calculado a partir de
    # nada. Existe porque `valor` já é o PREÇO em dinheiro (usado pela Loja e
    # pelo Comércio Livre) e não tem relação com o número que o item vale em
    # mesa; são duas coisas distintas que precisavam de duas colunas.
    #
    # Fica em `Item` (e não em três models) porque `Arma` e `Armadura` herdam
    # dele por herança multi-tabela: uma coluna cobre os três. Na `Armadura`
    # ele é mantido igual a `defesa` pelo `save()` dela — ver o comentário lá.
    #
    # É este o número que outra entidade recebe ao usar um item como origem de
    # bônus (ver `Bonus.tipo_origem`).
    valor_final = models.IntegerField(default=0, db_default=0)

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

    def save(self, *args, **kwargs):
        """
        `defesa` continua sendo O campo da armadura — é o que o jogador edita,
        o que a Loja copia (`Campanha/loja.py`) e o que `ArmaduraCampanha`/
        `ArmaduraSistema` também têm. Aqui só o espelhamos na coluna
        `valor_final` herdada de `Item`.

        Por que espelhar em vez de expor `defesa` como alias no serializer: a
        MESMA linha aparece na aba Inventário (como Item) e na aba Combate
        (como Armadura) — herança multi-tabela, ver `api/recursosIrmaos.ts` no
        frontend. Um alias só no `ArmaduraSerializer` faria a visão de Item
        devolver 0 para a mesma armadura, e o valor mudaria de tab para tab.
        Com o espelho, `valor_final` é o mesmo número em qualquer visão e em
        qualquer bônus que use esta armadura como origem.
        """
        self.valor_final = self.defesa
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "valor_final"}
        super().save(*args, **kwargs)
    
class Tecnica(models.Model):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='tecnicas')
    midia = CloudinaryField('Mídia_tecnica', blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    mecanica = models.TextField(blank=True)
    limitacoes = models.TextField(blank=True)
    # Digitado pelo jogador (ver `Item.valor_final`): Técnica não tem número
    # que o sistema saiba derivar. Serve para a Técnica poder ser origem de
    # bônus de outra entidade.
    valor_final = models.IntegerField(default=0, db_default=0)
    
    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"

class PoderBase(models.Model):
    """
    O que um poder É, independente de onde mora: os campos que `Poder` (da
    ficha) e `PoderUsuario` (da conta) têm em comum. Herança ABSTRATA de
    propósito — não cria tabela nem muda a de `Poder` (a migration que
    acompanha esta extração é vazia); só garante que um campo novo no poder
    chegue aos dois de uma vez, em vez de ser lembrado duas vezes.

    `tecnica` e `status` ficam de fora: apontam para linhas de UMA ficha, e
    um poder da conta é compartilhado por todas.
    """
    midia = CloudinaryField('Mídia_poder', blank=True)
    tag = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    custo = models.IntegerField(default=0)
    # Digitado pelo jogador (ver `Item.valor_final`). Fica em `Poder` e
    # `Habilidade` o herda — uma coluna para os dois, como em `Item`.
    valor_final = models.IntegerField(default=0, db_default=0)

    class Meta:
        abstract = True


class Poder(PoderBase):
    personagem = models.ForeignKey(Personagem, on_delete=models.CASCADE, related_name='poderes')
    tecnica = models.ForeignKey(Tecnica, on_delete=models.SET_NULL, related_name='poderes', blank=True, null=True)
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, related_name='poderes', blank=True, null=True)
    
    def __str__(self):
        return f"{self.nome} ({self.personagem.nome})"


class PoderUsuario(PoderBase):
    """
    Poder cadastrado na CONTA, não numa ficha: aparece na Biblioteca (botão
    flutuante da ficha) de todos os personagens do dono, ao lado dos poderes
    do Sistema, e "Adicionar" o COPIA para a ficha como um `Poder` comum —
    o mesmo modelo de toda a Biblioteca. A cópia ganha técnica, status,
    bônus e "Usar" da ficha, e editar o poder da conta depois não mexe nas
    fichas que já o copiaram.

    `usuario` é o que faz `IsOwnerOrAdmin` reconhecer o dono sem regra nova
    (ramo "objeto com `usuario`" de `Usuario/permissions.py`).
    """
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='poderes_usuario')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.usuario})"
    
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
    # Digitado pelo jogador (ver `Item.valor_final`).
    valor_final = models.IntegerField(default=0, db_default=0)

    @property
    def personagem(self):
        """
        Único model da ficha sem FK direta para `Personagem` — o vínculo passa
        pela Habilidade. Esta propriedade é o que faz `check_object_permission`
        (`Usuario/permissions.py`) funcionar aqui: ele procura `obj.personagem`
        e, sem ela, caía no `return False` final e negava o acesso até para o
        dono. Era o que impedia o Aprimoramento de aceitar bônus, apesar de o
        frontend já declarar `BONUS_TIPO.aprimoramento`.
        """
        return self.habilidade.personagem
    
class BonusFornecido(models.Model):
    """
    Um bônus que uma entidade-FOLHA da ficha (Item/Arma/Armadura, Técnica,
    Poder/Habilidade, Aprimoramento) oferece a quem a usar como origem.

    Antes cada uma dessas entidades fornecia um número só — a coluna
    `valor_final` ("Bônus fornecido"). Isso não dava conta de uma Habilidade
    como "Postura Defensiva", que concede +4 de CA E +2 de DT: o jogador tinha
    de escolher um dos dois. Agora ela guarda uma linha por bônus, cada uma
    com o próprio rótulo e valor, e um `Bonus` por entidade aponta para a
    linha exata que escolheu (`Bonus.origem_fornecido`).

    `valor_final` continua existindo e valendo — é o "Valor total" que os
    bônus já gravados usam, e o que a Armadura espelha de `defesa`. Nada que
    existia muda de número.

    Genérico (content_type/object_id), como o próprio `Bonus`, e gravado
    sempre sob o model BASE da herança (`item`, `poder`) — ver
    `calculos.tipo_base`: uma arma tem o mesmo conjunto de bônus fornecidos
    na aba Inventário e na aba Combate.

    Quem apaga as linhas quando a entidade é excluída é
    `Personagem/signals.py` (GenericForeignKey não tem `on_delete`).
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    entidade = GenericForeignKey("content_type", "object_id")
    # O que o bônus representa ("CA", "DT", "Defesa Física") — é o rótulo
    # que aparece ao escolhê-lo como origem: "Postura Defensiva → +4 CA".
    nome = models.CharField(max_length=100)
    valor = models.IntegerField(default=0)
    descricao = models.CharField(max_length=255, blank=True, default="")
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.nome} ({self.valor:+d})"


class Bonus(Versionado):
    """
    Modificador anexado a qualquer entidade da ficha (Status, Atributo,
    Defesa, Perícia, Item/Arma/Armadura, Técnica, Poder, Habilidade,
    Aprimoramento) através de uma GenericForeignKey.

    Duas origens possíveis (`tipo_origem`):

      - `manual`: o número vem de `valor`, digitado pelo jogador.
      - `entidade`: o número é o `valor_final` de OUTRA entidade da mesma
        ficha, resolvido na hora da leitura (`Personagem/calculos.py`). É uma
        REFERÊNCIA, não uma cópia: se a Força subir, todo bônus que a usa como
        origem sobe junto, sem ninguém reeditar nada.

    `expira_em` é o que sustenta a regra de "Usar" de Técnica/Poder/
    Habilidade/Aprimoramento: o uso liga os bônus da entidade e marca a hora
    em que eles devem cair. Não há Celery nem cron neste projeto, então a
    expiração é PREGUIÇOSA — o cálculo já ignora um bônus vencido, e
    `calculos.expirar_bonus()` grava o `ativo=False` quando alguém olha para
    a lista de bônus. Ler nunca depende de o varredor ter rodado.
    """

    TIPO_MANUAL = "manual"
    TIPO_ENTIDADE = "entidade"
    TIPOS_ORIGEM = [(TIPO_MANUAL, "Manual"), (TIPO_ENTIDADE, "Entidade")]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    alvo = GenericForeignKey("content_type", "object_id")
    nome = models.CharField(max_length=100)
    valor = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)
    somente_teste = models.BooleanField(default=False)

    tipo_origem = models.CharField(
        max_length=10, choices=TIPOS_ORIGEM, default=TIPO_MANUAL, db_default=TIPO_MANUAL
    )

    # Segunda GenericForeignKey: a entidade de onde o valor vem quando
    # `tipo_origem == "entidade"`. Genérica (e não uma FK por tipo) porque a
    # origem pode ser qualquer um dos dez models da ficha — dez colunas
    # nuláveis seriam a alternativa.
    #
    # Como GenericForeignKey NÃO tem `on_delete`, apagar a entidade de origem
    # deixaria um bônus apontando para um id que não existe mais. Quem limpa é
    # o signal `Personagem/signals.py::_origem_removida`, que reproduz o mesmo
    # `SET_NULL` que `Defesa.atributo` já usa: o bônus vira manual com valor 0
    # em vez de sumir (o jogador vê o que sobrou e decide).
    origem_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="bonus_como_origem",
        blank=True,
        null=True,
    )
    origem_object_id = models.PositiveIntegerField(blank=True, null=True)
    origem = GenericForeignKey("origem_content_type", "origem_object_id")

    # QUAL dos bônus da origem foi escolhido, quando ela oferece vários (ver
    # `BonusFornecido`). Vazio = o `valor_final` da origem, que é como todo
    # bônus por entidade funcionava antes — e continua funcionando.
    #
    # `SET_NULL` só por segurança: o signal de `BonusFornecido` transforma
    # antes o bônus em manual com o último valor, do mesmo jeito que faz
    # quando a entidade de origem inteira é apagada.
    origem_fornecido = models.ForeignKey(
        BonusFornecido,
        on_delete=models.SET_NULL,
        related_name="referencias",
        blank=True,
        null=True,
    )

    expira_em = models.DateTimeField(blank=True, null=True, default=None)

    class Meta:
        indexes = [
            # A consulta de todo cálculo: "os bônus deste alvo".
            models.Index(fields=["content_type", "object_id"]),
            # Usado pela limpeza quando a entidade de origem é excluída.
            models.Index(fields=["origem_content_type", "origem_object_id"]),
            # Usado pelo varredor de expirados.
            models.Index(fields=["expira_em"]),
        ]