from django.db import migrations


# ---------------------------------------------------------------------------
# 1) Consolidação dos campos narrativos em `conteudo` (Markdown)
# ---------------------------------------------------------------------------

# Para cada model: lista de (campo_antigo, título em Markdown), na ordem em
# que devem aparecer no `conteudo` final. Campos vazios são pulados (não
# geram uma seção "## Título" vazia no meio do texto).
CAMPOS_NARRATIVOS = {
    "NPC": [
        ("aparencia", "Aparência"),
        ("personalidade", "Personalidade"),
        ("familia", "Família"),
        ("maior_desejo", "Maior Desejo"),
        ("maior_prazer", "Maior Prazer"),
        ("peculiaridade", "Peculiaridade"),
        ("ocupacao", "Ocupação"),
        ("status_social", "Status Social"),
        ("segredo", "Segredo"),
        ("anotacoes", "Anotações"),
    ],
    "Local": [
        ("descricao", "Descrição"),
        ("historia", "História"),
        ("clima", "Clima"),
        ("populacao", "População"),
        ("governo", "Governo"),
        ("tesouros", "Tesouros"),
        ("segredos", "Segredos"),
        ("peculiaridade", "Peculiaridade"),
        ("anotacoes", "Anotações"),
    ],
    "Organizacao": [
        ("descricao", "Descrição"),
        ("historia", "História"),
        ("objetivos", "Objetivos"),
        ("recursos", "Recursos"),
        ("anotacoes", "Anotações"),
    ],
    "Mapa": [
        ("descricao", "Descrição"),
        ("anotacoes", "Anotações"),
    ],
    "Sessao": [
        ("resumo", "Resumo"),
        ("eventos_importantes", "Eventos Importantes"),
        ("anotacoes", "Anotações"),
    ],
    "Missao": [
        ("descricao", "Descrição"),
        ("objetivo", "Objetivo"),
        ("recompensas", "Recompensas"),
        ("anotacoes", "Anotações"),
    ],
    "Evento": [
        ("descricao", "Descrição"),
        ("anotacoes", "Anotações"),
    ],
}


def _monta_markdown(instancia, campos):
    """
    Monta o `conteudo` em Markdown a partir dos campos antigos de uma
    instância, um `## Título` por campo não-vazio, na ordem definida em
    CAMPOS_NARRATIVOS. Não descarta nada: campos em branco são só
    ignorados (não haveria o que preservar), campos preenchidos viram uma
    seção.
    """
    secoes = []

    for campo, titulo in campos:
        valor = (getattr(instancia, campo, "") or "").strip()

        if valor:
            secoes.append(f"## {titulo}\n\n{valor}")

    return "\n\n".join(secoes)


def migrar_conteudo(apps, schema_editor):
    for nome_model, campos in CAMPOS_NARRATIVOS.items():
        Model = apps.get_model("Campanha", nome_model)

        instancias = list(Model.objects.all())

        for instancia in instancias:
            markdown = _monta_markdown(instancia, campos)

            if markdown:
                instancia.conteudo = markdown

        Model.objects.bulk_update(instancias, ["conteudo"])


def reverter_conteudo(apps, schema_editor):
    # Reversão intencionalmente no-op: os campos antigos ainda existem
    # nesta migration (só são removidos na migration seguinte), e o
    # `conteudo` sintetizado a partir deles seria só descartado — não há
    # perda de dados ao reverter.
    pass


# ---------------------------------------------------------------------------
# 2) RelacaoNPC / MembroOrganizacao -> Conexao (+ TipoConexao)
# ---------------------------------------------------------------------------

# Pares (nome, inverso) semeados para os tipos de conexão já implícitos no
# sistema antigo. `MEMBRO_DE`/`POSSUI_MEMBRO` cobre MembroOrganizacao;
# `tipo_relacao` de RelacaoNPC é texto livre, então seus tipos são
# criados sob demanda (get_or_create) em `migrar_relacoes_npc`.
MEMBRO_DE = "Membro de"
POSSUI_MEMBRO = "Possui membro"


def _content_type(apps, model):
    ContentType = apps.get_model("contenttypes", "ContentType")
    return ContentType.objects.get_for_model(model)


