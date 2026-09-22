from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Campanha", "0027_podercampanha_habilidadecampanha_tecnicacampanha_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="participantecombate",
            name="nome_avulso",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="participantecombate",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("personagem", "Personagem"),
                    ("npc", "NPC"),
                    ("criatura", "Criatura"),
                    ("avulso", "Avulso"),
                ],
                max_length=20,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="participantecombate",
            name="participante_combate_uma_entidade",
        ),
        migrations.AddConstraint(
            model_name="participantecombate",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("criatura__isnull", True),
                        ("npc__isnull", True),
                        ("personagem__isnull", False),
                        ("tipo", "personagem"),
                    ),
                    models.Q(
                        ("criatura__isnull", True),
                        ("npc__isnull", False),
                        ("personagem__isnull", True),
                        ("tipo", "npc"),
                    ),
                    models.Q(
                        ("criatura__isnull", False),
                        ("npc__isnull", True),
                        ("personagem__isnull", True),
                        ("tipo", "criatura"),
                    ),
                    models.Q(
                        ("criatura__isnull", True),
                        ("nome_avulso__isnull", False),
                        ("npc__isnull", True),
                        ("personagem__isnull", True),
                        ("tipo", "avulso"),
                    ),
                    _connector="OR",
                ),
                name="participante_combate_uma_entidade",
            ),
        ),
    ]
