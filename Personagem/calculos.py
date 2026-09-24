"""
Fonte ÚNICA dos valores finais da ficha.

Antes deste módulo cada fórmula existia em dois lugares no frontend
(`StatusSection.tsx`/`SimpleValueStatSection.tsx`/`PericiasTab.tsx` para a
ficha e `utils/escudoCalculos.ts` para o Escudo do Mestre) e em nenhum no
backend. Agora o backend calcula, os serializers publicam `valor_final`, e o
frontend só prevê o resultado enquanto o PATCH não volta.

--------------------------------------------------------------------------
As fórmulas
--------------------------------------------------------------------------
Entidades CALCULADAS (o backend deriva o número):

    Atributo   valor_final     = valor + bonus
    Status     valor_final     = valor_atual + atributo + bonus
               valor_max_final = valor_max   + atributo + bonus
    Defesa     valor_final     = valor + atributo + bonus
    Perícia    valor_final     = treinamento + atributo + bonus
                                 (atributo só entra se `somar_atributo`)

    onde `atributo` = atributo.valor_final × (nível do personagem, se
    `Status.atributo_nivel`; senão × 1)

Entidades FOLHA (o número é digitado pelo jogador, não derivado):

    Item / Arma / Armadura, Técnica, Poder, Habilidade, Aprimoramento
    → a própria coluna `valor_final`. Na Armadura ela é mantida igual a
      `defesa` pelo `save()` do model.

    Além dela, uma folha pode oferecer VÁRIOS bônus nomeados
    (`BonusFornecido`: "+4 CA", "+2 DT"). Um bônus por entidade que aponta
    para um deles (`Bonus.origem_fornecido`) vale o número daquela linha;
    sem ele, vale o `valor_final` da origem, como sempre.

Duas coisas que a ficha SEMPRE fez e continuam valendo:

  - `valor_temp` do Status NÃO entra no total. Ele é exibido à parte, entre
    parênteses, e somá-lo aqui mudaria o número de toda ficha existente.
  - bônus `somente_teste` NÃO entram em nenhum total. Ficam visíveis e
    editáveis no painel de bônus, mas fora do valor estático da ficha.

--------------------------------------------------------------------------
Herança multi-tabela: um alvo, um balde de bônus
--------------------------------------------------------------------------
`Arma` e `Armadura` são subclasses de `Item`; `Habilidade` é subclasse de
`Poder`. A MESMA linha do banco aparece em rotas diferentes (uma arma é
listada em `/itens/` e em `/arma/`), e `ContentType` as trata como models
distintos. Sem cuidado, um bônus criado pela aba Inventário e outro criado
pela aba Combate ficariam em baldes separados, invisíveis um para o outro, e
a mesma linha teria dois `valor_final` diferentes.

`modelo_base()` resolve isso: todo bônus é gravado e lido pelo model BASE
(`item`, `poder`). A migration 0026 converte os bônus antigos.

--------------------------------------------------------------------------
Ciclos
--------------------------------------------------------------------------
Um bônus pode ter como origem o `valor_final` de outra entidade, então o
grafo de dependências é dirigido e pode fechar ciclo (Força → Defesa →
Atletismo → Força). Há duas barreiras:

  1. Na ESCRITA, `BonusSerializer.validate` recusa a aresta que fecharia um
     ciclo, com a rota inteira na mensagem de erro.
  2. Na LEITURA, aqui, `_resolver` guarda o que está sendo calculado na pilha
     `_visitando`: reentrar numa chave contribui 0 e marca a chave como
     incompleta (`valor_final_incompleto` no serializer). É a rede de
     segurança para dado legado ou para dois POSTs concorrentes que passem
     pela barreira 1 ao mesmo tempo — um GET da ficha nunca pode virar
     RecursionError.
"""

