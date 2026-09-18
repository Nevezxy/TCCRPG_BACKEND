from django.db import migrations


# Mesmo padrão da migration 0008 (consolidação em `conteudo`): move o valor
# dos dois TextFields antigos para dentro do Markdown de `conteudo`, um
# "# Título" por campo não-vazio, ANTES de removê-los do model — nenhuma
# raça já preenchida perde texto na atualização.
CAMPOS_ANTIGOS = [
    ("tendencias", "Tendências"),
    ("tracos_raciais", "Traços Raciais"),
]


def migrar_conteudo(apps, schema_editor):
    Raca = apps.get_model("Campanha", "Raca")

    instancias = list(Raca.objects.all())

    for instancia in instancias:
        secoes = []

        for campo, titulo in CAMPOS_ANTIGOS:
            valor = (getattr(instancia, campo, "") or "").strip()

            if valor:
                secoes.append(f"# {titulo}\n\n{valor}")

        if not secoes:
            continue

        adicional = "\n\n".join(secoes)
        instancia.conteudo = f"{instancia.conteudo}\n\n{adicional}" if instancia.conteudo else adicional

    if instancias:
        Raca.objects.bulk_update(instancias, ["conteudo"])


def reverter_conteudo(apps, schema_editor):
    # No-op — mesmo racional da reversão de 0008: os campos antigos ainda
    # existem nesta migration (só somem no RemoveField logo abaixo), e o
    # texto já copiado para `conteudo` não é retirado de lá ao reverter.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("Campanha", "0025_npc_ocupacao_status_social"),
    ]

    operations = [
        migrations.RunPython(migrar_conteudo, reverter_conteudo),
        migrations.RemoveField(
            model_name="raca",
            name="tendencias",
        ),
        migrations.RemoveField(
            model_name="raca",
            name="tracos_raciais",
        ),
    ]
