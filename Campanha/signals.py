"""
Gravações no banco → eventos do Escudo do Mestre (ver `escudo.py`).

Ficam em signals, e não nas views, para cobrir TODO caminho de escrita da
ficha: as views de Status/Atributo/Defesa/Bônus, o `usarStatus`, o admin e
qualquer view futura — ninguém precisa lembrar de "avisar o Escudo".

Três cuidados:

  - Só publica DEPOIS do commit (`transaction.on_commit`): uma gravação
    desfeita por rollback nunca vira evento, e quem recebe o evento sempre
    consegue ler do banco o mesmo valor que recebeu.
  - Não publica gravação que não muda nada visível no Escudo. A assinatura
    dos campos exibidos é guardada quando a instância é carregada
    (`post_init`) e comparada no `post_save`: um jogador digitando as
    anotações da ficha (vários PATCH seguidos no Personagem) não gera nenhum
    tráfego para o Escudo.
  - Resolve as campanhas no momento do commit. Na exclusão em cascata de um
    Personagem, os vínculos com a campanha já não existem mais nesse momento,
    então os Status/Atributos apagados junto não geram uma rajada de eventos
    — só o `personagem_saiu`, capturado antes da exclusão.

Leitura de campos sempre via `instance.__dict__`: um campo adiado (`.only()`)
dispararia uma consulta só para montar a assinatura.
"""

from functools import lru_cache, partial

from django.db import transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete, post_init, post_save, pre_delete

from Midia.services import public_id_de
from Personagem.models import Atributo, Bonus, Defesa, Personagem, Status

from . import combate, escudo
from .models import NPC, Campanha, Combate, Criatura, ParticipanteCombate

_ENTIDADE = {Status: "status", Atributo: "atributo", Defesa: "defesa"}
_CAMPO_COMBATE = {Personagem: "personagem", NPC: "npc", Criatura: "criatura"}

# Campos que aparecem no Escudo. Para Status/Atributo/Defesa é a linha toda
# (menos a própria versão); para o Personagem, só o que o card mostra.
_CAMPOS_PERSONAGEM = ("nome", "nivel", "classe1", "usuario_id", "foto")
_CAMPOS_BONUS = ("content_type_id", "object_id", "valor", "ativo", "somente_teste")


@lru_cache(maxsize=None)
def _campos(model):
    # Em cache: roda no `post_init` de TODA instância carregada (uma listagem
    # de 200 status passa por aqui 200 vezes) e o resultado nunca muda.
    if model is Personagem:
        return _CAMPOS_PERSONAGEM
    if model is Bonus:
        return _CAMPOS_BONUS
    return tuple(f.attname for f in model._meta.concrete_fields if f.attname != "versao")


def _assinatura(model, instance):
    """Valores crus (barato: roda em todo `post_init`)."""
    valores = instance.__dict__
    return tuple(valores.get(campo) for campo in _campos(model))


def _normalizar(model, assinatura):
    """A foto pode ser string no carregamento e CloudinaryResource depois do
    upload: só o public_id diz se ela mudou. Feito só na hora de comparar
    (no save), não a cada instância carregada."""
    if model is not Personagem or assinatura is None:
        return assinatura
    return tuple(
        public_id_de(valor) if campo == "foto" else valor
        for campo, valor in zip(_campos(model), assinatura)
    )


def _ao_carregar(sender, instance, **kwargs):
    instance._escudo_assinatura = _assinatura(sender, instance)


def _mudou_algo_visivel(sender, instance, created):
    atual = _assinatura(sender, instance)
    antes = instance.__dict__.get("_escudo_assinatura")
    instance._escudo_assinatura = atual
    return created or _normalizar(sender, antes) != _normalizar(sender, atual)


def _ao_commit(funcao, *args):
    # `robust=True`: uma exceção aqui é registrada em log em vez de subir —
    # o commit já aconteceu, não faz sentido a requisição responder 500.
    transaction.on_commit(partial(funcao, *args), robust=True)


# ---------------------------------------------------------------------------
# Status / Atributo / Defesa
# ---------------------------------------------------------------------------

