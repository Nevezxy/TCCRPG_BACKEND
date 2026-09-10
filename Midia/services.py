"""
Serviços de imagem (Cloudinary) compartilhados por todos os apps.

Três responsabilidades — nenhuma precisa de Pillow: o processamento pesado
(redimensionar, reencodar, converter formato) fica com o próprio Cloudinary.

1. UPLOAD padronizado: pasta por contexto, formatos aceitos, teto de
   resolução (`opcoes_upload`, `validar_arquivo`, `enviar_imagem`).
2. ENQUADRAMENTO guardado à parte do arquivo (`sanitizar_ajuste`,
   `ler_ajustes`, `gravar_ajuste`, `apagar_ajuste`).
3. EXCLUSÃO SEGURA de arquivos que deixaram de ser usados: fila durável
   gravada na mesma transação da troca/exclusão + rechecagem de uso
   imediatamente antes de apagar (`enfileirar_exclusao`, `processar_fila`).
"""

import json
import logging
import math
import threading

import cloudinary.api
import cloudinary.uploader
from cloudinary import CloudinaryResource
from cloudinary.models import CloudinaryField
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.db.models import F, JSONField, Q, TextField
from django.db.models.functions import Cast

from .models import AjusteImagem, ExclusaoImagemPendente

logger = logging.getLogger(__name__)

PADRAO = {
    # Prefixo de pasta no Cloudinary. Separar por ambiente (ex.: "tccrpg-dev")
    # é o que permite ao comando de órfãos nunca tocar no que é de outro.
    "PASTA_RAIZ": "tccrpg",
    # Liga a exclusão de fato no Cloudinary. Desligado, as exclusões só
    # ficam na fila — ver `app/settings.py` (padrão False com DEBUG).
    "EXCLUSAO_ATIVA": False,
    # Testes: processa a fila na hora, sem thread (o SQLite em memória não é
    # visível de outra thread).
    "PROCESSAMENTO_SINCRONO": False,
    "TAMANHO_MAXIMO_MB": 15,
    # Teto de resolução guardada. O frontend já envia menor que isso por
    # contexto; aqui é a rede de segurança para qualquer outro cliente.
    "LADO_MAXIMO": 4096,
    # Sem SVG de propósito: é XML que pode carregar script.
    "FORMATOS": ["jpg", "jpeg", "png", "webp", "gif", "avif", "heic", "heif"],
    "IDADE_MINIMA_ORFAO_HORAS": 24,
}

# Limites do enquadramento — os mesmos de `FOTO_ESCALA_MIN/MAX` no frontend.
ESCALA_MIN = 0.5
ESCALA_MAX = 4.0

# Lote máximo aceito por `cloudinary.api.delete_resources`.
LOTE_EXCLUSAO = 100

# Só para reaproveitar o parser do próprio pacote (`image/upload/v1/id.jpg`).
_PARSER = CloudinaryField()


def config():
    return {**PADRAO, **getattr(settings, "IMAGENS", {})}


# ---------------------------------------------------------------------------
# Descoberta dos campos de imagem
# ---------------------------------------------------------------------------

def campos_cloudinary(model):
    """
    Campos de imagem de `model`, INCLUINDO os herdados — `Arma` herda `foto`
    de `Item`. É o que os signals precisam: o Django dispara pre/post_save só
    para a classe concreta da instância, não para a mãe.
    """
    return [f for f in model._meta.concrete_fields if isinstance(f, CloudinaryField)]


def colunas_cloudinary():
    """
    Pares (model, campo) onde a coluna de imagem REALMENTE mora. Usa só
    `local_fields`, para a mesma coluna não ser varrida duas vezes via
    herança multi-tabela.
    """
    for model in apps.get_models():
        for campo in model._meta.local_fields:
            if isinstance(campo, CloudinaryField):
                yield model, campo


def campos_de_texto():
    """
    Campos onde uma URL do Cloudinary pode ter sido COPIADA como texto: todo
    JSONField (o `dados` do Canva guarda a URL de uma Imagem da campanha num
    objeto do quadro) e os `conteudo` Markdown (um `![](url)` escrito à mão).
    Os models do próprio Midia ficam de fora — o `dados` do ajuste nunca tem
    URL.
    """
    for model in apps.get_models():
        if model._meta.app_label == "Midia":
            continue
        for campo in model._meta.local_fields:
            if isinstance(campo, JSONField) or (isinstance(campo, TextField) and campo.name == "conteudo"):
                yield model, campo


