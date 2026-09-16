"""
Combate do Escudo do Mestre — lista de iniciativa, PV de combate e turno.

Mesma arquitetura do resto do Escudo (ver `escudo.py`): o cliente carrega o
estado uma vez (GET /campanha/<pk>/combate/) e depois só recebe eventos pelo
WebSocket que já existe — nenhuma conexão nova, nenhum polling.

CONSISTÊNCIA. Toda escrita é um UPDATE que incrementa `versao` no próprio
banco, e o evento/resposta leva essa versão. O cliente descarta o que for
mais velho do que já tem, então respostas e eventos fora de ordem nunca
fazem a tela voltar para um valor antigo.

OPERAÇÕES RELATIVAS NO BANCO. Dano é `pv_atual = GREATEST(pv_atual - n, 0)`
num único UPDATE, e "próximo turno" é calculado sob `select_for_update` do
combate. Dois danos (ou dois cliques em "próximo") disparados antes da
primeira resposta se SOMAM — um "ler, subtrair em Python, gravar" perderia
um deles.

EVENTOS ENXUTOS. Editar iniciativa/PV é a operação mais frequente da mesa, e
nome/foto de um participante nunca mudam depois que ele entra. Por isso há
duas formas da linha: a completa (`participantes_dados`, só na carga e ao
adicionar) e a de valores (`valores_participante`, uma consulta por
`values()` — sem JOIN, sem ler ajuste de imagem).

VISIBILIDADE. O grupo do WebSocket é a mesa toda; o filtro por destinatário
fica em `filtrar_evento`, chamado pelo consumer. Jogador só recebe linhas
quando o mestre liga `visivel_para_jogadores`, e mesmo assim sem os números
de PV (só o percentual da barra).
"""

import re
from functools import partial

from django.db import transaction
from django.db.models import F, IntegerField, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from Midia.services import ler_ajustes, url_de
from Personagem.models import Personagem

from . import escudo
from .models import NPC, Combate, Criatura, ParticipanteCombate

LIMITE_PARTICIPANTES = 200
LIMITE_QUANTIDADE = 20
LIMITE_INICIATIVA = 9999
LIMITE_PV = 1_000_000

MODELO_POR_TIPO = {"personagem": Personagem, "npc": NPC, "criatura": Criatura}

CAMPOS_VALORES = ("id", "versao", "iniciativa", "pv_atual", "pv_max")

ORDEM = ("-iniciativa", "id")


class ErroCombate(Exception):
    """Regra de negócio violada — a view devolve 400 com a mensagem."""


# ---------------------------------------------------------------------------
# PV a partir da ficha
# ---------------------------------------------------------------------------

_NUMERO = re.compile(r"\d+")


def pv_da_ficha(ficha):
    """
    PV máximo da `ficha` de um NPC/Criatura, ou None. A ficha guarda o PV
    como TEXTO livre digitado no editor (`public/ficha-rpg-editor.html`):
    "45 / 45" no modelo TCC (`staticInfo.hp`) e "200 (16d20+32)" no D&D
    (`combat.hp`). A regra: ignora o que estiver entre parênteses (a fórmula)
    e usa o ÚLTIMO número — em "atual / máximo" é o máximo, e num número
    solto é ele mesmo. Não reconhecer vira None e o mestre digita na lista.
    """
    if not isinstance(ficha, dict):
        return None
    bruto = None
    for bloco in ("staticInfo", "combat"):
        dados = ficha.get(bloco)
        if isinstance(dados, dict) and dados.get("hp") not in (None, ""):
            bruto = dados["hp"]
            break
    if isinstance(bruto, bool):
        return None
    if isinstance(bruto, (int, float)):
        return max(0, min(int(bruto), LIMITE_PV))
    if not isinstance(bruto, str):
        return None
    numeros = _NUMERO.findall(bruto.split("(", 1)[0])
    if not numeros:
        return None
    return min(int(numeros[-1]), LIMITE_PV)


# ---------------------------------------------------------------------------
# Formatos
# ---------------------------------------------------------------------------

def combate_dados(combate):
    return {
        "id": combate.id,
        "versao": combate.versao,
        "rodada": combate.rodada,
        "turno_participante": combate.turno_participante_id,
        "visivel_para_jogadores": combate.visivel_para_jogadores,
    }


