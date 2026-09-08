from django.db import migrations


def copiar_sistema_para_sistemas(apps, schema_editor):
    """
    Mesmo passo feito em Campanha/0013: fichas antigas só têm a FK
    `sistema`; sem copiá-la para o M2M novo elas perderiam o acesso à
    biblioteca já configurada (Inventário, Combate, "Adicionar da
    Biblioteca") assim que a interface passar a ler `sistemas`.
    """
    Personagem = apps.get_model("Personagem", "Personagem")

    for personagem in Personagem.objects.exclude(sistema__isnull=True).iterator():
        personagem.sistemas.add(personagem.sistema_id)


def reverter(apps, schema_editor):
    Personagem = apps.get_model("Personagem", "Personagem")

    for personagem in Personagem.objects.iterator():
        personagem.sistemas.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("Personagem", "0019_personagem_sistemas"),
    ]

    operations = [
        migrations.RunPython(copiar_sistema_para_sistemas, reverter),
    ]