from collections import defaultdict
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    Aprimoramento,
    Arma,
    Armadura,
    Atributo,
    Bonus,
    BonusFornecido,
    Defesa,
    Habilidade,
    Item,
    Pericia,
    Personagem,
    Poder,
    Status,
    Tecnica,
)

# Tipos que o cliente pode usar na URL de bônus (`/personagem/<tipo>/<id>/bonus/`)
# e como origem. A chave é sempre `model._meta.model_name`.
MODELOS_ALVO = {
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
    "aprimoramento": Aprimoramento,
}

# tipo pedido -> tipo REALMENTE gravado (ver "Herança multi-tabela" acima).
TIPO_BASE = {
    "arma": "item",
    "armadura": "item",
    "habilidade": "poder",
}

# Os quatro tipos cujo valor o backend deriva. Todos os demais são folhas.
TIPOS_CALCULADOS = ("atributo", "status", "defesa", "pericia")

# Os tipos sob os quais um bônus é de fato gravado — `MODELOS_ALVO` menos as
# subclasses que colapsam no pai (`arma`/`armadura` -> `item`,
# `habilidade` -> `poder`).
TIPOS_BASE = tuple(tipo for tipo in MODELOS_ALVO if tipo not in TIPO_BASE)


# Os tipos-FOLHA: o número é digitado, e só eles podem oferecer vários
# bônus nomeados (`BonusFornecido`). Um Atributo/Defesa já é, ele mesmo, UM
# valor — quem quer "+2 de Força e +1 de Destreza" usa duas origens.
TIPOS_FORNECEDORES = ("item", "tecnica", "poder", "aprimoramento")


def tipo_base(tipo):
    """Nome do tipo sob o qual os bônus daquele alvo são gravados."""
    return TIPO_BASE.get(tipo, tipo)


def modelo_base(tipo):
    """O model concreto base da cadeia de herança de `tipo` (ou None)."""
    return MODELOS_ALVO.get(tipo_base(tipo))


def chave_de(obj):
    """`(tipo_base, pk)` de uma instância — a identidade usada em todo o módulo."""
    return (tipo_base(obj._meta.model_name), obj.pk)


def personagem_de(obj):
    """
    `personagem_id` de qualquer entidade da ficha. `Aprimoramento` chega aqui
    pela `@property personagem` do model (o vínculo dele passa pela
    Habilidade); os demais têm a FK direta.
    """
    pid = getattr(obj, "personagem_id", None)
    if pid is not None:
        return pid
    personagem = getattr(obj, "personagem", None)
    return personagem.pk if personagem is not None else None


def fornecidos_por_entidade(objetos):
    """
    `{(tipo_base, pk): [BonusFornecido, ...]}` de várias entidades numa
    consulta por tipo — o que os serializers usam para publicar a lista de
    bônus fornecidos de uma listagem inteira sem uma consulta por linha.
    """
    por_tipo = defaultdict(set)
    for obj in objetos:
        tipo, pk = chave_de(obj)
        if tipo in TIPOS_FORNECEDORES and pk is not None:
            por_tipo[tipo].add(pk)

    # Toda entidade pedida ganha a sua entrada, mesmo sem bônus nenhum —
    # quem guarda o resultado sabe que ela já foi consultada.
    resultado = {(tipo, pk): [] for tipo, ids in por_tipo.items() for pk in ids}
    for tipo, ids in por_tipo.items():
        ct = ContentType.objects.get_for_model(MODELOS_ALVO[tipo])
        for fornecido in BonusFornecido.objects.filter(content_type=ct, object_id__in=ids):
            resultado[(tipo, fornecido.object_id)].append(fornecido)
    return resultado


# ---------------------------------------------------------------------------
# Expiração dos bônus ligados pelo botão "Usar"
# ---------------------------------------------------------------------------

DURACAO_USO_SEGUNDOS = 60 * 60  # 1 hora