def _publicar_entidade(personagem_id, evento):
    escudo.publicar(escudo.campanhas_do_personagem(personagem_id), {**evento, "personagem": personagem_id})


def _publicar_linha(sender, pk, personagem_id):
    """Relê a linha e publica com o `valor_final` já calculado."""
    dados = escudo.linha_calculada(sender, pk)
    if dados is None:
        return  # excluída antes do commit; o post_delete dela já avisou
    _publicar_entidade(personagem_id, {"tipo": "upsert", "entidade": _ENTIDADE[sender], "dados": dados})


def _publicar_ficha(personagem_id):
    """
    Republica TODAS as linhas calculadas do personagem.

    Usado quando a gravação cascateia: um bônus muda o total do alvo, e um
    atributo (ou o Nível) muda o total de toda Defesa/Status apoiada nele —
    sem que a `versao` dessas linhas mude, então elas nunca seriam
    reenviadas e o Escudo ficaria com números velhos até a reconexão.

    Republicar a ficha inteira em vez de calcular exatamente quem depende de
    quem: são ~18 linhas de ~200 bytes, e o grafo de dependências é
    transitivo (um bônus por entidade pode encadear). O custo é uma ficha
    inteira por mudança de bônus/atributo, não por tecla digitada num Status.
    """
    campanhas = escudo.campanhas_do_personagem(personagem_id)
    if not campanhas:
        return
    for entidade, dados in escudo.linhas_calculadas(personagem_id):
        escudo.publicar(
            campanhas,
            {"tipo": "upsert", "entidade": entidade, "personagem": personagem_id, "dados": dados},
        )


def _entidade_salva(sender, instance, created, raw=False, **kwargs):
    if raw or not _mudou_algo_visivel(sender, instance, created):
        return

    # A serialização foi adiada para o `on_commit` (antes era feita aqui,
    # "sem consulta nenhuma"). Agora o serializer publica `valor_final`, que
    # depende dos bônus do alvo e do atributo vinculado: montá-lo dentro do
    # `post_save` custaria consultas a CADA gravação da ficha — e os botões
    # rápidos de Status gravam a cada clique. No commit, a gravação em si
    # volta a ser um único UPDATE.
    if sender is Atributo:
        # Atributo cascateia: Status, Defesas e Perícias que o referenciam
        # mudam de total junto, e a própria linha dele vai no lote.
        _ao_commit(_publicar_ficha, instance.personagem_id)
    else:
        _ao_commit(_publicar_linha, sender, instance.pk, instance.personagem_id)


def _entidade_excluida(sender, instance, **kwargs):
    _ao_commit(
        _publicar_entidade,
        instance.__dict__.get("personagem_id"),
        {
            "tipo": "remover",
            "entidade": _ENTIDADE[sender],
            "id": instance.pk,
            "versao": instance.__dict__.get("versao"),
        },
    )


# ---------------------------------------------------------------------------
# Bônus (alvo genérico — só interessa quando o alvo aparece no Escudo)
# ---------------------------------------------------------------------------

def _tipo_do_bonus(instance):
    return escudo._tipos_bonus().get(instance.__dict__.get("content_type_id"))


def _publicar_bonus(tipo, object_id, evento):
    personagem_id = (
        escudo.MODELOS_ALVO_BONUS[tipo]
        .objects.filter(pk=object_id)
        .values_list("personagem_id", flat=True)
        .first()
    )
    if personagem_id is None:
        return  # bônus órfão (alvo já excluído): não aparece em lugar nenhum
    _publicar_entidade(personagem_id, evento)


def _bonus_salvo(sender, instance, created, raw=False, **kwargs):
    tipo = _tipo_do_bonus(instance)
    if raw or tipo is None or not _mudou_algo_visivel(sender, instance, created):
        return
    evento = {"tipo": "upsert", "entidade": "bonus", "dados": escudo.bonus_dados(instance, tipo)}
    _ao_commit(_publicar_bonus, tipo, instance.object_id, evento)
    # O bônus mudou: o total do alvo (e de quem depende dele) mudou junto,
    # sem que a `versao` dessas linhas subisse. Ver `_publicar_ficha`.
    _ao_commit(_publicar_ficha_do_alvo, tipo, instance.object_id)