def migrar_membro_organizacao(apps, schema_editor):
    MembroOrganizacao = apps.get_model("Campanha", "MembroOrganizacao")
    TipoConexao = apps.get_model("Campanha", "TipoConexao")
    Conexao = apps.get_model("Campanha", "Conexao")
    Organizacao = apps.get_model("Campanha", "Organizacao")
    Personagem = apps.get_model("Personagem", "Personagem")
    NPC = apps.get_model("Campanha", "NPC")

    if not MembroOrganizacao.objects.exists():
        return

    tipo_membro_de, _ = TipoConexao.objects.get_or_create(
        nome=MEMBRO_DE,
        defaults={"descricao": "Migrado automaticamente de MembroOrganizacao."},
    )
    tipo_possui_membro, _ = TipoConexao.objects.get_or_create(
        nome=POSSUI_MEMBRO,
        defaults={"descricao": "Migrado automaticamente de MembroOrganizacao."},
    )

    if tipo_membro_de.inverso_id is None:
        tipo_membro_de.inverso = tipo_possui_membro
        tipo_membro_de.save(update_fields=["inverso"])

    if tipo_possui_membro.inverso_id is None:
        tipo_possui_membro.inverso = tipo_membro_de
        tipo_possui_membro.save(update_fields=["inverso"])

    ct_organizacao = _content_type(apps, Organizacao)
    ct_personagem = _content_type(apps, Personagem)
    ct_npc = _content_type(apps, NPC)

    for membro in MembroOrganizacao.objects.select_related("organizacao").all():

        if membro.personagem_id:
            ct_membro, id_membro = ct_personagem, membro.personagem_id
        elif membro.npc_id:
            ct_membro, id_membro = ct_npc, membro.npc_id
        else:
            # Registro inconsistente (nem personagem nem npc) — não deveria
            # existir dada a CheckConstraint original, mas não descartamos
            # silenciosamente: pulamos e deixamos o registro antigo intacto
            # para inspeção manual (a migration seguinte só remove o model
            # depois que TODOS os registros válidos já migraram).
            continue

        descricao = f"## Cargo\n\n{membro.cargo}" if membro.cargo else ""

        Conexao.objects.get_or_create(
            entidade1_tipo=ct_membro,
            entidade1_id=id_membro,
            entidade2_tipo=ct_organizacao,
            entidade2_id=membro.organizacao_id,
            tipo=tipo_membro_de,
            defaults={
                "campanha_id": membro.organizacao.campanha_id,
                "descricao": descricao,
            },
        )


def migrar_relacao_npc(apps, schema_editor):
    RelacaoNPC = apps.get_model("Campanha", "RelacaoNPC")
    TipoConexao = apps.get_model("Campanha", "TipoConexao")
    Conexao = apps.get_model("Campanha", "Conexao")
    NPC = apps.get_model("Campanha", "NPC")
    Personagem = apps.get_model("Personagem", "Personagem")

    if not RelacaoNPC.objects.exists():
        return

    ct_npc = _content_type(apps, NPC)
    ct_personagem = _content_type(apps, Personagem)

    for relacao in RelacaoNPC.objects.select_related("npc").all():

        if relacao.personagem_id:
            ct_origem, id_origem = ct_personagem, relacao.personagem_id
        elif relacao.outro_npc_id:
            ct_origem, id_origem = ct_npc, relacao.outro_npc_id
        else:
            # Mesmo caso de inconsistência descrito em
            # migrar_membro_organizacao: preservado para inspeção manual.
            continue

        nome_tipo = (relacao.tipo_relacao or "Relacionado a").strip() or "Relacionado a"

        tipo, _ = TipoConexao.objects.get_or_create(
            nome=nome_tipo,
            defaults={"descricao": "Migrado automaticamente de RelacaoNPC."},
        )

        Conexao.objects.get_or_create(
            entidade1_tipo=ct_origem,
            entidade1_id=id_origem,
            entidade2_tipo=ct_npc,
            entidade2_id=relacao.npc_id,
            tipo=tipo,
            defaults={
                "campanha_id": relacao.npc.campanha_id,
                "descricao": relacao.descricao or "",
            },
        )


def migrar_relacoes(apps, schema_editor):
    migrar_membro_organizacao(apps, schema_editor)
    migrar_relacao_npc(apps, schema_editor)


def reverter_relacoes(apps, schema_editor):
    # No-op: RelacaoNPC/MembroOrganizacao ainda existem intactos nesta
    # migration (só são removidos na seguinte); reverter só precisaria
    # desfazer a CRIAÇÃO das Conexao correspondentes, o que não é
    # necessário para não perder dados (os originais continuam lá).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("Campanha", "0007_adiciona_pasta_conexao_conteudo"),
    ]

    operations = [
        migrations.RunPython(migrar_conteudo, reverter_conteudo),
        migrations.RunPython(migrar_relacoes, reverter_relacoes),
    ]