def bonus_vigente(bonus, agora=None):
    """
    O bônus conta para um total? Precisa estar ligado, não ser "somente
    teste" e não ter vencido. A checagem de `expira_em` é feita AQUI (e não
    só no varredor) para a leitura nunca depender de uma gravação anterior.
    """
    if not bonus.ativo or bonus.somente_teste:
        return False
    if bonus.expira_em is None:
        return True
    return bonus.expira_em > (agora or timezone.now())


def expirar_bonus(personagem_id=None, agora=None):
    """
    Grava `ativo=False` nos bônus já vencidos, para que o estado persistido
    bata com o que o cálculo já vinha devolvendo — e para que a mudança
    chegue ao Escudo do Mestre pelos signals normais.

    Chamado nos caminhos em que alguém está de fato OLHANDO para bônus
    (`bonus_lista`, `/calculos/`, `usar`), nunca num GET qualquer de Status:
    um UPDATE que não casa com nada é barato, mas não a ponto de valer em
    toda leitura da ficha.

    Devolve quantas linhas mudaram. `versao` sobe pelo próprio UPDATE (ver
    `Versionado`), então o evento do Escudo sai com a versão certa.
    """
    agora = agora or timezone.now()
    qs = Bonus.objects.filter(ativo=True, expira_em__isnull=False, expira_em__lte=agora)

    # Atalho barato: uma consulta no índice de `expira_em` antes de levantar
    # os ids das dez tabelas da ficha. O caso comum é não haver NADA vencido
    # (bônus com prazo só existem na hora seguinte a um "Usar"), e sem isto
    # abrir o painel de bônus de um card custaria oito consultas de id para
    # depois não atualizar linha nenhuma.
    if personagem_id is not None and not qs.exists():
        return 0

    if personagem_id is not None:
        alvos = Q(pk__in=[])
        for tipo in TIPOS_BASE:
            modelo = MODELOS_ALVO[tipo]
            ids = ids_do_personagem(modelo, personagem_id)
            if ids:
                ct = ContentType.objects.get_for_model(modelo)
                alvos |= Q(content_type=ct, object_id__in=ids)
        qs = qs.filter(alvos)

    return qs.update(ativo=False, expira_em=None, versao=F("versao") + 1)


def expirar_bonus_do_alvo(alvo, agora=None):
    """
    Como `expirar_bonus`, mas só para os bônus de UM alvo.

    É o que `bonus_lista` usa: ali já sabemos exatamente qual é o alvo, e
    uma única consulta indexada por (content_type, object_id) resolve — a
    versão por personagem precisaria levantar os ids das dez tabelas da
    ficha para montar o filtro, e esse painel abre a cada card expandido.
    """
    agora = agora or timezone.now()
    tipo, object_id = chave_de(alvo)
    return Bonus.objects.filter(
        content_type=ContentType.objects.get_for_model(MODELOS_ALVO[tipo]),
        object_id=object_id,
        ativo=True,
        expira_em__isnull=False,
        expira_em__lte=agora,
    ).update(ativo=False, expira_em=None, versao=F("versao") + 1)


def ids_do_personagem(modelo, personagem_id):
    if modelo is Aprimoramento:
        return list(
            Aprimoramento.objects.filter(
                habilidade__personagem_id=personagem_id
            ).values_list("pk", flat=True)
        )
    return list(modelo.objects.filter(personagem_id=personagem_id).values_list("pk", flat=True))


def bonus_relacionados(alvo):
    """
    Todos os bônus que dizem respeito a esta entidade, nos DOIS sentidos:

      - os que ela RECEBE (`content_type`/`object_id` apontam para ela);
      - os que ela FORNECE (`origem_*` aponta para ela) — um bônus na Força
        cuja origem é a Habilidade "Fúria" é um bônus *dela*, ainda que a
        linha esteja pendurada no atributo.

    O segundo sentido é o caso comum de Técnica/Poder/Habilidade/
    Aprimoramento: o `valor_final` dessas entidades é digitado justamente
    para servir de origem a bônus de outras. Uma Habilidade que concede +2 de
    Força não tem bônus nenhum em cima de si — o bônus mora no Atributo.
    """
    content_type = ContentType.objects.get_for_model(MODELOS_ALVO[chave_de(alvo)[0]])
    object_id = alvo.pk
    return Bonus.objects.filter(
        Q(content_type=content_type, object_id=object_id)
        | Q(origem_content_type=content_type, origem_object_id=object_id)
    ).order_by("id")


