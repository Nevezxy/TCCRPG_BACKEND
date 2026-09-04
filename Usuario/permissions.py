from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q


def _get_campanha(obj):
    """
    Descobre a Campanha à qual o objeto pertence, mesmo quando o vínculo é
    indireto (ex.: um recurso cujo model tem `npc`/`organizacao` em vez de
    `campanha` diretamente).

    Retorna None se o objeto não tiver nenhuma relação (direta ou indireta)
    com uma Campanha (ex.: o próprio Personagem, ou recursos filhos dele).
    """
    if hasattr(obj, "campanha"):
        return obj.campanha

    for attr in ("npc", "organizacao"):
        relacionado = getattr(obj, attr, None)
        if relacionado is not None and hasattr(relacionado, "campanha"):
            return relacionado.campanha

    return None


def _pode_acessar_personagem(personagem, user, is_safe):
    """
    Regra única de acesso a um Personagem que NÃO é do usuário logado —
    usada tanto para o próprio Personagem quanto para qualquer recurso
    filho dele (Status, Atributo, Defesa, Item, Arma, Armadura, Técnica,
    Poder, Habilidade, Bônus...). Ponto único de manutenção: mudar a regra
    aqui já vale para toda a ficha, em qualquer endpoint.

      - Mestre de QUALQUER campanha à qual este personagem esteja
        vinculado: leitura E edição plena (é o que permite ao mestre gerir
        a ficha de qualquer jogador da própria mesa).
      - Jogador (não mestre) de uma campanha em comum: só leitura — é o
        que já alimentava o Escudo do Mestre/visão entre jogadores.

    Não decide sozinho sobre EXCLUIR o próprio Personagem (a ficha
    inteira) — isso é tratado à parte por quem chama esta função, porque
    apagar a ficha toda de outra pessoa continua exclusivo do dono, mesmo
    para o mestre.
    """
    if not hasattr(personagem, "campanhas"):
        return False

    if personagem.campanhas.filter(mestre=user).exists():
        return True

    if is_safe:
        return personagem.campanhas.filter(jogadores=user).exists()

    return False


def usuario_pode_ver_objeto(user, obj):
    """
    Mesma regra de visibilidade usada no ramo "leitura" de
    `IsOwnerOrAdmin.has_object_permission` (mestre sempre vê; jogador só se
    `visivel_para_jogadores`), mas independente do método HTTP da
    requisição atual — usado para checar se alguém pode CRIAR uma nota
    sobre um objeto, uma ação que exige poder VER o objeto (não poder
    editá-lo). `has_object_permission` reaproveita esta função para seu
    próprio ramo de leitura, evitando duas implementações divergentes.
    """
    if user.is_superuser:
        return True

    if hasattr(obj, "mestre") and hasattr(obj, "jogadores"):
        return obj.mestre == user or obj.jogadores.filter(pk=user.pk).exists()

    campanha = _get_campanha(obj)

    if campanha is not None:
        if campanha.mestre == user:
            return True
        if not campanha.jogadores.filter(pk=user.pk).exists():
            return False
        return getattr(obj, "visivel_para_jogadores", True)

    if hasattr(obj, "usuario"):
        if obj.usuario == user:
            return True
        if hasattr(obj, "campanhas"):
            return obj.campanhas.filter(Q(mestre=user) | Q(jogadores=user)).exists()
        return False

    if hasattr(obj, "personagem"):
        if obj.personagem.usuario == user:
            return True
        if hasattr(obj.personagem, "campanhas"):
            return obj.personagem.campanhas.filter(Q(mestre=user) | Q(jogadores=user)).exists()
        return False

    return False