def _ajustes_das_fotos(entidades_por_tipo):
    """`{tipo: {pk: ajuste}}` — uma consulta por tipo presente, não por linha."""
    resultado = {}
    for tipo, entidades in entidades_por_tipo.items():
        pks = {e.pk for e in entidades if e.foto}
        lidos = ler_ajustes(MODELO_POR_TIPO[tipo], pks, ["foto"]) if pks else {}
        resultado[tipo] = {pk: campos.get("foto") for pk, campos in lidos.items()}
    return resultado


def _identidade(tipo, entidade, ajustes):
    return {
        "tipo": tipo,
        "entidade_id": entidade.pk,
        "nome": entidade.nome,
        "foto": url_de(entidade.foto),
        "foto_ajuste": ajustes.get(tipo, {}).get(entidade.pk) if entidade.foto else None,
    }


def participantes_dados(participantes):
    """Linhas completas (identidade + valores), na ordem recebida."""
    por_tipo = {}
    for p in participantes:
        por_tipo.setdefault(p.tipo, []).append(p.entidade)
    ajustes = _ajustes_das_fotos(por_tipo)
    return [
        {
            **_identidade(p.tipo, p.entidade, ajustes),
            **{campo: getattr(p, campo) for campo in CAMPOS_VALORES},
        }
        for p in participantes
    ]


def _participantes_com_entidade(filtro):
    """Participantes já com nome/foto da entidade num JOIN só — e sem trazer
    a `ficha`/`conteudo` (JSON e Markdown grandes) que a lista não usa."""
    return (
        ParticipanteCombate.objects.filter(filtro)
        .select_related("personagem", "npc", "criatura")
        .only(
            *CAMPOS_VALORES,
            "tipo",
            "combate",
            "personagem__id", "personagem__nome", "personagem__foto",
            "npc__id", "npc__nome", "npc__foto",
            "criatura__id", "criatura__nome", "criatura__foto",
        )
        .order_by(*ORDEM)
    )


def valores_participante(participante_id):
    return ParticipanteCombate.objects.filter(pk=participante_id).values(*CAMPOS_VALORES).first()


def publico_participante(dados):
    """Linha como o JOGADOR a vê: sem os números de PV, só o percentual da
    barra ("está ferido?"), limitado a 100 para não denunciar PV extra."""
    dados = dict(dados)
    pv_atual = dados.pop("pv_atual", None)
    pv_max = dados.pop("pv_max", None)
    dados["pv_percentual"] = (
        min(100, round(100 * pv_atual / pv_max)) if pv_atual is not None and pv_max else None
    )
    return dados


def montar_estado(combate, gerencia):
    participantes = list(_participantes_com_entidade(Q(combate_id=combate.pk)))
    linhas = participantes_dados(participantes)
    if not gerencia:
        linhas = [publico_participante(linha) for linha in linhas]
    return {"combate": combate_dados(combate), "participantes": linhas, "pode_gerenciar": gerencia}


def candidatos(campanha):
    """Tudo que pode entrar no combate, numa forma enxuta para o modal: 3
    listas + no máximo 3 consultas de enquadramento de foto."""
    grupos = {
        "personagem": list(campanha.personagens.only("id", "nome", "foto").order_by("nome", "id")),
        "npc": list(campanha.npcs.only("id", "nome", "foto", "ficha").order_by("nome", "id")),
        "criatura": list(campanha.criaturas.only("id", "nome", "foto", "ficha").order_by("nome", "id")),
    }
    ajustes = _ajustes_das_fotos(grupos)
    return [
        {
            **_identidade(tipo, entidade, ajustes),
            "pv_max": None if tipo == "personagem" else pv_da_ficha(entidade.ficha),
        }
        for tipo, entidades in grupos.items()
        for entidade in entidades
    ]


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

def _publicar(campanha_id, evento):
    # Depois do commit: um rollback nunca vira evento (ver `signals.py`).
    transaction.on_commit(partial(escudo.publicar, [campanha_id], evento), robust=True)


def filtrar_evento(evento, gerencia, visivel):
    """
    Decide o que UM destinatário recebe de um evento de combate. Devolve
    `(evento ou None, visibilidade atualizada)` — o consumer guarda a
    visibilidade que viu por último, e é o próprio evento `combate` que a
    atualiza (sem consulta ao banco por mensagem).
    """
    tipo = evento.get("tipo")
    if tipo == "combate":
        return evento, bool(evento["dados"].get("visivel_para_jogadores"))
    if gerencia:
        return evento, visivel
    if not visivel:
        return None, visivel
    if tipo == "combate_participantes":
        return {**evento, "dados": [publico_participante(d) for d in evento["dados"]]}, visivel
    if tipo == "combate_valores":
        return {**evento, "dados": publico_participante(evento["dados"])}, visivel
    return evento, visivel