def ativar_bonus_por_uso(alvo, duracao_segundos=DURACAO_USO_SEGUNDOS, agora=None):
    """
    Regra do botão "Usar" de Técnica/Poder/Habilidade/Aprimoramento: liga os
    bônus DESLIGADOS relacionados à entidade e marca a hora em que devem cair.

    "Relacionados" nos dois sentidos — ver `bonus_relacionados`. É o sentido
    da ORIGEM que faz a regra valer na prática: usar a Habilidade "Fúria"
    precisa acender o +2 que ela concede à Força, e esse bônus está no
    Atributo, não na Habilidade.

    Bônus que já estavam ligados de propósito (sem prazo) são deixados em paz
    — usar uma técnica não pode transformar um bônus permanente do jogador
    num bônus de uma hora. Os que já tinham prazo têm o prazo renovado, que é
    o que "usar de novo" significa.

    Devolve a lista dos bônus afetados (já regravados).
    """
    agora = agora or timezone.now()
    expira_em = agora + timedelta(seconds=duracao_segundos)

    afetados = []
    for bonus in bonus_relacionados(alvo):
        if bonus.ativo and bonus.expira_em is None:
            continue
        bonus.ativo = True
        bonus.expira_em = expira_em
        bonus.save(update_fields=["ativo", "expira_em"])
        afetados.append(bonus)

    return afetados


# ---------------------------------------------------------------------------
# Contexto de cálculo
# ---------------------------------------------------------------------------

