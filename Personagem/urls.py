#PERSONAGEM
from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    #PERSONAGEM
    path("", views.personagens, name="personagens"),
    path("<int:pk>/", views.personagem, name="personagem"),
    
    #STATUS
    path("<int:personagem_id>/status/", views.status_lista, name="status_lista"),
    path("status/<int:pk>/", views.status_detalhe, name="status_detalhe"),
    
    #ATRIBUTOS
    path("<int:personagem_id>/atributos/", views.atributo_lista, name="atributo_lista"),
    path("atributo/<int:pk>/", views.atributo_detalhe, name="atributo_detalhe"),
    
    #DEFESAS
    path("<int:personagem_id>/defesas/", views.defesa_lista, name="defesa_lista"),
    path("defesa/<int:pk>/", views.defesa_detalhe, name="defesa_detalhe"),
    
    #PERÍCIAS
    path("<int:personagem_id>/pericias/", views.pericia_lista, name="pericia_lista"),
    path("pericias/<int:pk>/", views.pericia_detalhe, name="pericia_detalhe"),
    
    #ITEM
    path("<int:personagem_id>/itens/", views.item_lista, name="item_lista"),
    path("itens/<int:pk>/", views.item_detalhe, name="item_detalhe"),

    #ARMA
    path("<int:personagem_id>/arma/", views.arma_lista, name="arma_lista"),
    path("armas/<int:pk>/", views.arma_detalhe, name="arma_detalhe"),

    #ARMADURA
    path("<int:personagem_id>/armadura/", views.armadura_lista, name="armadura_lista"),
    path("armaduras/<int:pk>/", views.armadura_detalhe, name="armadura_detalhe"),
    
    # TÉCNICAS
    path("<int:personagem_id>/tecnicas/", views.tecnica_lista, name="tecnica_lista"),
    path("tecnicas/<int:pk>/", views.tecnica_detalhe, name="tecnica_detalhe"),

    # PODERES
    path("<int:personagem_id>/poderes/", views.poder_lista, name="poder_lista"),
    path("poderes/<int:pk>/", views.poder_detalhe, name="poder_detalhe"),

    # HABILIDADES
    path("<int:personagem_id>/habilidades/", views.habilidade_lista, name="habilidade_lista"),
    path("habilidades/<int:pk>/", views.habilidade_detalhe, name="habilidade_detalhe"),

    # APRIMORAMENTOS
    path("habilidades/<int:habilidade_id>/aprimoramentos/", views.aprimoramento_lista, name="aprimoramento_lista"),
    path("aprimoramentos/<int:pk>/", views.aprimoramento_detalhe, name="aprimoramento_detalhe"),
    
    #BONUS
    path("<str:tipo>/<int:object_id>/bonus/", views.bonus_lista, name="bonus_lista"),
    path("bonus/<int:pk>/", views.bonus_detalhe, name="bonus_detalhe"),
]