# ---------------------------------------------------------------------------
# Operações
# ---------------------------------------------------------------------------

def obter(campanha, criar=False):
    if criar:
        return Combate.objects.get_or_create(campanha=campanha)[0]
    return Combate.objects.filter(campanha=campanha).first()


def _travar(combate_id):
    # Sem select_related: `select_for_update` + FK nulável quebra no
    # PostgreSQL (ver README, seção de testes).
    return Combate.objects.select_for_update().get(pk=combate_id)


def _ordem_ids(combate_id):
    return list(
        ParticipanteCombate.objects.filter(combate_id=combate_id).order_by(*ORDEM).values_list("id", flat=True)
    )


def _gravar_combate(combate_id, **campos):
    Combate.objects.filter(pk=combate_id).update(
        **campos, versao=F("versao") + 1, atualizado_em=timezone.now()
    )
    combate = Combate.objects.get(pk=combate_id)
    dados = combate_dados(combate)
    _publicar(combate.campanha_id, {"tipo": "combate", "dados": dados})
    return dados


def resolver_entidades(campanha, entradas):
    """`[(tipo, id, quantidade)]` → `[(tipo, entidade, quantidade)]`, garantindo
    que tudo pertence a ESTA campanha (id de outra mesa vira erro, não 404
    silencioso nem vazamento)."""
    ids_por_tipo = {}
    for tipo, pk, _ in entradas:
        ids_por_tipo.setdefault(tipo, set()).add(pk)
    fontes = {
        "personagem": campanha.personagens.all(),
        "npc": campanha.npcs.all(),
        "criatura": campanha.criaturas.all(),
    }
    encontrados = {}
    for tipo, ids in ids_por_tipo.items():
        campos = ("id",) if tipo == "personagem" else ("id", "ficha")
        encontrados[tipo] = {e.pk: e for e in fontes[tipo].filter(id__in=ids).only(*campos)}
        faltando = ids - encontrados[tipo].keys()
        if faltando:
            raise ErroCombate(f"Entidade não encontrada nesta campanha: {tipo} {sorted(faltando)}.")
    return [(tipo, encontrados[tipo][pk], quantidade) for tipo, pk, quantidade in entradas]


def _novo_participante(combate_id, tipo, entidade):
    pv = None if tipo == "personagem" else pv_da_ficha(entidade.ficha)
    return ParticipanteCombate(
        combate_id=combate_id, tipo=tipo, pv_atual=pv, pv_max=pv, **{tipo: entidade}
    )


def adicionar(combate, entidades=None, todos_personagens=False):
    """
    Adiciona `entidades` (`[(tipo, entidade, quantidade)]`, repetições
    permitidas) ou, com `todos_personagens`, os personagens da campanha que
    ainda não estão no combate. A trava no combate serializa dois "adicionar
    todos" simultâneos (duas abas) — sem ela ambos veriam o combate vazio e
    duplicariam todo mundo.
    """
    with transaction.atomic():
        combate = _travar(combate.pk)
        if todos_personagens:
            ja_estao = ParticipanteCombate.objects.filter(combate_id=combate.pk, tipo="personagem").values_list(
                "personagem_id", flat=True
            )
            personagens = combate.campanha.personagens.exclude(id__in=ja_estao).only("id").order_by("id")
            novos = [_novo_participante(combate.pk, "personagem", p) for p in personagens]
        else:
            novos = [
                _novo_participante(combate.pk, tipo, entidade)
                for tipo, entidade, quantidade in entidades
                for _ in range(quantidade)
            ]
        if not novos:
            return []

        total = ParticipanteCombate.objects.filter(combate_id=combate.pk).count() + len(novos)
        if total > LIMITE_PARTICIPANTES:
            raise ErroCombate(f"Um combate comporta no máximo {LIMITE_PARTICIPANTES} participantes.")

        criados = ParticipanteCombate.objects.bulk_create(novos)
        linhas = participantes_dados(list(_participantes_com_entidade(Q(pk__in=[p.pk for p in criados]))))
        _publicar(combate.campanha_id, {"tipo": "combate_participantes", "dados": linhas})
        return linhas


