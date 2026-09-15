"""
Loja da campanha — rotação de vitrine e montagem do que o cliente recebe.

A ROTAÇÃO é uma função pura do relógio, não um job. O projeto não tem fila
nem cron, e mesmo que tivesse, um worker girando a loja traria problemas que
aqui simplesmente não existem:

  - todos os jogadores veem a MESMA seleção, porque todos recebem o
    resultado da mesma conta feita no servidor — não há sorteio por cliente
    nem estado que possa divergir entre duas requisições simultâneas;
  - nada é guardado, então restart, deploy ou banco restaurado não perdem
    nem adiantam a rotação: ela é derivada de `rotacao_inicio`, do intervalo
    e da hora atual;
  - o cliente não precisa ficar perguntando se já virou. A resposta diz em
    `proxima_rotacao_em` exatamente quando a seleção muda, e o frontend
    agenda UM refetch para esse instante.

A conta é:

    janela = floor((agora - rotacao_inicio) / intervalo)

e a janela decide a seleção — por ordem (fatia cíclica que anda a cada
janela) ou por sorteio semeado com `(semente, categoria, janela)`, que é
reproduzível em qualquer processo, em qualquer máquina.

Consequência assumida: o "pool" são os produtos disponíveis AGORA, então um
item que esgota sai da conta e a seleção daquela janela é recalculada sem
ele. É o comportamento desejado (esgotou, sumiu da prateleira) — a seleção
não é congelada no início da janela.
"""

import random
from datetime import timedelta

from django.utils import timezone

from Midia.services import copiar_ajuste, ler_ajustes, url_de
from Usuario.permissions import pode_gerenciar_campanha

# ---------------------------------------------------------------------------
# Identificação das origens
# ---------------------------------------------------------------------------

# Os três "formatos" de equipamento que a loja conhece. O frontend usa isto
# para decidir o que mostrar no card (dano numa arma, defesa numa armadura).
CLASSE_POR_MODELO = {
    "itemsistema": "item",
    "armasistema": "arma",
    "armadurasistema": "armadura",
    "itemcampanha": "item",
    "armacampanha": "arma",
    "armaduracampanha": "armadura",
    # Os próprios models da ficha: o Comércio Livre anuncia itens que já
    # estão no inventário de alguém, e o card do anúncio é o mesmo da loja.
    "item": "item",
    "arma": "arma",
    "armadura": "armadura",
}

# Campos de jogo específicos de cada formato, além dos comuns.
CAMPOS_POR_CLASSE = {
    "item": (),
    "arma": (
        "ataque", "dano", "dano_extra", "margem_critico",
        "critico", "alcance", "tipo_dano", "empunhadura",
    ),
    "armadura": ("defesa",),
}

CAMPOS_COMUNS = ("nome", "descricao", "peso", "valor", "qualidade")


def tipo_de(obj):
    """Nome do model em minúsculo — o mesmo valor usado em `content_type.model`."""
    return obj._meta.model_name


def classe_de(obj):
    return CLASSE_POR_MODELO.get(tipo_de(obj), "item")


# ---------------------------------------------------------------------------
# Resumo de uma origem
# ---------------------------------------------------------------------------

def resumos_de_origens(objetos):
    """
    `{(tipo, id): resumo}` para uma lista de equipamentos de origem, com os
    enquadramentos carregados EM LOTE (uma consulta por model).

    Não reaproveita `ItemCampanhaSerializer` e companhia de propósito: o
    serializer de entidade de mundo tem um `conexoes` que consulta o banco
    por objeto, e uma vitrine com 40 produtos pagaria 40 consultas por algo
    que a loja não mostra. Aqui só sai o que o card precisa.
    """
    por_model = {}
    for obj in objetos:
        por_model.setdefault(type(obj), []).append(obj)

    ajustes = {}
    for model, itens in por_model.items():
        ajustes[model] = ler_ajustes(model, [o.pk for o in itens], ["foto"])

    resumos = {}
    for obj in objetos:
        tipo = tipo_de(obj)
        classe = classe_de(obj)
        dados = {campo: getattr(obj, campo) for campo in CAMPOS_COMUNS}
        dados.update({campo: getattr(obj, campo) for campo in CAMPOS_POR_CLASSE[classe]})
        foto = url_de(getattr(obj, "foto", None))
        resumos[(tipo, obj.pk)] = {
            "tipo": tipo,
            "classe": classe,
            "id": obj.pk,
            "foto": foto,
            "foto_ajuste": ajustes[type(obj)].get(obj.pk, {}).get("foto") if foto else None,
            **dados,
        }
    return resumos