class ContextoCalculo:
    """
    Carrega de uma vez tudo que os cálculos de um ou mais personagens
    precisam e memoriza os resultados.

    Sem ele, serializar 21 perícias custaria 21 consultas de bônus + 21 de
    atributo. Com ele, um personagem inteiro sai em ~7 consultas fixas,
    qualquer que seja o tamanho da ficha — o mesmo remédio que
    `Campanha/escudo.py::montar_snapshot` já aplica ao Escudo.

    Use um contexto por REQUISIÇÃO e descarte depois: ele é um retrato do
    banco naquele instante, não um cache de longa vida.
    """

    def __init__(self, personagem_ids=None, agora=None):
        self.agora = agora or timezone.now()
        self._carregados = set()
        self._objetos = {}                      # (tipo, id) -> instância
        self._bonus = defaultdict(list)         # (tipo, id) -> [Bonus]
        self._final = {}                        # (tipo, id) -> int
        self._incompletos = set()               # chaves atingidas por um ciclo
        self._visitando = []                    # pilha da resolução em curso
        self._nivel = {}                        # personagem_id -> nivel

        if personagem_ids:
            self.carregar(personagem_ids)

    # -- carga ------------------------------------------------------------

    def carregar(self, personagem_ids):
        """Traz para a memória tudo de `personagem_ids` que ainda não veio."""
        ids = [pid for pid in set(personagem_ids) if pid is not None and pid not in self._carregados]
        if not ids:
            return
        self._carregados.update(ids)

        for pid, nivel in Personagem.objects.filter(pk__in=ids).values_list("pk", "nivel"):
            self._nivel[pid] = nivel

        # Um por tipo BASE: `Arma`/`Armadura` já vêm dentro de `Item`, e
        # `Habilidade` dentro de `Poder` (é a mesma linha, herança
        # multi-tabela) — consultar as subclasses seria trabalho repetido.
        conjuntos = [
            ("atributo", Atributo.objects.filter(personagem_id__in=ids)),
            ("status", Status.objects.filter(personagem_id__in=ids)),
            ("defesa", Defesa.objects.filter(personagem_id__in=ids)),
            ("pericia", Pericia.objects.filter(personagem_id__in=ids)),
            ("item", Item.objects.filter(personagem_id__in=ids)),
            ("tecnica", Tecnica.objects.filter(personagem_id__in=ids)),
            ("poder", Poder.objects.filter(personagem_id__in=ids)),
            ("aprimoramento", Aprimoramento.objects.filter(habilidade__personagem_id__in=ids)),
        ]

        filtro_bonus = Q(pk__in=[])
        houve_alvo = False
        for tipo, qs in conjuntos:
            objetos = list(qs)
            if not objetos:
                continue
            for obj in objetos:
                self._objetos.setdefault((tipo, obj.pk), obj)
                # Marca o alvo como "bônus já consultados", inclusive quando
                # ele não tem nenhum. Sem isto, `bonus_de` veria a chave
                # ausente e faria uma consulta por entidade SEM bônus — o
                # N+1 voltava pela porta dos fundos, e o snapshot do Escudo
                # tornava a crescer com o número de personagens.
                self._bonus.setdefault((tipo, obj.pk), [])
            ct = ContentType.objects.get_for_model(MODELOS_ALVO[tipo])
            filtro_bonus |= Q(content_type=ct, object_id__in=[o.pk for o in objetos])
            houve_alvo = True

        if houve_alvo:
            self._carregar_bonus(Bonus.objects.filter(filtro_bonus))

    def _carregar_bonus(self, queryset):
        tipos = {
            ContentType.objects.get_for_model(MODELOS_ALVO[tipo]).id: tipo
            for tipo in MODELOS_ALVO
        }
        # `origem_fornecido` junto: `valor_bonus` o lê para todo bônus que
        # aponta para um bônus nomeado, e sem isto seria uma consulta cada.
        for bonus in queryset.select_related("origem_fornecido"):
            tipo = tipos.get(bonus.content_type_id)
            if tipo is None:
                continue
            self._bonus[(tipo_base(tipo), bonus.object_id)].append(bonus)

    # -- acesso -----------------------------------------------------------

    def registrar(self, obj):
        """
        Põe `obj` no contexto SEM disparar carga nenhuma.

        De propósito preguiçoso: publicar uma única linha alterada no Escudo
        do Mestre acontece a cada tecla do jogador, e carregar a ficha
        inteira ali custaria ~10 consultas para serializar um Status. Quem
        precisa da ficha toda (o endpoint `/calculos/`, o snapshot do Escudo)
        constrói o contexto com `ContextoCalculo([ids])` e paga a carga uma
        vez só.

        A instância do chamador tem precedência sobre a cópia que uma carga
        posterior traria: é ela que o serializer está publicando, e pode ter
        alterações ainda não regravadas.
        """
        self._objetos[chave_de(obj)] = obj

    def objeto(self, tipo, object_id):
        chave = (tipo_base(tipo), object_id)
        if chave not in self._objetos:
            modelo = modelo_base(tipo)
            if modelo is None:
                return None
            self._objetos[chave] = modelo.objects.filter(pk=object_id).first()
        return self._objetos[chave]

    def bonus_de(self, obj):
        """Todos os bônus do alvo, vencidos e "somente teste" inclusive."""
        chave = chave_de(obj)
        if chave not in self._bonus and chave[1] is not None:
            ct = ContentType.objects.get_for_model(MODELOS_ALVO[chave[0]])
            self._carregar_bonus(
                Bonus.objects.filter(content_type=ct, object_id=chave[1])
            )
            self._bonus.setdefault(chave, [])
        return self._bonus.get(chave, [])

    def nivel(self, personagem_id):
        if personagem_id not in self._nivel:
            self._nivel[personagem_id] = (
                Personagem.objects.filter(pk=personagem_id)
                .values_list("nivel", flat=True)
                .first()
                or 1
            )
        return self._nivel[personagem_id]

    # -- cálculo ----------------------------------------------------------

    def valor_bonus(self, bonus):
        """
        Quanto este bônus vale AGORA. Manual: o número digitado. Por
        entidade: o `valor_final` da origem, resolvido na hora — é isto que
        faz a Defesa acompanhar a Força sem ninguém reeditar o bônus.

        Origem apagada ou inválida vale 0 (o `Defesa.atributo` com
        `SET_NULL` já se comporta assim quando o atributo some).
        """
        if bonus.tipo_origem != Bonus.TIPO_ENTIDADE:
            return bonus.valor
        if bonus.origem_content_type_id is None or bonus.origem_object_id is None:
            return 0
        # Um dos bônus NOMEADOS da origem ("Postura Defensiva → +4 CA"): vale
        # o que aquela linha diz, não o total da entidade.
        if bonus.origem_fornecido_id is not None:
            fornecido = bonus.origem_fornecido
            return fornecido.valor if fornecido is not None else 0
        origem = self.objeto(bonus.origem_content_type.model, bonus.origem_object_id)
        if origem is None:
            return 0
        return self.valor_final(origem)

    def total_bonus(self, obj):
        """Soma dos bônus vigentes do alvo (ver `bonus_vigente`)."""
        return sum(
            self.valor_bonus(b)
            for b in self.bonus_de(obj)
            if bonus_vigente(b, self.agora)
        )

    def contribuicao_atributo(self, obj):
        """
        Quanto o Atributo vinculado acrescenta a este Status/Defesa/Perícia.

        Usa o `valor_final` do atributo (e não o `valor` cru): um bônus na
        Força passa a chegar na Defesa e na Perícia que dependem dela — foi a
        decisão tomada ao aprovar o plano.

        `Status.atributo_nivel` multiplica pelo Nível do personagem;
        `Pericia.somar_atributo` desligado zera a contribuição (a perícia
        continua exibindo o atributo, só não o conta).
        """
        atributo_id = getattr(obj, "atributo_id", None)
        if atributo_id is None:
            return 0
        if isinstance(obj, Pericia) and not obj.somar_atributo:
            return 0

        atributo = self.objeto("atributo", atributo_id)
        if atributo is None:
            return 0

        valor = self.valor_final(atributo)
        if isinstance(obj, Status) and obj.atributo_nivel:
            valor *= self.nivel(personagem_de(obj))
        return valor

    def valor_final(self, obj):
        """O número que a ficha exibe. Memorizado por (tipo, id)."""
        if obj is None:
            return 0
        return self._resolver(chave_de(obj), obj)

    def valor_max_final(self, status):
        """
        Só para Status: o TETO da barra. Atributo e bônus somam ao máximo (e
        não ao valor atual) quando `barra=True` — é como a ficha sempre se
        comportou, e mexer nisso mudaria o número de toda ficha existente.
        """
        self.registrar(status)
        return status.valor_max + self.contribuicao_atributo(status) + self.total_bonus(status)

    def incompleto(self, obj):
        """True se o valor deste alvo foi truncado por um ciclo."""
        return chave_de(obj) in self._incompletos

    def componentes(self, obj):
        """
        A decomposição que o card mostra ("Base 2 + Atributo 3 + Bônus 1").
        Publicada pelos serializers para o frontend não precisar refazer a
        conta só para montar a legenda.
        """
        self.registrar(obj)
        tipo = chave_de(obj)[0]
        base = {
            "atributo": lambda: obj.valor,
            "status": lambda: obj.valor_atual,
            "defesa": lambda: obj.valor,
            "pericia": lambda: obj.treinamento,
        }.get(tipo, lambda: obj.valor_final)()

        return {
            "base": base,
            "atributo": self.contribuicao_atributo(obj) if tipo in TIPOS_CALCULADOS else 0,
            "bonus": self.total_bonus(obj) if tipo in TIPOS_CALCULADOS else 0,
        }

    # -- resolução com guarda de ciclo ------------------------------------

    def _resolver(self, chave, obj):
        if chave in self._final:
            return self._final[chave]

        if chave in self._visitando:
            # Ciclo. Contribui 0 e marca TODAS as chaves do ciclo como
            # incompletas, para o serializer poder avisar o jogador.
            inicio = self._visitando.index(chave)
            self._incompletos.update(self._visitando[inicio:])
            return 0

        self._visitando.append(chave)
        try:
            valor = self._calcular(chave[0], obj)
        finally:
            self._visitando.pop()

        # Um valor obtido a partir de um ciclo não é memorizado: ele depende
        # do ponto por onde a resolução entrou no ciclo, e guardá-lo faria
        # duas leituras da mesma ficha darem números diferentes.
        if chave not in self._incompletos:
            self._final[chave] = valor
        return valor

    def _calcular(self, tipo, obj):
        self.registrar(obj)

        if tipo == "atributo":
            return obj.valor + self.total_bonus(obj)

        if tipo == "status":
            return obj.valor_atual + self.contribuicao_atributo(obj) + self.total_bonus(obj)

        if tipo == "defesa":
            return obj.valor + self.contribuicao_atributo(obj) + self.total_bonus(obj)

        if tipo == "pericia":
            return obj.treinamento + self.contribuicao_atributo(obj) + self.total_bonus(obj)

        # Folhas: o número é o que o jogador digitou (na Armadura, o `save()`
        # dela mantém a coluna igual a `defesa`).
        return getattr(obj, "valor_final", 0) or 0