def remover(combate_id, filtro):
    """
    Remove os participantes do combate que casam com `filtro`. Se quem está
    agindo sai, a vez passa ao próximo que FICA (virando a rodada se ele era
    o último); se a lista esvazia, o combate volta à rodada 1.

    Devolve `(ids removidos, dados do combate ou None se não mudou)`.
    """
    with transaction.atomic():
        combate = _travar(combate_id)
        ordem = _ordem_ids(combate.pk)
        removidos = list(
            ParticipanteCombate.objects.filter(filtro, combate_id=combate.pk).values_list("id", flat=True)
        )
        if not removidos:
            return [], None

        fora = set(removidos)
        restantes = [pk for pk in ordem if pk not in fora]
        dados_combate = None
        if not restantes:
            if combate.rodada != 1 or combate.turno_participante_id is not None:
                dados_combate = _gravar_combate(combate.pk, rodada=1, turno_participante=None)
        elif combate.turno_participante_id in fora:
            indice = ordem.index(combate.turno_participante_id)
            depois = [pk for pk in ordem[indice + 1:] if pk not in fora]
            if depois:
                dados_combate = _gravar_combate(combate.pk, turno_participante_id=depois[0])
            else:
                dados_combate = _gravar_combate(
                    combate.pk, turno_participante_id=restantes[0], rodada=combate.rodada + 1
                )

        # O turno já foi movido acima: o SET_NULL da exclusão não encontra
        # mais nenhum combate apontando para quem sai.
        ParticipanteCombate.objects.filter(pk__in=removidos).delete()
        _publicar(combate.campanha_id, {"tipo": "combate_removidos", "ids": removidos})
        return removidos, dados_combate


def remover_da_entidade(campo, entidade_id):
    """Chamado pelos signals antes de excluir um Personagem/NPC/Criatura (ou
    de o personagem sair da campanha): tira as entradas dele de cada combate
    PELO FLUXO NORMAL — passando a vez e avisando os clientes — em vez de
    deixar a cascata apagar em silêncio."""
    filtro = Q(**{f"{campo}_id": entidade_id})
    for combate_id in set(ParticipanteCombate.objects.filter(filtro).values_list("combate_id", flat=True)):
        remover(combate_id, filtro)


def atualizar_participante(participante, campos):
    with transaction.atomic():
        alterados = ParticipanteCombate.objects.filter(pk=participante.pk).update(
            **campos, versao=F("versao") + 1
        )
        if not alterados:
            return None
        dados = valores_participante(participante.pk)
        _publicar(participante.combate.campanha_id, {"tipo": "combate_valores", "dados": dados})
        return dados


def aplicar_dano(participante, valor):
    if participante.pv_atual is None:
        raise ErroCombate("Este participante não tem Pontos de Vida no combate.")
    with transaction.atomic():
        alterados = ParticipanteCombate.objects.filter(pk=participante.pk, pv_atual__isnull=False).update(
            pv_atual=Greatest(F("pv_atual") - Value(valor), Value(0), output_field=IntegerField()),
            versao=F("versao") + 1,
        )
        if not alterados:
            return None
        dados = valores_participante(participante.pk)
        _publicar(participante.combate.campanha_id, {"tipo": "combate_valores", "dados": dados})
        return dados


def mudar_turno(combate, acao):
    """
    `proximo` / `anterior`, calculado SOB TRAVA a partir do turno gravado —
    o cliente manda a intenção, não o id do próximo. Assim dois cliques
    rápidos avançam dois turnos, mesmo com a primeira resposta a caminho.

    Sem turno ativo (combate recém-criado, reiniciado, ou quem agia foi
    excluído numa cascata), qualquer ação começa pelo primeiro da ordem.
    """
    with transaction.atomic():
        combate = _travar(combate.pk)
        ordem = _ordem_ids(combate.pk)
        if not ordem:
            raise ErroCombate("Adicione participantes antes de iniciar os turnos.")

        rodada = combate.rodada
        atual = combate.turno_participante_id
        if atual not in ordem:
            proximo = ordem[0]
        elif acao == "proximo":
            indice = ordem.index(atual) + 1
            if indice >= len(ordem):
                indice = 0
                rodada += 1
            proximo = ordem[indice]
        else:
            indice = ordem.index(atual) - 1
            if indice < 0:
                if rodada > 1:
                    indice = len(ordem) - 1
                    rodada -= 1
                else:
                    indice = 0
            proximo = ordem[indice]

        return _gravar_combate(combate.pk, turno_participante_id=proximo, rodada=rodada)


def reiniciar(combate):
    with transaction.atomic():
        combate = _travar(combate.pk)
        return _gravar_combate(combate.pk, rodada=1, turno_participante=None)


def definir_visibilidade(combate, visivel):
    with transaction.atomic():
        combate = _travar(combate.pk)
        return _gravar_combate(combate.pk, visivel_para_jogadores=visivel)
