"""
Comércio Livre — jogadores vendendo itens do próprio inventário entre si.

Duas responsabilidades:

1. Manter `Item.vendas` e `AnuncioComercioLivre` como UM estado só. O campo
   booleano na ficha é o interruptor que o jogador vê; o anúncio é o
   registro com preço e quantidade. Marcar `vendas` cria o anúncio com
   padrões sensatos (preço = `valor` do item, quantidade = a que ele tem),
   desmarcar o retira, e mexer no anúncio reflete de volta no campo. Sem
   isso os dois divergiriam e a ficha mentiria sobre o que está à venda.

2. Executar a venda: dinheiro de um lado para o outro e o item do
   inventário de um para o do outro, tudo numa transação com as quatro
   linhas envolvidas travadas.
"""

from django.db import transaction

from Personagem.models import Arma, Armadura, Item, Personagem

from . import loja
from .models import AnuncioComercioLivre, TransacaoLoja


class ErroComercio(Exception):
    """Regra de negócio violada — a view traduz em 400/409 com esta mensagem."""

    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


# ---------------------------------------------------------------------------
# Tipo concreto de um item da ficha
# ---------------------------------------------------------------------------

def concreto(item):
    """
    A instância REAL de um `Item`: `Arma` ou `Armadura` quando for o caso.

    `Item.objects.get(...)` devolve sempre um `Item`, mesmo quando a linha é
    de uma arma — na herança multi-tabela as duas compartilham o pk. Sem
    resolver isto, uma arma vendida chegaria ao comprador como item comum,
    sem dano nem crítico.
    """
    for atributo in ("arma", "armadura"):
        filho = getattr(item, atributo, None)
        if filho is not None:
            return filho
    return item


def classe_do_item(item):
    real = concreto(item)
    if isinstance(real, Arma):
        return "arma"
    if isinstance(real, Armadura):
        return "armadura"
    return "item"


# ---------------------------------------------------------------------------
# Sincronização com `Item.vendas`
# ---------------------------------------------------------------------------

def campanha_do_item(item, campanha=None):
    """
    Em qual campanha este item pode ser anunciado.

    Com o personagem em uma única campanha, é ela — o caso comum, e o que
    permite o `vendas` da ficha funcionar com um clique só. Em mais de uma,
    é ambíguo e o chamador precisa dizer qual (a aba Loja sempre manda);
    em nenhuma, não há comércio possível.
    """
    campanhas = list(item.personagem.campanhas.all())

    if campanha is not None:
        if all(c.id != campanha.id for c in campanhas):
            raise ErroComercio("Este personagem não participa desta campanha.")
        return campanha

    if not campanhas:
        raise ErroComercio(
            "Este personagem não participa de nenhuma campanha, então não há onde vender o item."
        )

    if len(campanhas) > 1:
        raise ErroComercio(
            "Este personagem está em mais de uma campanha — escolha em qual "
            "delas anunciar o item pela aba Loja."
        )

    return campanhas[0]


def anuncio_ativo(item):
    return AnuncioComercioLivre.objects.filter(item=item, ativo=True).first()


def anunciar(item, campanha=None, preco=None, quantidade=None):
    """
    Põe o item à venda (ou atualiza o anúncio que já existe) e deixa
    `Item.vendas` verdadeiro.

    Os padrões são o que torna o interruptor da ficha utilizável sozinho:
    preço = o `valor` do próprio item, quantidade = tudo o que o personagem
    tem. O jogador ajusta os dois na aba Loja quando quiser.
    """
    campanha = campanha_do_item(item, campanha)

    if item.quantidade < 1:
        raise ErroComercio("Não há nenhuma unidade deste item para vender.")

    quantidade = item.quantidade if quantidade is None else int(quantidade)

    if quantidade < 1:
        raise ErroComercio("A quantidade à venda precisa ser pelo menos 1.")

    if quantidade > item.quantidade:
        raise ErroComercio("Você não tem essa quantidade deste item.")

    preco = item.valor if preco is None else preco

    anuncio = anuncio_ativo(item)

    if anuncio is None:
        anuncio = AnuncioComercioLivre.objects.create(
            campanha=campanha,
            vendedor_personagem=item.personagem,
            item=item,
            quantidade=quantidade,
            preco=preco,
        )
    else:
        anuncio.campanha = campanha
        anuncio.quantidade = quantidade
        anuncio.preco = preco
        anuncio.save(update_fields=["campanha", "quantidade", "preco", "atualizado_em"])

    if not item.vendas:
        # `update_fields` evita disparar de novo a sincronização vinda do
        # serializer, e mantém o save barato.
        item.vendas = True
        item.save(update_fields=["vendas"])

    return anuncio