def _bonus_excluido(sender, instance, **kwargs):
    tipo = _tipo_do_bonus(instance)
    if tipo is None:
        return
    evento = {"tipo": "remover", "entidade": "bonus", "id": instance.pk, "versao": instance.__dict__.get("versao")}
    object_id = instance.__dict__.get("object_id")
    _ao_commit(_publicar_bonus, tipo, object_id, evento)
    _ao_commit(_publicar_ficha_do_alvo, tipo, object_id)


def _publicar_ficha_do_alvo(tipo, object_id):
    """Ponte bônus -> personagem: o Bonus só conhece o alvo genérico."""
    personagem_id = (
        escudo.MODELOS_ALVO_BONUS[tipo]
        .objects.filter(pk=object_id)
        .values_list("personagem_id", flat=True)
        .first()
    )
    if personagem_id is not None:
        _publicar_ficha(personagem_id)


# ---------------------------------------------------------------------------
# Personagem
# ---------------------------------------------------------------------------

def _publicar_personagem(personagem_id):
    campanhas = escudo.campanhas_do_personagem(personagem_id)
    if not campanhas:
        return
    personagem = Personagem.objects.select_related("usuario").filter(pk=personagem_id).first()
    if personagem is None:
        return
    dados = escudo.personagens_resumo([personagem])[0]
    escudo.publicar(campanhas, {"tipo": "upsert", "entidade": "personagem", "personagem": personagem_id, "dados": dados})


def _personagem_salvo(sender, instance, created, raw=False, **kwargs):
    # Personagem recém-criado ainda não está em campanha nenhuma: nada a avisar.
    if raw or created or not _mudou_algo_visivel(sender, instance, created):
        return
    _ao_commit(_publicar_personagem, instance.pk)
    # O Nível multiplica a contribuição do atributo em todo Status com
    # `atributo_nivel` marcado: subir de nível muda esses totais sem mexer
    # na linha do Status. Ver `_publicar_ficha`.
    _ao_commit(_publicar_ficha, instance.pk)


def _personagem_sera_excluido(sender, instance, **kwargs):
    # Os vínculos com as campanhas somem na mesma cascata: captura antes.
    campanhas = escudo.campanhas_do_personagem(instance.pk)
    if campanhas:
        _ao_commit(escudo.publicar, campanhas, {"tipo": "personagem_saiu", "personagem": instance.pk})


# ---------------------------------------------------------------------------
# Vínculos da campanha: personagens e jogadores
# ---------------------------------------------------------------------------

def _publicar_entradas(campanha_id, personagem_ids):
    campanha = Campanha.objects.filter(pk=campanha_id).first()
    if campanha is None:
        return
    for dados in escudo.montar_snapshot(campanha, personagem_ids)["personagens"]:
        escudo.publicar([campanha_id], {"tipo": "personagem_entrou", "personagem": dados["id"], "dados": dados})


def _publicar_saidas(campanha_id, personagem_ids):
    for personagem_id in personagem_ids:
        escudo.publicar([campanha_id], {"tipo": "personagem_saiu", "personagem": personagem_id})


def _pares(instance, reverse, pk_set):
    """Normaliza os dois lados do M2M (`campanha.personagens.add(p)` e
    `personagem.campanhas.add(c)`) em pares (campanha_id, {ids do outro lado})."""
    if not reverse:
        return [(instance.pk, set(pk_set))]
    return [(campanha_id, {instance.pk}) for campanha_id in pk_set]