def public_id_de(valor):
    """`CloudinaryResource`, string gravada no banco ou vazio → public_id ou None."""
    if not valor:
        return None
    if isinstance(valor, CloudinaryResource):
        return valor.public_id or None
    if isinstance(valor, str):
        return _PARSER.parse_cloudinary_resource(valor).public_id or None
    return None


def url_de(valor):
    if not valor:
        return None
    url = getattr(valor, "url", None)
    return url or (valor if isinstance(valor, str) else None)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def opcoes_upload(model, campo):
    """
    Opções de upload por contexto. A pasta `{raiz}/{app}/{model}/{campo}`
    deixa o console do Cloudinary navegável e, principalmente, dá ao comando
    de órfãos um escopo seguro para varrer.

    A transformação de entrada `c_limit` só REDUZ o que passar do teto (nunca
    amplia). `quality: auto:best` evita perda perceptível na reencodificação.
    """
    cfg = config()
    pasta = "/".join(
        [cfg["PASTA_RAIZ"].strip("/"), model._meta.app_label.lower(), model._meta.model_name, campo]
    )
    return {
        "folder": pasta,
        "resource_type": "image",
        "type": "upload",
        "use_filename": False,
        "unique_filename": True,
        "overwrite": False,
        "allowed_formats": cfg["FORMATOS"],
        "transformation": [
            {"width": cfg["LADO_MAXIMO"], "height": cfg["LADO_MAXIMO"], "crop": "limit", "quality": "auto:best"}
        ],
    }


def validar_arquivo(arquivo):
    """
    Checagem barata ANTES de gastar um upload. Não é a barreira final — o
    Cloudinary reconhece o formato real pelo conteúdo e recusa o que não
    estiver em `allowed_formats` — mas devolve um erro legível na hora.
    """
    cfg = config()
    limite = cfg["TAMANHO_MAXIMO_MB"] * 1024 * 1024
    if getattr(arquivo, "size", 0) > limite:
        raise ValueError(f"A imagem passa do limite de {cfg['TAMANHO_MAXIMO_MB']} MB.")

    nome = getattr(arquivo, "name", "") or ""
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    tipo = (getattr(arquivo, "content_type", "") or "").lower()

    if tipo == "image/svg+xml" or extensao == "svg":
        raise ValueError("Imagens SVG não são aceitas. Envie JPG, PNG, WebP, GIF ou AVIF.")
    if tipo and not tipo.startswith("image/"):
        raise ValueError("O arquivo enviado não é uma imagem.")
    if extensao and extensao not in cfg["FORMATOS"]:
        raise ValueError(f"Formato .{extensao} não é aceito. Envie JPG, PNG, WebP, GIF ou AVIF.")


def enviar_imagem(arquivo, model, campo):
    """Upload explícito (em vez do implícito do `CloudinaryField.pre_save`),
    para o serializer saber o `public_id` novo e poder desfazê-lo se o save
    falhar depois."""
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    return cloudinary.uploader.upload_resource(arquivo, **opcoes_upload(model, campo))


def descartar_uploads(public_ids):
    """
    Desfaz uploads que NUNCA chegaram ao banco (o save falhou depois do
    upload). Por nunca terem sido referenciados, são seguros de apagar em
    qualquer ambiente — por isso ignoram `EXCLUSAO_ATIVA`. Se o Cloudinary
    falhar, vão para a fila em vez de virarem órfãos silenciosos.
    """
    for public_id in [p for p in public_ids if p]:
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
            logger.info("Upload descartado no Cloudinary: %s", public_id)
        except Exception:  # noqa: BLE001 — qualquer falha de rede/API cai na fila
            logger.warning("Falha ao descartar upload %s; enfileirado.", public_id, exc_info=True)
            enfileirar_exclusao([public_id], "upload_descartado")


# ---------------------------------------------------------------------------
# Enquadramento
# ---------------------------------------------------------------------------

def _numero(valor, padrao):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return padrao
    return float(valor) if math.isfinite(valor) else padrao


def _limitar(n, minimo, maximo):
    return min(maximo, max(minimo, n))


