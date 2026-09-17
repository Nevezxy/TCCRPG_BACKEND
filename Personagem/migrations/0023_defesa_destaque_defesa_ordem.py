from django.db import migrations, models


def marcar_destaque_das_defesas_existentes(apps, schema_editor):
    """
    Antes deste campo, "Classe de Armadura" e "DT"/"Dificuldade do Teste"
    ganhavam destaque na ficha por um match de NOME fixo no frontend (ver
    `highlightItemNames` em `CombateTab.tsx`, removido junto com esta
    migração). Sem este backfill, toda defesa já cadastrada nasceria com
    `destaque=False` e sumiria do destaque na primeira renderização depois
    do deploy — mesmo sem o jogador ter mudado nada.
    """
    Defesa = apps.get_model("Personagem", "Defesa")
    nomes_destacados = {"classe de armadura", "dt", "dificuldade do teste"}

    for defesa in Defesa.objects.iterator():
        if defesa.nome.strip().lower() in nomes_destacados:
            defesa.destaque = True
            defesa.save(update_fields=["destaque"])


def reverter(apps, schema_editor):
    Defesa = apps.get_model("Personagem", "Defesa")
    Defesa.objects.update(destaque=False)


class Migration(migrations.Migration):

    dependencies = [
        ("Personagem", "0022_comercio_livre"),
    ]

    operations = [
        migrations.AddField(
            model_name="defesa",
            name="destaque",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="defesa",
            name="ordem",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(marcar_destaque_das_defesas_existentes, reverter),
    ]
