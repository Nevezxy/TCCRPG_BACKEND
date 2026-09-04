from django.urls import path

from . import views


urlpatterns = [

    # CRUD campanhas
    path(
        "",
        views.campanhas,
        name="campanhas"
    ),

    path(
        "<int:pk>/",
        views.campanha,
        name="campanha"
    ),


    # Entrar
    path(
        "entrar/",
        views.entrar_campanha,
        name="entrar_campanha"
    ),


    # Sair
    path(
        "<int:pk>/sair/",
        views.sair_campanha,
        name="sair_campanha"
    ),


    # Personagens
    path(
        "<int:pk>/personagens/",
        views.adicionar_personagens,
        name="adicionar_personagens"
    ),

    path(
        "<int:pk>/personagens-disponiveis/",
        views.personagens_disponiveis,
        name="personagens_disponiveis"
    ),

    path(
        "<int:pk>/personagens/<int:personagem_pk>/",
        views.remover_personagem,
        name="remover_personagem"
    ),


    # Jogadores — NOVO: só o mestre pode expulsar alguém da campanha; a
    # autorremoção (o próprio jogador saindo) continua sendo
    # `sair_campanha` (POST /campanha/<pk>/sair/), sem mudanças.
    path(
        "<int:pk>/jogadores/<int:usuario_pk>/",
        views.remover_jogador,
        name="remover_jogador"
    ),


    # NPCs — lista aninhada em Campanha, detalhe "achatado" (só o id do
    # NPC), no mesmo padrão usado pelos recursos filhos de Personagem
    # (ver createChildResource no frontend). A campanha do NPC é sempre
    # derivada de npc.campanha nas views/permissions, então repetir o pk
    # da campanha na URL de detalhe seria redundante.
    path(
        "<int:pk>/npcs/",
        views.npc_lista,
        name="npc_lista"
    ),

    path(
        "npcs/<int:npc_pk>/",
        views.npc_detalhe,
        name="npc_detalhe"
    ),

    # Relações de NPC — substituídas pelo modelo genérico Conexao (ver
    # seções 6-10 da refatoração). `npc_conexoes` lista as conexões deste
    # NPC especificamente; CRUD completo de conexões fica nos endpoints
    # genéricos `conexao_lista`/`conexao_detalhe` mais abaixo.
    path(
        "npcs/<int:npc_pk>/conexoes/",
        views.npc_conexoes,
        name="npc_conexoes"
    ),


    # Locais
    path(
        "<int:pk>/locais/",
        views.local_lista,
        name="local_lista"
    ),

    path(
        "locais/<int:local_pk>/",
        views.local_detalhe,
        name="local_detalhe"
    ),

    path(
        "locais/<int:local_pk>/conexoes/",
        views.local_conexoes,
        name="local_conexoes"
    ),


    # Organizações
    path(
        "<int:pk>/organizacoes/",
        views.organizacao_lista,
        name="organizacao_lista"
    ),

    path(
        "organizacoes/<int:organizacao_pk>/",
        views.organizacao_detalhe,
        name="organizacao_detalhe"
    ),

    # Membros de organização — substituído pelo modelo genérico Conexao
    # (tipo "Membro de"/"Possui membro"; ver seções 6-10 da refatoração).
    path(
        "organizacoes/<int:organizacao_pk>/conexoes/",
        views.organizacao_conexoes,
        name="organizacao_conexoes"
    ),


    # Mapas
    path(
        "<int:pk>/mapas/",
        views.mapa_lista,
        name="mapa_lista"
    ),

    path(
        "mapas/<int:mapa_pk>/",
        views.mapa_detalhe,
        name="mapa_detalhe"
    ),

    path(
        "mapas/<int:mapa_pk>/conexoes/",
        views.mapa_conexoes,
        name="mapa_conexoes"
    ),


    # Sessões
    path(
        "<int:pk>/sessoes/",
        views.sessao_lista,
        name="sessao_lista"
    ),

    path(
        "sessoes/<int:sessao_pk>/",
        views.sessao_detalhe,
        name="sessao_detalhe"
    ),

    path(
        "sessoes/<int:sessao_pk>/conexoes/",
        views.sessao_conexoes,
        name="sessao_conexoes"
    ),


    # Missões
    path(
        "<int:pk>/missoes/",
        views.missao_lista,
        name="missao_lista"
    ),

    path(
        "missoes/<int:missao_pk>/",
        views.missao_detalhe,
        name="missao_detalhe"
    ),

    path(
        "missoes/<int:missao_pk>/conexoes/",
        views.missao_conexoes,
        name="missao_conexoes"
    ),


    # Eventos
    path(
        "<int:pk>/eventos/",
        views.evento_lista,
        name="evento_lista"
    ),

    path(
        "eventos/<int:evento_pk>/",
        views.evento_detalhe,
        name="evento_detalhe"
    ),

    path(
        "eventos/<int:evento_pk>/conexoes/",
        views.evento_conexoes,
        name="evento_conexoes"
    ),


    # Pastas — árvore de organização estilo Obsidian (seção 3)
    path(
        "<int:pk>/pastas/",
        views.pasta_lista,
        name="pasta_lista"
    ),

    path(
        "pastas/<int:pasta_pk>/",
        views.pasta_detalhe,
        name="pasta_detalhe"
    ),

    path(
        "pastas/<int:pasta_pk>/mover/",
        views.pasta_mover,
        name="pasta_mover"
    ),


    # Tipos de conexão — vocabulário compartilhado (não aninhado em
    # campanha; ver TipoConexao em models.py)
    path(
        "tipos-conexao/",
        views.tipo_conexao_lista,
        name="tipo_conexao_lista"
    ),

    path(
        "tipos-conexao/<int:tipo_pk>/",
        views.tipo_conexao_detalhe,
        name="tipo_conexao_detalhe"
    ),


    # Conexões — relacionamento genérico entre entidades de uma campanha
    # (seções 6-10; substitui RelacaoNPC e MembroOrganizacao)
    path(
        "<int:pk>/conexoes/",
        views.conexao_lista,
        name="conexao_lista"
    ),

    path(
        "conexoes/<int:conexao_pk>/",
        views.conexao_detalhe,
        name="conexao_detalhe"
    ),


    # Notas (não aninhadas em campanha — o vínculo é via
    # content_type/object_id, ver NotaSerializer). Aceita filtros opcionais
    # via querystring: ?content_type=npc&object_id=5 (notas de um objeto
    # específico) ou ?campanha=3 (todas as notas do usuário sobre qualquer
    # objeto desta campanha) — ver nota_lista.
    path(
        "notas/",
        views.nota_lista,
        name="nota_lista"
    ),

    path(
        "notas/<int:pk>/",
        views.nota_detalhe,
        name="nota_detalhe"
    ),
]