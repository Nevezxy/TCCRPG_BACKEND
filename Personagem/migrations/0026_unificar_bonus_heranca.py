"""
Duas correções de dados que a coluna `valor_final` (0025) tornou necessárias.

1) UM BALDE DE BÔNUS POR LINHA FÍSICA

`Arma` e `Armadura` são subclasses de `Item`, e `Habilidade` de `Poder`
(herança multi-tabela): é a MESMA linha, com o mesmo id, aparecendo em rotas
diferentes — uma arma é listada tanto em `/itens/` quanto em `/arma/` (ver
`src/api/recursosIrmaos.ts` no frontend). Como `ContentType` trata cada
subclasse como um model distinto, um bônus criado pela aba Inventário ia para
`content_type=item` e um criado pela aba Combate para `content_type=arma`:
dois conjuntos separados, invisíveis um para o outro, na mesma arma.

Isso já era um bug silencioso (o painel de bônus mostrava conjuntos diferentes
conforme a aba). Com `valor_final` viraria um bug visível: a mesma linha teria
dois totais. A partir daqui todo bônus é gravado sob o model BASE
(`Personagem/calculos.py::tipo_base`), e esta migration converte o que já
existe. Nenhum bônus é perdido: só muda o `content_type` da linha.

2) `Armadura.valor_final` = `Armadura.defesa`

`Armadura.save()` passa a espelhar `defesa` na coluna `valor_final` herdada de
`Item`, para que a mesma armadura dê o mesmo número quando vista como Item e
quando vista como Armadura. As armaduras que já existem nunca passaram por
esse `save()`, então o espelho é feito aqui.
"""

from django.db import migrations


# (subclasse, model base) — as duas cadeias de herança multi-tabela da ficha.
COLAPSOS = [("arma", "item"), ("armadura", "item"), ("habilidade", "poder")]


def _content_types(apps):
    ContentType = apps.get_model("contenttypes", "ContentType")
    return {
        nome: ContentType.objects.filter(app_label="Personagem", model=nome).first()
        for nome in {"arma", "armadura", "habilidade", "item", "poder"}
    }


def unificar(apps, schema_editor):
    Bonus = apps.get_model("Personagem", "Bonus")
    cts = _content_types(apps)

    for subclasse, base in COLAPSOS:
        ct_sub, ct_base = cts.get(subclasse), cts.get(base)
        # Um banco que nunca chegou a criar esses ContentTypes (instalação
        # nova, migrando do zero) não tem nada para converter.
        if ct_sub is None or ct_base is None:
            continue
        Bonus.objects.filter(content_type=ct_sub).update(content_type=ct_base)

    Armadura = apps.get_model("Personagem", "Armadura")
    for armadura in Armadura.objects.all().iterator():
        if armadura.valor_final != armadura.defesa:
            armadura.valor_final = armadura.defesa
            armadura.save(update_fields=["valor_final"])


def reverter(apps, schema_editor):
    """
    A conversão não é reversível campo a campo: depois de unificados não há
    como saber por qual aba cada bônus tinha sido criado. Voltar deixa tudo no
    model base, que é exatamente o que o código anterior a 0025 lia para
    Itens — nenhum bônus some, alguns deixam de aparecer na aba Combate.
    O espelho de `valor_final` é inofensivo e fica.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("Personagem", "0025_aprimoramento_valor_final_bonus_expira_em_and_more"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(unificar, reverter)]