class IsOwnerOrAdmin(BasePermission):

    message = "Você não tem permissão para acessar este recurso."

    def has_object_permission(self, request, view, obj):

        if request.user.is_superuser:
            return True

        is_safe = request.method in ("GET", "HEAD", "OPTIONS")

        # --- O próprio objeto é uma Campanha ---
        if hasattr(obj, "mestre") and hasattr(obj, "jogadores"):

            if obj.mestre == request.user:
                return True

            if is_safe:
                return usuario_pode_ver_objeto(request.user, obj)

            return False

        # --- Objetos "de mundo" pertencentes a uma Campanha: NPC, Local,
        # Organizacao, Mapa, Sessao, Missao, Evento, Pasta, Conexao, etc.
        # Regra:
        #   - mestre: acesso total (ler, criar, editar, excluir)
        #   - jogador: leitura só se visivel_para_jogadores=True;
        #     escrita (PUT/PATCH) só se, além de visível, também for
        #     editavel_para_jogadores=True; DELETE nunca (só o mestre).
        campanha = _get_campanha(obj)

        if campanha is not None:

            if campanha.mestre == request.user:
                return True

            e_jogador = campanha.jogadores.filter(pk=request.user.pk).exists()

            if not e_jogador:
                return False

            # Objetos sem os campos de visibilidade (ex.: Pasta, Conexao,
            # que não têm noção de "rascunho do mestre") são tratados
            # como visíveis por padrão, mas não editáveis por jogadores.
            visivel = getattr(obj, "visivel_para_jogadores", True)
            editavel = getattr(obj, "editavel_para_jogadores", False)

            if is_safe:
                return visivel

            if request.method in ("PUT", "PATCH"):
                return visivel and editavel

            # POST/DELETE em objetos já existentes: só o mestre
            return False

        # --- Personagem ---
        if hasattr(obj, "usuario"):

            if obj.usuario == request.user:
                return True

            # Leitura: qualquer participante de uma campanha vinculada a
            # este personagem (mestre OU jogador) pode CONSULTAR — é o que
            # permite o "Escudo do Mestre" mostrar Status/Atributos/
            # Defesas de personagens de outros jogadores para todo mundo
            # na mesa, não só para quem mestra.
            #
            # Escrita (PUT/PATCH): só o MESTRE de uma campanha vinculada
            # pode editar a ficha de outro jogador — é o que permite ao
            # mestre gerenciar (ex.: ajustar Status/Itens durante a
            # sessão) a ficha de qualquer personagem de sua mesa.
            #
            # Excluir a ficha INTEIRA de outra pessoa continua exclusivo
            # do dono, mesmo para o mestre — por isso DELETE nunca passa
            # por aqui, mesmo quando `_pode_acessar_personagem` retorna
            # True (ela só sabe dizer "pode ver/editar", não "pode
            # apagar").
            if hasattr(obj, "campanhas") and _pode_acessar_personagem(obj, request.user, is_safe):
                return request.method != "DELETE"

            return False

        # --- Recursos "filhos" do personagem (Status, Atributo, Defesa,
        # Item, Arma, Armadura, Técnica, Poder, Habilidade, Bonus, etc.) ---
        if hasattr(obj, "personagem"):

            if obj.personagem.usuario == request.user:
                return True

            # Aqui não existe "excluir o personagem inteiro" — excluir um
            # Item/Status/Bônus é uma operação normal de EDITAR a ficha,
            # então o mestre tem CRUD completo (GET/POST/PUT/PATCH/DELETE)
            # nesses sub-recursos, igual ao dono. Jogador (não mestre)
            # continua só com leitura, via `is_safe` dentro do helper.
            if hasattr(obj.personagem, "campanhas"):
                return _pode_acessar_personagem(obj.personagem, request.user, is_safe)

            return False

        return False


def pode_criar_ou_excluir(request, campanha):
    """
    Helper para uso nas views de listagem (POST) e nas views de detalhe
    (DELETE) de recursos "de mundo" (NPC, Local, Organizacao, etc.), onde
    ainda não existe uma instância do objeto para checar
    has_object_permission. Regra: só mestre (ou superuser) pode criar ou
    excluir esses recursos.

    Também reaproveitado por `Campanha/views.py` para decidir se quem está
    removendo um personagem/jogador da campanha é o mestre (com poder de
    remover qualquer um) ou um jogador comum (só a si mesmo).
    """
    if request.user.is_superuser:
        return True

    return campanha.mestre == request.user


def check_object_permission(request, obj):
    permission = IsOwnerOrAdmin()

    if not permission.has_object_permission(request, None, obj):
        raise PermissionDenied(permission.message)