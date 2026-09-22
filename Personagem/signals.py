"""
Limpeza das referências de bônus quando a entidade de ORIGEM é excluída.

`Bonus.origem` é uma GenericForeignKey e, ao contrário de uma FK comum, ela
NÃO tem `on_delete`: apagar o Atributo "Força" deixaria cada bônus que o usa
como origem apontando para um id que não existe mais. O cálculo já trata
origem sumida como 0 (`calculos.ContextoCalculo.valor_bonus`), então nada
quebra — mas o bônus ficaria para sempre valendo 0 sem o jogador entender
por quê, e a linha órfã ainda apareceria na detecção de ciclos.

O que fazemos aqui é reproduzir o mesmo comportamento que `Defesa.atributo`
já tem com `on_delete=SET_NULL`: a referência é desfeita e o bônus volta a
ser MANUAL, com o último valor efetivo congelado em `valor`. Assim o jogador
vê o número que tinha, sabe que virou manual, e decide se reaponta para
outra entidade ou apaga. Apagar o bônus junto seria mais limpo de código e
pior de usar — some da ficha um modificador que a pessoa não mandou tirar.

`post_delete` (e não `pre_delete`) porque só depois da exclusão temos certeza
de que ela ocorreu; o valor congelado é calculado ANTES, no `pre_delete`,
enquanto a origem ainda existe para ser somada.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from . import calculos
from .models import Bonus

# Só os models BASE: uma `Arma` excluída dispara o sinal de `Item` também
# (herança multi-tabela), e as referências são sempre gravadas sob a base.
_MODELOS_ORIGEM = [calculos.MODELOS_ALVO[tipo] for tipo in calculos.TIPOS_BASE]


def _bonus_que_usam(instance):
    content_type = ContentType.objects.get_for_model(
        calculos.modelo_base(instance._meta.model_name)
    )
    return Bonus.objects.filter(
        origem_content_type=content_type,
        origem_object_id=instance.pk,
        tipo_origem=Bonus.TIPO_ENTIDADE,
    )


@receiver(pre_delete)
def _congelar_valor_da_origem(sender, instance, **kwargs):
    """Guarda na instância o valor que a origem tinha, para o `post_delete`."""
    if sender not in _MODELOS_ORIGEM:
        return

    dependentes = list(_bonus_que_usam(instance))
    if not dependentes:
        return

    contexto = calculos.ContextoCalculo()
    instance._bonus_dependentes = [(b.pk, contexto.valor_final(instance)) for b in dependentes]


@receiver(post_delete)
def _origem_removida(sender, instance, **kwargs):
    if sender not in _MODELOS_ORIGEM:
        return

    congelados = getattr(instance, "_bonus_dependentes", None)
    if not congelados:
        return

    for bonus_id, valor in congelados:
        # `.filter().update()` em vez de carregar e salvar: a exclusão pode
        # estar em cascata (o personagem inteiro sendo apagado) e o bônus
        # talvez já tenha ido embora junto — um UPDATE que não casa com nada
        # é um no-op, enquanto um `.get()` levantaria DoesNotExist.
        Bonus.objects.filter(pk=bonus_id).update(
            tipo_origem=Bonus.TIPO_MANUAL,
            origem_content_type=None,
            origem_object_id=None,
            valor=valor,
        )
