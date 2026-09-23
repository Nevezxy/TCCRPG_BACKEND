from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
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


def pode_gerenciar_campanha(campanha, user):
    """
    Regra central de "tem poder de mestre nesta campanha": o dono
    (`mestre`) ou um jogador promovido a Moderador (`moderadores`).

    Moderador tem TODAS as permissões do mestre sobre a campanha, com
    exatamente duas exceções — que NÃO passam por aqui, e continuam
    checando `campanha.mestre == user` diretamente onde importa:
      - excluir a própria campanha (`campanha` view, branch DELETE);
      - remover (expulsar) um jogador (`remover_jogador`).
    """
    if user.is_superuser:
        return True

    if campanha.mestre_id == user.id:
        return True

    return campanha.moderadores.filter(pk=user.id).exists()


def _pode_acessar_personagem(personagem, user, is_safe):
    """
    Regra única de acesso a um Personagem que NÃO é do usuário logado —
    usada tanto para o próprio Personagem quanto para qualquer recurso
    filho dele (Status, Atributo, Defesa, Item, Arma, Armadura, Técnica,
    Poder, Habilidade, Bônus...). Ponto único de manutenção: mudar a regra
    aqui já vale para toda a ficha, em qualquer endpoint.

      - Mestre OU Moderador de QUALQUER campanha à qual este personagem
        esteja vinculado: leitura E edição plena (é o que permite gerir a
        ficha de qualquer jogador da própria mesa).
      - Jogador comum de uma campanha em comum: só leitura — é o que já
        alimentava o Escudo do Mestre/visão entre jogadores.

    Não decide sozinho sobre EXCLUIR o próprio Personagem (a ficha
    inteira) — isso é tratado à parte por quem chama esta função, porque
    apagar a ficha toda de outra pessoa continua exclusivo do dono, mesmo
    para o mestre/moderador.
    """
    if not hasattr(personagem, "campanhas"):
        return False

    if personagem.campanhas.filter(Q(mestre=user) | Q(moderadores=user)).exists():
        return True

    if is_safe:
        return personagem.campanhas.filter(jogadores=user).exists()

    return False


def compartilham_campanha(usuario_a, usuario_b):
    """
    Os dois estão numa mesma Campanha, em qualquer papel (mestre, moderador
    ou jogador)? É a régua de "conhecer" alguém no produto: o perfil de um
    usuário — e o mural de notas nele — só é visível para quem já joga com
    ele. Import local porque `Campanha` importa deste módulo.
    """
    from Campanha.models import Campanha

    return (
        Campanha.objects.filter(Q(mestre=usuario_a) | Q(jogadores=usuario_a) | Q(moderadores=usuario_a))
        .filter(Q(mestre=usuario_b) | Q(jogadores=usuario_b) | Q(moderadores=usuario_b))
        .exists()
    )


def _e_usuario(obj):
    # Checagem por classe, e não por atributo como o resto deste módulo:
    # o Usuario TEM `campanhas` (M2M reverso de `Campanha.jogadores`) e
    # `personagens`, e cairia no ramo errado de qualquer teste de `hasattr`.
    return isinstance(obj, get_user_model())


def pode_ver_perfil(user, perfil):
    """Quem pode ver (e anotar) o perfil `perfil`: ele mesmo, superuser, ou
    quem divide alguma campanha com ele."""
    return user.is_superuser or perfil.pk == user.pk or compartilham_campanha(user, perfil)


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

    if _e_usuario(obj):
        return pode_ver_perfil(user, obj)

    if hasattr(obj, "mestre") and hasattr(obj, "jogadores"):
        return obj.mestre == user or obj.jogadores.filter(pk=user.pk).exists()

    campanha = _get_campanha(obj)

    if campanha is not None:
        if pode_gerenciar_campanha(campanha, user):
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

        # --- O próprio objeto é um Usuario (perfil) ---
        # Ler: quem divide campanha com ele. Editar: só ele mesmo.
        if _e_usuario(obj):
            if obj.pk == request.user.pk:
                return True
            return is_safe and pode_ver_perfil(request.user, obj)

        # --- O próprio objeto é uma Campanha ---
        if hasattr(obj, "mestre") and hasattr(obj, "jogadores"):

            if obj.mestre == request.user:
                return True

            # Moderador tem os mesmos poderes do mestre sobre a campanha
            # (ex.: editar nome/banner), MENOS excluí-la — por isso o
            # DELETE fica de fora deste ramo, mesmo para moderador.
            if request.method != "DELETE" and obj.moderadores.filter(pk=request.user.pk).exists():
                return True

            if is_safe:
                return usuario_pode_ver_objeto(request.user, obj)

            return False

        # --- Objetos "de mundo" pertencentes a uma Campanha: NPC, Local,
        # Organizacao, Mapa, Sessao, Missao, Evento, Pasta, Conexao, etc.
        # Regra:
        #   - mestre/moderador: acesso total (ler, criar, editar, excluir)
        #   - jogador: leitura só se visivel_para_jogadores=True;
        #     escrita (PUT/PATCH) só se, além de visível, também for
        #     editavel_para_jogadores=True; DELETE nunca (só mestre/moderador).
        campanha = _get_campanha(obj)

        if campanha is not None:

            if pode_gerenciar_campanha(campanha, request.user):
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
    has_object_permission. Regra: mestre, moderador (ou superuser) podem
    criar ou excluir esses recursos.

    Também reaproveitado por `Campanha/views.py::remover_personagem` para
    decidir se quem está removendo um personagem da campanha tem poder de
    remover qualquer um (mestre/moderador) ou só a si mesmo (jogador
    comum). NÃO é usado por `remover_jogador` (expulsar um jogador) nem
    pela exclusão da própria campanha — essas duas ações continuam
    exclusivas do mestre-dono, mesmo para moderador (ver
    `_exige_mestre_dono` em `Campanha/views.py`).
    """
    return pode_gerenciar_campanha(campanha, request.user)


def check_object_permission(request, obj):
    permission = IsOwnerOrAdmin()

    if not permission.has_object_permission(request, None, obj):
        raise PermissionDenied(permission.message)