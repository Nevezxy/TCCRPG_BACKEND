"""
Escudo do Mestre — snapshot único + eventos incrementais em tempo real.

Duas peças compartilham os MESMOS formatos de dados, definidos aqui:

  1. `montar_snapshot`: a carga completa (GET /campanha/<pk>/escudo/). Um
     número FIXO de consultas, independente de quantos personagens a campanha
     tem — substitui as ~4 + (1 por status/atributo/defesa) requisições que
     cada card fazia antes.
  2. `publicar`: os eventos por entidade enviados pelo WebSocket (ver
     `consumers.py`) quando algo muda no banco. Cada evento carrega a LINHA
     inteira da entidade alterada (não só o campo), com a `versao` dela.

Por que a linha inteira e não só o campo que mudou: com a versão junto, o
evento é idempotente e autossuficiente — duplicado ou fora de ordem, o
cliente só aplica se for mais novo do que o que tem, e nunca depende de ter
recebido o evento anterior. Um diff por campo exigiria ordem garantida (dois
diffs de campos diferentes chegando trocados perderiam um deles). A linha de
um Status tem ~200 bytes; a diferença de tráfego é irrelevante, e quem
decide o que re-renderiza é o cliente, campo a campo.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from Personagem.models import Atributo, Bonus, Defesa, Status
from Personagem.serializers import AtributoSerializer, DefesaSerializer, StatusSerializer

logger = logging.getLogger(__name__)

# Alvos de bônus que o Escudo exibe. Bônus de arma, perícia etc. não entram
# em nenhum número do Escudo — nem no snapshot, nem nos eventos.
MODELOS_ALVO_BONUS = {"status": Status, "atributo": Atributo, "defesa": Defesa}

ENTIDADES_SERIALIZER = {
    "status": StatusSerializer,
    "atributo": AtributoSerializer,
    "defesa": DefesaSerializer,
}


def nome_grupo(campanha_id):
    return f"escudo_campanha_{campanha_id}"


# ---------------------------------------------------------------------------
# Formatos
# ---------------------------------------------------------------------------

def _tipos_bonus():
    """`{content_type_id: "status" | "atributo" | "defesa"}` — o cache de
    ContentType do Django torna isto gratuito depois da primeira chamada."""
    return {
        ContentType.objects.get_for_model(modelo).id: tipo
        for tipo, modelo in MODELOS_ALVO_BONUS.items()
    }


def bonus_dados(bonus, tipo):
    """Forma enxuta do Bônus. Não usa o BonusSerializer porque o `alvo_nome`
    dele resolve a GenericForeignKey (uma consulta por bônus) só para mostrar
    um nome que o Escudo não exibe."""
    return {
        "id": bonus.id,
        "tipo": tipo,
        "object_id": bonus.object_id,
        "valor": bonus.valor,
        "ativo": bonus.ativo,
        "somente_teste": bonus.somente_teste,
        "versao": bonus.versao,
    }


def personagens_resumo(personagens):
    """Resumo do personagem (mesmo formato de `personagens_info` da campanha)
    + `versao`. Import local: `serializers.py` importa deste app no topo."""
    from .serializers import CampanhaPersonagemResumoSerializer

    dados = CampanhaPersonagemResumoSerializer(personagens, many=True).data
    for item, personagem in zip(dados, personagens):
        item["versao"] = personagem.versao
    return dados


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def montar_snapshot(campanha, personagem_ids=None):
    """
    Carga completa do Escudo em 6 consultas fixas (personagens, enquadramento
    das fotos, status, atributos, defesas, bônus), qualquer que seja o número
    de personagens. `personagem_ids` restringe a um subconjunto — usado para
    montar o evento de "personagem entrou na campanha" com o mesmo formato.
    """
    qs = campanha.personagens.select_related("usuario").order_by("id")
    if personagem_ids is not None:
        qs = qs.filter(id__in=personagem_ids)
    personagens = list(qs)
    if not personagens:
        return {"personagens": []}

    ids = [p.id for p in personagens]
    status = list(Status.objects.filter(personagem_id__in=ids).order_by("ordem", "id"))
    atributos = list(Atributo.objects.filter(personagem_id__in=ids).order_by("id"))
    defesas = list(Defesa.objects.filter(personagem_id__in=ids).order_by("id"))

    tipos = _tipos_bonus()
    ct_por_tipo = {tipo: ct_id for ct_id, tipo in tipos.items()}
    alvos = {"status": status, "atributo": atributos, "defesa": defesas}
    dono = {}
    filtro = Q(pk__in=[])
    for tipo, objetos in alvos.items():
        if not objetos:
            continue
        filtro |= Q(content_type_id=ct_por_tipo[tipo], object_id__in=[o.id for o in objetos])
        for o in objetos:
            dono[(tipo, o.id)] = o.personagem_id
    bonus = list(Bonus.objects.filter(filtro).order_by("id"))

    por_personagem = {
        item["id"]: {**item, "status": [], "atributos": [], "defesas": [], "bonus": []}
        for item in personagens_resumo(personagens)
    }
    for chave, serializer_cls, objetos in (
        ("status", StatusSerializer, status),
        ("atributos", AtributoSerializer, atributos),
        ("defesas", DefesaSerializer, defesas),
    ):
        for dados in serializer_cls(objetos, many=True).data:
            por_personagem[dados["personagem"]][chave].append(dados)
    for b in bonus:
        tipo = tipos[b.content_type_id]
        personagem_id = dono.get((tipo, b.object_id))
        if personagem_id is not None:
            por_personagem[personagem_id]["bonus"].append(bonus_dados(b, tipo))

    return {"personagens": [por_personagem[i] for i in ids]}


# ---------------------------------------------------------------------------
# Publicação
# ---------------------------------------------------------------------------

def campanhas_do_personagem(personagem_id):
    """Uma consulta indexada na tabela M2M — o único custo fixo de uma
    gravação de ficha que não pertence a nenhuma campanha."""
    from .models import Campanha

    return list(
        Campanha.personagens.through.objects.filter(personagem_id=personagem_id).values_list(
            "campanha_id", flat=True
        )
    )


def publicar(campanha_ids, evento):
    """
    Envia `evento` para o grupo de cada campanha. Nunca propaga erro: a
    gravação que originou o evento já foi confirmada no banco (isto roda em
    `on_commit`) — uma falha do channel layer (ex.: Redis fora do ar) não
    pode transformar um PATCH bem-sucedido num 500. O cliente se recupera
    sozinho no próximo snapshot (reconexão).
    """
    if not campanha_ids:
        return
    camada = get_channel_layer()
    if camada is None:
        return
    enviar = async_to_sync(camada.group_send)
    for campanha_id in campanha_ids:
        try:
            enviar(nome_grupo(campanha_id), {"type": "escudo.evento", "evento": evento})
        except Exception:  # noqa: BLE001 — ver docstring
            logger.exception("Falha ao publicar evento do Escudo (campanha %s)", campanha_id)