def _personagens_da_campanha_mudaram(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear":
        # `clear()` não informa `pk_set`: guarda quem estava vinculado.
        instance._escudo_limpando = (
            set(instance.personagens.values_list("id", flat=True))
            if not reverse
            else set(instance.campanhas.values_list("id", flat=True))
        )
        return
    if action == "post_clear":
        pk_set = instance.__dict__.pop("_escudo_limpando", set())
        action = "post_remove"
    if action not in ("post_add", "post_remove") or not pk_set:
        return
    funcao = _publicar_entradas if action == "post_add" else _publicar_saidas
    for campanha_id, personagem_ids in _pares(instance, reverse, pk_set):
        _ao_commit(funcao, campanha_id, personagem_ids)
        if action == "post_remove":
            # Quem sai da mesa sai do combate dela — na MESMA transação (não
            # em on_commit), para a lista nunca apontar um personagem de fora.
            _remover_do_combate(campanha_id, personagem_ids)


def _remover_do_combate(campanha_id, personagem_ids):
    filtro = Q(tipo="personagem", personagem_id__in=personagem_ids)
    combate_id = Combate.objects.filter(campanha_id=campanha_id).values_list("id", flat=True).first()
    if combate_id is not None and ParticipanteCombate.objects.filter(filtro, combate_id=combate_id).exists():
        combate.remover(combate_id, filtro)


def _entidade_de_combate_sera_excluida(sender, instance, **kwargs):
    # Antes da cascata: tira as entradas pelo fluxo normal (passa a vez,
    # publica a remoção) em vez de deixá-las sumirem em silêncio.
    combate.remover_da_entidade(_CAMPO_COMBATE[sender], instance.pk)


def _jogadores_da_campanha_mudaram(sender, instance, action, reverse, pk_set, **kwargs):
    # Só a SAÍDA importa: quem entra conecta de novo e é autorizado no
    # handshake; quem sai precisa ter a conexão já aberta encerrada.
    if action == "pre_clear":
        instance._escudo_limpando = (
            set(instance.jogadores.values_list("id", flat=True))
            if not reverse
            else set(instance.campanhas.values_list("id", flat=True))
        )
        return
    if action == "post_clear":
        pk_set = instance.__dict__.pop("_escudo_limpando", set())
        action = "post_remove"
    if action != "post_remove" or not pk_set:
        return
    for campanha_id, usuario_ids in _pares(instance, reverse, pk_set):
        _ao_commit(escudo.publicar, [campanha_id], {"tipo": "acesso_revogado", "usuarios": sorted(usuario_ids)})


def _campanha_sera_excluida(sender, instance, **kwargs):
    _ao_commit(escudo.publicar, [instance.pk], {"tipo": "campanha_removida"})


def conectar():
    for model in (Personagem, Status, Atributo, Defesa, Bonus):
        post_init.connect(_ao_carregar, sender=model, dispatch_uid=f"escudo-init-{model._meta.label_lower}")

    for model in _ENTIDADE:
        uid = model._meta.label_lower
        post_save.connect(_entidade_salva, sender=model, dispatch_uid=f"escudo-save-{uid}")
        post_delete.connect(_entidade_excluida, sender=model, dispatch_uid=f"escudo-delete-{uid}")

    post_save.connect(_bonus_salvo, sender=Bonus, dispatch_uid="escudo-save-bonus")
    post_delete.connect(_bonus_excluido, sender=Bonus, dispatch_uid="escudo-delete-bonus")
    post_save.connect(_personagem_salvo, sender=Personagem, dispatch_uid="escudo-save-personagem")
    pre_delete.connect(_personagem_sera_excluido, sender=Personagem, dispatch_uid="escudo-predelete-personagem")
    pre_delete.connect(_campanha_sera_excluida, sender=Campanha, dispatch_uid="escudo-predelete-campanha")

    for model, campo in _CAMPO_COMBATE.items():
        pre_delete.connect(
            _entidade_de_combate_sera_excluida, sender=model, dispatch_uid=f"combate-predelete-{campo}"
        )

    m2m_changed.connect(
        _personagens_da_campanha_mudaram,
        sender=Campanha.personagens.through,
        dispatch_uid="escudo-m2m-personagens",
    )
    m2m_changed.connect(
        _jogadores_da_campanha_mudaram,
        sender=Campanha.jogadores.through,
        dispatch_uid="escudo-m2m-jogadores",
    )