def retirar(item):
    """Tira o item da venda — o anúncio é encerrado, não apagado (o
    histórico das transações continua apontando para ele)."""
    AnuncioComercioLivre.objects.filter(item=item, ativo=True).update(ativo=False)

    if item.vendas:
        item.vendas = False
        item.save(update_fields=["vendas"])


def sincronizar_vendas(item, campanha=None):
    """
    Chamado depois de gravar um item da ficha: aplica o que `Item.vendas`
    passou a dizer. É o que faz `True` significar "à venda automaticamente".
    """
    if item.vendas:
        anunciar(item, campanha=campanha)
    else:
        retirar(item)


# ---------------------------------------------------------------------------
# Venda
# ---------------------------------------------------------------------------

def comprar(anuncio_id, comprador, usuario, quantidade=1, chave=None):
    """
    Executa uma venda entre dois personagens.

    Tudo dentro de uma transação, com anúncio, item e os DOIS personagens
    travados: é o que impede duas pessoas de comprarem a mesma última
    unidade, ou o vendedor de retirar o item no meio da operação. O dinheiro
    sai de um e entra no outro na mesma transação — nunca some nem aparece.

    Devolve (transacao, item_do_comprador, anuncio).
    """
    with transaction.atomic():
        anuncio = (
            AnuncioComercioLivre.objects.select_for_update()
            .select_related("campanha", "vendedor_personagem", "item")
            .filter(pk=anuncio_id)
            .first()
        )

        if anuncio is None or not anuncio.ativo:
            raise ErroComercio("Este anúncio não está mais ativo.", status=409)

        campanha = anuncio.campanha

        if comprador.pk == anuncio.vendedor_personagem_id:
            raise ErroComercio("Você não pode comprar o próprio anúncio.")

        if not campanha.personagens.filter(pk=comprador.pk).exists():
            raise ErroComercio("Este personagem não participa desta campanha.")

        if not campanha.personagens.filter(pk=anuncio.vendedor_personagem_id).exists():
            # O vendedor saiu da mesa depois de anunciar.
            raise ErroComercio("O vendedor não participa mais desta campanha.", status=409)

        item = Item.objects.select_for_update().get(pk=anuncio.item_id)
        # As duas fichas travadas: o dinheiro sai de uma e entra na outra, e
        # nenhuma das duas pode ser lida por outra compra no meio disso.
        vendedor = Personagem.objects.select_for_update().get(pk=anuncio.vendedor_personagem_id)
        comprador = Personagem.objects.select_for_update().get(pk=comprador.pk)

        if quantidade < 1:
            raise ErroComercio("A quantidade precisa ser pelo menos 1.")

        if quantidade > anuncio.quantidade or quantidade > item.quantidade:
            raise ErroComercio("Não há essa quantidade à venda.", status=409)

        total = anuncio.preco * quantidade

        if comprador.dinheiro < total:
            raise ErroComercio("Dinheiro insuficiente.")

        # --- daqui para baixo, só gravação ---
        comprador.dinheiro = comprador.dinheiro - total
        vendedor.dinheiro = vendedor.dinheiro + total
        comprador.save(update_fields=["dinheiro"])
        vendedor.save(update_fields=["dinheiro"])

        real = concreto(item)
        copia = loja.copiar_para_ficha(real, comprador, quantidade)

        restante = item.quantidade - quantidade
        nome_item = item.nome

        anuncio.quantidade -= quantidade
        if anuncio.quantidade < 1 or restante < 1:
            anuncio.ativo = False
        anuncio.save(update_fields=["quantidade", "ativo", "atualizado_em"])

        if restante < 1:
            # Vendeu tudo: a linha sai do inventário do vendedor. A foto não
            # se perde — a fila de exclusão do app Midia recheca o uso e vê a
            # cópia do comprador apontando para o mesmo arquivo.
            item.delete()
        else:
            item.quantidade = restante
            item.vendas = anuncio.ativo
            item.save(update_fields=["quantidade", "vendas"])

        transacao = TransacaoLoja.objects.create(
            campanha=campanha,
            tipo="comercio_livre",
            comprador_personagem=comprador,
            vendedor_personagem=vendedor,
            anuncio=anuncio,
            nome_item=nome_item,
            preco_unitario=anuncio.preco,
            quantidade=quantidade,
            total=total,
            chave_idempotencia=chave,
        )

    return transacao, copia, anuncio
