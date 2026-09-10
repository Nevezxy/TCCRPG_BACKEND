"""
Ciclo de vida das imagens no banco → fila de exclusão do Cloudinary.

Ficam em signals (e não só no serializer) para cobrir TODO caminho de
gravação e exclusão: as ~25 views function-based que chamam `.delete()`
direto, o admin, e principalmente a CASCATA — excluir uma Campanha apaga
todas as entidades dela sem passar por serializer nenhum. Com signals
conectados, o Django deixa de usar o "fast delete" em massa e carrega cada
objeto da cascata por inteiro, então `post_delete` enxerga as imagens de
todos eles.

O que é decidido aqui:
  - troca ou remoção de imagem → o arquivo ANTIGO vai para a fila e o
    enquadramento dele é apagado (não serve para outra imagem);
  - exclusão do objeto → todas as imagens dele vão para a fila, e os ajustes
    somem junto.
Quem apaga de fato é `services.processar_fila`, depois do commit.
"""

from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save

from .services import apagar_ajuste, campos_cloudinary, enfileirar_exclusao, public_id_de


def conectar():
    for model in apps.get_models():
        if model._meta.app_label == "Midia" or not campos_cloudinary(model):
            continue
        uid = model._meta.label_lower
        pre_save.connect(_antes_de_salvar, sender=model, dispatch_uid=f"midia-pre-save-{uid}")
        post_save.connect(_depois_de_salvar, sender=model, dispatch_uid=f"midia-post-save-{uid}")
        post_delete.connect(_depois_de_excluir, sender=model, dispatch_uid=f"midia-post-delete-{uid}")


def _antes_de_salvar(sender, instance, raw=False, update_fields=None, **kwargs):
    """
    Lê do BANCO (não da instância) o public_id atual de cada campo de imagem.
    A instância em memória já pode ter o valor novo — ou até um arquivo
    ainda não enviado —, então só o banco diz qual arquivo está saindo.
    """
    instance._midia_antigos = {}
    if raw or instance.pk is None or instance._state.adding:
        return

    campos = [f.name for f in campos_cloudinary(sender)]
    if update_fields is not None:
        # `save(update_fields=["sistema"])` e afins não mexem em imagem:
        # poupa a consulta extra.
        campos = [c for c in campos if c in update_fields]
    if not campos:
        return

    linha = sender._base_manager.filter(pk=instance.pk).values_list(*campos).first()
    if linha:
        instance._midia_antigos = {campo: public_id_de(valor) for campo, valor in zip(campos, linha)}


def _depois_de_salvar(sender, instance, raw=False, **kwargs):
    antigos = instance.__dict__.pop("_midia_antigos", None) or {}
    saindo = []
    for campo, antigo in antigos.items():
        novo = public_id_de(getattr(instance, campo, None))
        if antigo == novo:
            continue
        # Enquadramento é da imagem, não do campo: com outro arquivo (ou sem
        # nenhum), o ajuste antigo não faz mais sentido. Se o cliente mandou
        # um ajuste novo junto do upload, o serializer o grava logo depois.
        apagar_ajuste(instance, campo)
        if antigo:
            saindo.append((antigo, "substituida" if novo else "removida"))

    for motivo in ("substituida", "removida"):
        enfileirar_exclusao([p for p, m in saindo if m == motivo], motivo)


def _depois_de_excluir(sender, instance, **kwargs):
    # `__dict__` e não `getattr`: um campo adiado (`.only()`) dispararia uma
    # consulta a uma linha que já não existe. Na cascata com signals ligados
    # o Django carrega os objetos inteiros, então os valores estão aqui.
    public_ids = [public_id_de(instance.__dict__.get(f.attname)) for f in campos_cloudinary(sender)]
    enfileirar_exclusao(public_ids, "excluida")
    apagar_ajuste(instance)