def sanitizar_ajuste(bruto):
    """
    Valida o enquadramento vindo do cliente — objeto JSON ou string JSON (no
    multipart não dá para mandar objeto). Espelha `sanitizarFotoAjuste` do
    frontend: campos fora da faixa são presos aos limites, chaves
    desconhecidas descartadas. Só números saem daqui — o frontend usa esses
    valores direto em `style`, então nada de texto arbitrário.

    Devolve o dict limpo, ou None para "sem ajuste" (null, "" ou "null").
    Levanta ValueError para JSON malformado ou tipo errado.
    """
    if bruto is None or bruto == "" or bruto == "null":
        return None
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except ValueError as exc:
            raise ValueError("Ajuste de imagem inválido (JSON malformado).") from exc
        if bruto is None:
            return None
    if not isinstance(bruto, dict):
        raise ValueError("Ajuste de imagem precisa ser um objeto.")

    ajuste = {
        "modo": "conter" if bruto.get("modo") == "conter" else "cobrir",
        "escala": _limitar(_numero(bruto.get("escala"), 1.0), ESCALA_MIN, ESCALA_MAX),
        "offsetX": _limitar(_numero(bruto.get("offsetX"), 0.0), -1.0, 1.0),
        "offsetY": _limitar(_numero(bruto.get("offsetY"), 0.0), -1.0, 1.0),
    }
    ar = _numero(bruto.get("ar"), 0.0)
    if 0 < ar < 100:
        ajuste["ar"] = round(ar, 6)
    return ajuste


def _content_type_do_campo(model, campo):
    return ContentType.objects.get_for_model(model._meta.get_field(campo).model)


def ler_ajustes(model, pks, campos):
    """`{pk: {campo: dados}}` para vários objetos de uma vez (uma query por
    model declarante) — é o que evita N+1 nas listagens."""
    pks = [pk for pk in pks if pk is not None]
    if not pks or not campos:
        return {}

    por_content_type = {}
    for campo in campos:
        por_content_type.setdefault(_content_type_do_campo(model, campo).id, []).append(campo)

    resultado = {}
    for ct_id, campos_do_ct in por_content_type.items():
        linhas = AjusteImagem.objects.filter(
            content_type_id=ct_id, object_id__in=pks, campo__in=campos_do_ct
        ).values_list("object_id", "campo", "dados")
        for object_id, campo, dados in linhas:
            resultado.setdefault(object_id, {})[campo] = dados
    return resultado


def gravar_ajuste(instance, campo, dados):
    ct = _content_type_do_campo(type(instance), campo)
    AjusteImagem.objects.update_or_create(
        content_type=ct, object_id=instance.pk, campo=campo, defaults={"dados": dados}
    )


def apagar_ajuste(instance, campo=None):
    """Apaga o ajuste de um campo (ou de todos os campos de imagem do objeto)."""
    model = type(instance)
    campos = [campo] if campo else [f.name for f in campos_cloudinary(model)]
    for nome in campos:
        ct = _content_type_do_campo(model, nome)
        AjusteImagem.objects.filter(content_type=ct, object_id=instance.pk, campo=nome).delete()


# ---------------------------------------------------------------------------
# Referências e exclusão
# ---------------------------------------------------------------------------

def referencias_ativas(public_ids):
    """
    Quais destes `public_ids` ainda são usados em QUALQUER lugar do banco.

    Duas passadas:
      1. colunas de imagem: busca candidatas por substring (LIKE) e confirma
         com o public_id EXATO depois de parsear — "abc" não pode "proteger"
         "abcd";
      2. texto livre (JSON do Canva, Markdown): basta a substring aparecer.
         Aqui um falso positivo só significa NÃO apagar — o lado seguro.

    Roda depois do commit, então o próprio objeto que acabou de trocar ou
    excluir a imagem já não a referencia — não precisa de exceção para ele.
    """
    ids = {p for p in public_ids if p}
    if not ids:
        return set()

    em_uso = set()
    for model, campo in colunas_cloudinary():
        filtro = Q()
        for public_id in ids:
            filtro |= Q(**{f"{campo.name}__contains": public_id})
        for valor in model._base_manager.filter(filtro).values_list(campo.name, flat=True):
            encontrado = public_id_de(valor)
            if encontrado in ids:
                em_uso.add(encontrado)

    restantes = ids - em_uso
    for model, campo in campos_de_texto():
        if not restantes:
            break
        filtro = Q()
        for public_id in restantes:
            filtro |= Q(_midia_txt__contains=public_id)
        textos = (
            model._base_manager.annotate(_midia_txt=Cast(campo.name, TextField()))
            .filter(filtro)
            .values_list("_midia_txt", flat=True)
        )
        for texto in textos:
            for public_id in list(restantes):
                if public_id in (texto or ""):
                    em_uso.add(public_id)
                    restantes.discard(public_id)

    return em_uso