# ---------------------------------------------------------------------------
# Detecção de ciclo na ESCRITA
# ---------------------------------------------------------------------------

def rota_ate(origem_tipo, origem_id, alvo_tipo, alvo_id):
    """
    Existe caminho de (origem) até (alvo) seguindo as dependências atuais?

    Chamado antes de gravar um bônus por entidade: se a ORIGEM já depende
    (direta ou indiretamente) do ALVO, a aresta nova fecharia um ciclo.
    Devolve a rota como lista de chaves (para a mensagem de erro), ou None.

    As arestas de um nó são os bônus por entidade que ele recebe MAIS o
    Atributo vinculado (`Status.atributo`, `Defesa.atributo`,
    `Pericia.atributo`) — os dois caminham na mesma direção "meu valor
    depende de".
    """
    alvo = (tipo_base(alvo_tipo), alvo_id)
    inicio = (tipo_base(origem_tipo), origem_id)

    contexto = ContextoCalculo()
    pilha = [(inicio, [inicio])]
    vistos = set()

    while pilha:
        atual, rota = pilha.pop()
        if atual == alvo:
            return rota
        if atual in vistos:
            continue
        vistos.add(atual)

        obj = contexto.objeto(*atual)
        if obj is None:
            continue

        for vizinho in _dependencias(obj, contexto):
            if vizinho not in vistos:
                pilha.append((vizinho, [*rota, vizinho]))

    return None


def _dependencias(obj, contexto):
    """De quem o `valor_final` de `obj` depende."""
    atributo_id = getattr(obj, "atributo_id", None)
    if atributo_id is not None and not (isinstance(obj, Pericia) and not obj.somar_atributo):
        yield ("atributo", atributo_id)

    for bonus in contexto.bonus_de(obj):
        if bonus.tipo_origem != Bonus.TIPO_ENTIDADE:
            continue
        if bonus.origem_content_type_id is None or bonus.origem_object_id is None:
            continue
        yield (tipo_base(bonus.origem_content_type.model), bonus.origem_object_id)


def descrever_rota(rota):
    """"atributo #3 → defesa #7 → atributo #3" — para a mensagem de erro."""
    return " → ".join(f"{tipo} #{pk}" for tipo, pk in rota)
