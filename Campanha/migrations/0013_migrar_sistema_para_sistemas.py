from django.db import migrations


def copiar_sistema_para_sistemas(apps, schema_editor):
    """
    Campanhas criadas antes do M2M `sistemas` só têm a FK `sistema`. Sem
    este passo elas apareceriam com "nenhuma biblioteca de regras" na
    interface nova, mesmo tendo um sistema definido — os dados existentes
    precisam continuar valendo (seção 10 da tarefa).
    """
    Campanha = apps.get_model("Campanha", "Campanha")

    for campanha in Campanha.objects.exclude(sistema__isnull=True).iterator():
        campanha.sistemas.add(campanha.sistema_id)


def reverter(apps, schema_editor):
    """
    A volta é segura porque `sistema` (a FK) nunca foi tocada: basta esvaziar
    o M2M, que é a coluna nova.
    """
    Campanha = apps.get_model("Campanha", "Campanha")

    for campanha in Campanha.objects.iterator():
        campanha.sistemas.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("Campanha", "0012_campanha_sistemas_canva_criatura_divindade_documento_and_more"),
    ]

    operations = [
        migrations.RunPython(copiar_sistema_para_sistemas, reverter),
    ]