def carregar_origens(produtos):
    """
    Resolve as origens de vários produtos com UMA consulta por model, em vez
    de uma por produto (o que a GenericForeignKey faria sozinha).
    """
    por_ct = {}
    for produto in produtos:
        por_ct.setdefault(produto.content_type, []).append(produto.object_id)

    objetos = []
    for content_type, ids in por_ct.items():
        model = content_type.model_class()
        if model is None:
            continue
        objetos.extend(model.objects.filter(pk__in=set(ids)))
    return objetos


# ---------------------------------------------------------------------------
# Rotação
# ---------------------------------------------------------------------------

def _intervalo(categoria):
    minutos = categoria.rotacao_intervalo_minutos or 0
    return timedelta(minutes=minutos) if minutos > 0 else None


def janela_atual(categoria, agora=None):
    """
    Índice da janela de tempo corrente, contado desde `rotacao_inicio`.
    `None` quando a categoria não rotaciona por tempo.

    Antes do início configurado (o mestre pode agendar para o futuro) a
    janela é 0 — a primeira seleção já vale, ela só para de trocar.
    """
    intervalo = _intervalo(categoria)
    if intervalo is None:
        return None
    agora = agora or timezone.now()
    decorrido = agora - categoria.rotacao_inicio
    if decorrido.total_seconds() < 0:
        return 0
    return int(decorrido // intervalo)


def proxima_rotacao(categoria, agora=None):
    """Quando a seleção desta categoria muda. `None` = não muda sozinha."""
    intervalo = _intervalo(categoria)
    if intervalo is None:
        return None
    janela = janela_atual(categoria, agora)
    return categoria.rotacao_inicio + (janela + 1) * intervalo


def selecionar(categoria, produtos, agora=None):
    """
    Os produtos à mostra nesta categoria agora.

    `produtos` precisa chegar numa ordem ESTÁVEL (a ordenação padrão do
    model, `ordem` + `id`): é ela que torna a fatia "por ordem" previsível e
    o sorteio reproduzível entre processos.

    Sem rotação ativa — ou com a vitrine maior que o estoque — mostra tudo.
    """
    produtos = list(produtos)
    quantidade = categoria.rotacao_quantidade or 0

    if not categoria.rotacao_ativa or quantidade <= 0 or len(produtos) <= quantidade:
        return produtos

    janela = janela_atual(categoria, agora)
    if janela is None:
        return produtos

    if categoria.rotacao_metodo == "ordem":
        # Fatia cíclica que anda `quantidade` posições por janela: percorre a
        # lista inteira em voltas, sem repetir dentro da mesma janela.
        inicio = (janela * quantidade) % len(produtos)
        return [produtos[(inicio + i) % len(produtos)] for i in range(quantidade)]

    # `Random` semeado com uma string estável: o MESMO resultado em qualquer
    # processo, worker ou máquina — é isso que faz a mesa inteira ver a mesma
    # vitrine sem precisar guardar a escolha em lugar nenhum.
    sorteio = random.Random(f"{categoria.rotacao_semente}:{categoria.pk}:{janela}")
    return sorteio.sample(produtos, quantidade)


# ---------------------------------------------------------------------------
# Vitrine
# ---------------------------------------------------------------------------

def _dados_produto(produto, resumos, categorias_ids):
    return {
        "id": produto.id,
        "preco": str(produto.preco),
        "quantidade_disponivel": produto.quantidade_disponivel,
        "disponivel": produto.disponivel,
        "esgotado": produto.esgotado,
        "categorias": categorias_ids,
        "origem": resumos.get((produto.content_type.model, produto.object_id)),
        # Preenchido só para o mestre (ver `montar_vitrine`): se este produto
        # está na seleção que os jogadores enxergam agora.
        "na_vitrine": True,
    }


def _dados_categoria(categoria, agora):
    return {
        "id": categoria.id,
        "nome": categoria.nome,
        "descricao": categoria.descricao,
        "icone": categoria.icone,
        "cor": categoria.cor,
        "ordem": categoria.ordem,
        "visivel_para_jogadores": categoria.visivel_para_jogadores,
        "rotacao": {
            "ativa": categoria.rotacao_ativa,
            "metodo": categoria.rotacao_metodo,
            "quantidade": categoria.rotacao_quantidade,
            "intervalo_minutos": categoria.rotacao_intervalo_minutos,
            "proxima_em": proxima_rotacao(categoria, agora) if categoria.rotacao_ativa else None,
        },
    }


def montar_vitrine(campanha, usuario, agora=None):
    """
    A loja como o cliente a recebe: categorias na ordem do mestre, cada uma
    já com a SELEÇÃO da janela atual, mais `proxima_rotacao_em` — o instante
    da próxima virada entre todas as categorias, que é o único despertador de
    que o frontend precisa.

    O mestre enxerga tudo (inclusive categorias escondidas e produtos fora de
    venda, marcados pelas flags); o jogador recebe só o que está à venda.
    Número fixo de consultas, independente do tamanho da loja.
    """
    agora = agora or timezone.now()
    e_mestre = pode_gerenciar_campanha(campanha, usuario)

    categorias = list(campanha.categorias_loja.all())
    if not e_mestre:
        categorias = [c for c in categorias if c.visivel_para_jogadores]

    produtos = list(campanha.produtos_loja.select_related("content_type").prefetch_related("categorias"))
    if not e_mestre:
        # Fora de venda ou esgotado não chega nem a aparecer para o jogador.
        produtos = [p for p in produtos if p.disponivel and not p.esgotado]

    resumos = resumos_de_origens(carregar_origens(produtos))

    # Uma origem que sumiu (equipamento excluído sem passar por aqui) não
    # pode derrubar a vitrine inteira — o produto órfão é apenas omitido.
    produtos = [p for p in produtos if (p.content_type.model, p.object_id) in resumos]

    por_categoria = {c.id: [] for c in categorias}
    sem_categoria = []
    for produto in produtos:
        ids = [c.id for c in produto.categorias.all()]
        dados = _dados_produto(produto, resumos, ids)
        alocado = False
        for categoria_id in ids:
            if categoria_id in por_categoria:
                por_categoria[categoria_id].append((produto, dados))
                alocado = True
        if not alocado:
            # Sem categoria, ou só em categorias que este usuário não vê.
            if not ids or e_mestre:
                sem_categoria.append(dados)

    saida = []
    proximas = []
    for categoria in categorias:
        pares = por_categoria[categoria.id]
        selecionados = selecionar(categoria, [p for p, _ in pares], agora)
        ids_selecionados = {p.id for p in selecionados}

        dados = _dados_categoria(categoria, agora)
        dados["total_produtos"] = len(pares)

        if e_mestre:
            # O mestre precisa ver o ESTOQUE INTEIRO para administrá-lo —
            # com a rotação filtrando, metade dos produtos ficaria
            # inalcançável para editar. Cada um vem marcado com
            # `na_vitrine`, que é o que os jogadores estão vendo agora.
            dados["produtos"] = [{**d, "na_vitrine": p.id in ids_selecionados} for p, d in pares]
        else:
            dados["produtos"] = [d for p, d in pares if p.id in ids_selecionados]

        saida.append(dados)

        if dados["rotacao"]["proxima_em"] and len(pares) > (categoria.rotacao_quantidade or 0):
            # Só conta como "vai virar" se a rotação realmente muda algo —
            # com vitrine maior que o estoque, a seleção é sempre a mesma e
            # acordar o cliente seria uma requisição à toa.
            proximas.append(dados["rotacao"]["proxima_em"])

    return {
        "categorias": saida,
        "sem_categoria": sem_categoria,
        "proxima_rotacao_em": min(proximas) if proximas else None,
    }


def produto_a_venda(produto, usuario, campanha, agora=None):
    """
    O produto pode ser COMPRADO agora? Usado pela compra, não pela vitrine.

    Além de `disponivel` e estoque, exige que o produto esteja na seleção
    corrente de alguma categoria que o comprador enxerga — senão bastaria
    guardar o id de um produto e comprá-lo enquanto a rotação o esconde, o
    que esvaziaria a rotação como mecânica de jogo.

    Produto sem categoria nenhuma não passa por rotação: está sempre à venda
    enquanto `disponivel`.
    """
    if not produto.disponivel or produto.esgotado:
        return False

    e_mestre = pode_gerenciar_campanha(campanha, usuario)
    categorias = [
        c for c in produto.categorias.all() if e_mestre or c.visivel_para_jogadores
    ]

    if not produto.categorias.exists():
        return True

    if not categorias:
        # Só está em categorias escondidas do jogador.
        return False

    agora = agora or timezone.now()
    for categoria in categorias:
        irmaos = list(
            categoria.produtos.filter(disponivel=True)
            .exclude(quantidade_disponivel=0)
            .order_by("ordem", "id")
        )
        if any(p.id == produto.id for p in selecionar(categoria, irmaos, agora)):
            return True

    return False


# ---------------------------------------------------------------------------
# Origem -> ficha
# ---------------------------------------------------------------------------

def modelo_da_ficha(classe):
    """O model da ficha correspondente ao formato do equipamento."""
    from Personagem.models import Arma, Armadura, Item

    return {"item": Item, "arma": Arma, "armadura": Armadura}[classe]


def serializer_da_ficha(classe):
    from Personagem.serializers import ArmaSerializer, ArmaduraSerializer, ItemSerializer

    return {"item": ItemSerializer, "arma": ArmaSerializer, "armadura": ArmaduraSerializer}[classe]


def copiar_para_ficha(origem, personagem, quantidade=1):
    """
    Cria na ficha uma linha NOVA a partir de um equipamento de qualquer das
    seis origens (Sistema ou exclusivo da campanha). O original nunca é
    tocado.

    A imagem vai por referência (mesmo `public_id`) com o enquadramento
    junto — seguro porque a fila de exclusão do app Midia recheca o uso de
    cada arquivo antes de apagar. A coluna de imagem da ficha não aceita
    NULL, daí o `or ""`.

    Uma compra de 3 unidades vira UMA linha com `quantidade=3`, e nunca
    mexe numa linha que já existe: empilhar por nome alteraria um item que o
    jogador pode ter renomeado, recebido bônus ou trocado a foto.
    """
    classe = classe_de(origem)
    campos = CAMPOS_COMUNS + CAMPOS_POR_CLASSE[classe]
    dados = {campo: getattr(origem, campo) for campo in campos}

    copia = modelo_da_ficha(classe).objects.create(
        personagem=personagem,
        foto=getattr(origem, "foto", None) or "",
        quantidade=quantidade,
        **dados,
    )

    copiar_ajuste(origem, copia, ["foto"])

    return copia


# ---------------------------------------------------------------------------
# Categorias iniciais
# ---------------------------------------------------------------------------

# Prateleiras que toda campanha nova já ganha, para a Loja não nascer vazia —
# são as três divisões que praticamente toda mesa usa. O mestre renomeia,
# reordena ou apaga à vontade; não há nada de especial nelas depois de
# criadas.
CATEGORIAS_PADRAO = [
    {"nome": "Armas", "icone": "sword", "ordem": 1},
    {"nome": "Armaduras", "icone": "shield", "ordem": 2},
    {"nome": "Itens Gerais", "icone": "package", "ordem": 3},
]


def criar_categorias_padrao(campanha):
    """
    Cria as prateleiras iniciais da Loja de uma campanha.

    `ignore_conflicts` protege a UniqueConstraint (campanha, nome): se esta
    função rodar duas vezes para a mesma campanha — ou se o mestre já tiver
    criado uma "Armas" à mão —, o que existe é mantido e nada estoura.

    Fica aqui, e não num signal de `post_save`, por uma razão prática: um
    signal criaria categorias também para toda Campanha construída em
    teste ou no shell, mudando o estado inicial de dezenas de cenários que
    não têm nada a ver com a Loja. O único caminho que interessa é a
    criação pela API, e é de lá que esta função é chamada.
    """
    from .models import CategoriaLoja

    CategoriaLoja.objects.bulk_create(
        [CategoriaLoja(campanha=campanha, **dados) for dados in CATEGORIAS_PADRAO],
        ignore_conflicts=True,
    )
