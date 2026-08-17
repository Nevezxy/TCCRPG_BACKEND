from django.urls import path
from Sistema import views


urlpatterns = [
    path(
        "",
        views.sistema_lista,
        name="sistema_lista"
    ),

    # Regras — a view `regra_sistema_lista` já existia, mas não tinha rota
    # registrada (usada pela aba "Regras" da Campanha).
    path(
        "<int:sistema_id>/regras/",
        views.regra_sistema_lista,
        name="regra_sistema_lista"
    ),

    path(
        "<int:sistema_id>/poderes/",
        views.poder_sistema_lista,
        name="poder_sistema_lista"
    ),
    path(
        "personagens/<int:personagem_id>/poderes/<int:pk>/copiar/",
        views.copiar_poder_sistema,
        name="copiar_poder_sistema",
    ),

    path(
        "<int:sistema_id>/itens/",
        views.item_sistema_lista,
        name="item_sistema_lista"
    ),

    path(
        "personagens/<int:personagem_id>/itens/<int:item_id>/copiar/",
        views.copiar_item_sistema,
        name="copiar_item_sistema",
    ),

    path(
        "<int:sistema_id>/armas/",
        views.arma_sistema_lista,
        name="arma_sistema_lista"
    ),

    path(
        "personagens/<int:personagem_id>/armas/<int:arma_id>/copiar/",
        views.copiar_arma_sistema,
        name="copiar_arma_sistema"
    ),

    path(
        "<int:sistema_id>/armaduras/",
        views.armadura_sistema_lista,
        name="armadura_sistema_lista"
    ),

    path(
        "personagens/<int:personagem_id>/armaduras/<int:armadura_id>/copiar/",
        views.copiar_armadura_sistema,
        name="copiar_armadura_sistema"
    ),

    path(
        "<int:sistema_id>/habilidades/",
        views.habilidade_sistema_lista,
        name="habilidade_sistema_lista"
    ),

    path(
        "personagens/<int:personagem_id>/habilidades/<int:habilidade_id>/copiar/",
        views.copiar_habilidade_sistema,
        name="copiar_habilidade_sistema"
    ),

    # Modificações e Grupos de Armas — não são filtrados por sistema (as
    # views `modificacao_lista`/`grupo_arma_lista` retornam TODOS os
    # registros, de qualquer sistema); usados no formulário de Arma/Armadura
    # para popular os seletores de "Modificações"/"Grupo de Arma". As views
    # já existiam, só faltava registrar a rota.
    path(
        "modificacoes/",
        views.modificacao_lista,
        name="modificacao_lista"
    ),

    path(
        "grupos-armas/",
        views.grupo_arma_lista,
        name="grupo_arma_lista"
    ),

]