def enfileirar_exclusao(public_ids, motivo):
    """
    Grava na fila DENTRO da transação atual e agenda o processamento para
    DEPOIS do commit. Em rollback, as linhas somem junto — nada é apagado
    se a troca/exclusão não se concretizou.
    """
    ids = sorted({p for p in public_ids if p})
    if not ids:
        return
    ExclusaoImagemPendente.objects.bulk_create(
        [ExclusaoImagemPendente(public_id=p, motivo=motivo) for p in ids],
        ignore_conflicts=True,
    )
    transaction.on_commit(agendar_processamento)


# Uma exclusão em cascata (ex.: Campanha inteira) dispara dezenas de
# `on_commit`. Em vez de uma thread por callback, uma só por processo, que dá
# mais uma volta se chegou trabalho novo enquanto ela rodava.
_trava = threading.Lock()
_rodando = False
_de_novo = False


def agendar_processamento():
    global _rodando, _de_novo
    cfg = config()
    if not cfg["EXCLUSAO_ATIVA"]:
        return
    if cfg["PROCESSAMENTO_SINCRONO"]:
        processar_fila()
        return

    with _trava:
        if _rodando:
            _de_novo = True
            return
        _rodando = True
    # Fora da resposta: apagar no Cloudinary é chamada de rede, e excluir uma
    # campanha grande não pode travar a requisição. Se o processo morrer no
    # meio, a fila continua no banco para o comando terminar.
    threading.Thread(target=_laco_processamento, name="midia-exclusao", daemon=True).start()


def _laco_processamento():
    global _rodando, _de_novo
    try:
        while True:
            try:
                processar_fila()
            except Exception:  # noqa: BLE001 — a fila fica para o comando
                logger.exception("Falha ao processar a fila de exclusão de imagens.")
            with _trava:
                if not _de_novo:
                    _rodando = False
                    return
                _de_novo = False
    finally:
        # A thread abriu a própria conexão com o banco; fechar evita vazar.
        connection.close()


def apagar_no_cloudinary(public_ids):
    """
    Apaga em lotes de 100. "not_found" conta como sucesso: o objetivo — o
    arquivo não existir mais — já está cumprido (ex.: apagado à mão no
    console). Devolve (apagadas, {public_id: erro}).
    """
    ids = list(public_ids)
    apagadas, falhas = [], {}
    for i in range(0, len(ids), LOTE_EXCLUSAO):
        lote = ids[i:i + LOTE_EXCLUSAO]
        try:
            resposta = cloudinary.api.delete_resources(lote, resource_type="image", type="upload", invalidate=True)
        except Exception as exc:  # noqa: BLE001 — qualquer falha de rede/API
            for public_id in lote:
                falhas[public_id] = str(exc)[:500]
            continue
        situacao = (resposta or {}).get("deleted", {})
        for public_id in lote:
            if situacao.get(public_id) in ("deleted", "not_found"):
                apagadas.append(public_id)
            else:
                falhas[public_id] = str(situacao.get(public_id) or "sem resposta do Cloudinary")[:500]
    return apagadas, falhas


def processar_fila(limite=200):
    """
    Drena a fila: RECHECA o uso de cada arquivo imediatamente antes de apagar
    (outra entidade pode ter passado a usá-lo, ex.: a URL colada num objeto
    do Canva), apaga o resto e registra falhas para nova tentativa.
    """
    pendentes = list(ExclusaoImagemPendente.objects.order_by("id")[:limite])
    if not pendentes:
        return {"apagadas": 0, "em_uso": 0, "falhas": 0}

    ids = {p.public_id for p in pendentes}
    em_uso = referencias_ativas(ids)
    if em_uso:
        # Ainda usado: sai da fila sem apagar. Se um dia deixar de ser usado
        # sem passar por um signal, o comando de órfãos o encontra.
        ExclusaoImagemPendente.objects.filter(public_id__in=em_uso).delete()
        logger.info("Imagens ainda em uso, mantidas no Cloudinary: %s", sorted(em_uso))

    apagadas, falhas = apagar_no_cloudinary(sorted(ids - em_uso))
    if apagadas:
        ExclusaoImagemPendente.objects.filter(public_id__in=apagadas).delete()
        logger.info("Imagens apagadas do Cloudinary: %s", apagadas)
    for public_id, erro in falhas.items():
        ExclusaoImagemPendente.objects.filter(public_id=public_id).update(
            tentativas=F("tentativas") + 1, ultimo_erro=erro
        )
        logger.warning("Falha ao apagar %s do Cloudinary: %s", public_id, erro)

    return {"apagadas": len(apagadas), "em_uso": len(em_uso), "falhas": len(falhas)}
