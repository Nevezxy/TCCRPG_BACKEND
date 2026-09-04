import hashlib

from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import (
    Campanha,
    NPC,
    Local,
    Organizacao,
    Mapa,
    Sessao,
    Missao,
    Evento,
    Nota,
    Pasta,
    TipoConexao,
    Conexao,
    modelos_conectaveis,
)
from Personagem.models import Personagem
from Personagem.serializers import CloudinaryUrlSerializerMixin  # ajuste o import conforme seu projeto


# ---------------------------------------------------------------------------
# Auxiliares reaproveitados
# ---------------------------------------------------------------------------

class RestringeCamposDeMestreMixin:
    """
    `visivel_para_jogadores`/`editavel_para_jogadores` só podem ser
    alteradas pelo mestre da campanha (ou superuser) — mesmo que um
    jogador tenha permissão de PATCH no objeto (porque
    editavel_para_jogadores=True), ele não pode usar esse mesmo PATCH para
    mudar essas duas flags e esconder o objeto ou travar a própria edição.
    Views passam `request` no context (ver Campanha/views.py); sem ele, o
    campo simplesmente não é restringido aqui (a permission já bloqueia
    quem não deveria estar chamando o serializer de qualquer forma).
    """
    campos_restritos_ao_mestre = ("visivel_para_jogadores", "editavel_para_jogadores")

    def _campanha_do(self, instance):
        if hasattr(instance, "campanha"):
            return instance.campanha
        if getattr(instance, "npc", None) is not None:
            return instance.npc.campanha
        if getattr(instance, "organizacao", None) is not None:
            return instance.organizacao.campanha
        return None

    def update(self, instance, validated_data):
        request = self.context.get("request")
        campanha = self._campanha_do(instance)

        if request and campanha and campanha.mestre != request.user and not request.user.is_superuser:
            for campo in self.campos_restritos_ao_mestre:
                validated_data.pop(campo, None)

        return super().update(instance, validated_data)


class ValidaPastaDaCampanhaMixin:
    """
    Garante que a `pasta` escolhida para uma entidade pertence à MESMA
    campanha da entidade — sem isso, seria possível "prender" um NPC (ou
    Local, Organizacao, ...) numa pasta de uma campanha completamente
    diferente (ver seção 5 da tarefa de refatoração: nenhuma dependência
    dessa checagem no frontend). Reaproveitado por todos os serializers de
    entidades organizáveis em pasta (NPC, Local, Organizacao, Mapa,
    Sessao, Missao, Evento).
    """

    def validate_pasta(self, pasta):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if pasta and campanha and pasta.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "Esta pasta não pertence à mesma campanha do objeto."
            )

        return pasta


class UsuarioResumoSerializer(serializers.Serializer):
    """
    Representação enxuta de um Usuario, só com o que a UI de Campanhas
    precisa exibir (cards de jogador, destaque do mestre). Evita vazar
    campos sensíveis do model de usuário completo.
    """
    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()


class CampanhaPersonagemResumoSerializer(serializers.Serializer):
    """
    Representação enxuta de um Personagem dentro do contexto de uma
    Campanha (cards da aba "Personagens"). Não substitui o
    PersonagemSerializer completo — é só o suficiente para o card.
    """
    id = serializers.IntegerField()
    foto = serializers.SerializerMethodField()
    nome = serializers.CharField()
    nivel = serializers.IntegerField()
    classe1 = serializers.CharField(allow_null=True)
    usuario = serializers.IntegerField(source="usuario_id")
    usuario_username = serializers.SerializerMethodField()

    def get_foto(self, obj):
        if not obj.foto:
            return None
        try:
            return obj.foto.url
        except Exception:
            return str(obj.foto)

    def get_usuario_username(self, obj):
        return obj.usuario.username if getattr(obj, "usuario", None) else None


class CampanhaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["banner"]

    mestre_info = serializers.SerializerMethodField()
    jogadores_info = serializers.SerializerMethodField()
    personagens_info = serializers.SerializerMethodField()

    class Meta:
        model = Campanha
        fields = "__all__"
        read_only_fields = (
            "mestre",
            "codigo",
            "criado_em",
            "atualizado_em",
        )

    def get_mestre_info(self, obj):
        return UsuarioResumoSerializer(obj.mestre).data

    def get_jogadores_info(self, obj):
        return UsuarioResumoSerializer(obj.jogadores.all(), many=True).data

    def get_personagens_info(self, obj):
        return CampanhaPersonagemResumoSerializer(
            obj.personagens.select_related("usuario").all(), many=True
        ).data


# ---------------------------------------------------------------------------
# Objetos "notáveis"/"conectáveis" — modelos aos quais uma Nota pode ser
# anexada, ou que podem participar de uma Conexao. Mantém a superfície de
# ataque pequena: sem essa allowlist, qualquer content_type do projeto
# (inclusive de outros apps, como o próprio Usuario) poderia ser
# referenciado. `modelos_conectaveis()` (em models.py) é a mesma lista sem
# Campanha — reaproveitada aqui para não divergir.
# ---------------------------------------------------------------------------

_MODELOS_NOTAVEIS = [Campanha, NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento, Personagem]


def campanhas_do_objeto_notavel(objeto):
    """
    Retorna as Campanhas às quais um objeto anotável/conectável pertence —
    uma só para a maioria dos tipos (NPC, Local, Organizacao, Mapa,
    Sessao, Missao, Evento têm `campanha` direta; a própria Campanha é ela
    mesma), possivelmente várias para Personagem (M2M `campanhas`). Usado
    tanto para validar Notas quanto Conexoes.
    """
    if isinstance(objeto, Campanha):
        return [objeto]
    if hasattr(objeto, "campanha_id"):
        return [objeto.campanha]
    if hasattr(objeto, "campanhas"):
        return list(objeto.campanhas.all())
    return []


def conexoes_de_entidade(entidade):
    """
    Lista as Conexoes (em qualquer direção) que envolvem `entidade`, já
    resolvidas para um formato simples de leitura — a mesma lógica usada
    tanto pelo campo `conexoes` de cada serializer de entidade quanto pelo
    endpoint dedicado `.../<entidade>/<pk>/conexoes/` (ver views.py).

    Esta é a peça pensada para os futuros backlinks estilo Obsidian: dado
    um NPC, por exemplo, ela já devolve tanto as conexões que ELE criou
    quanto as que outras entidades criaram apontando PARA ele (usando,
    quando existe, o `TipoConexao.inverso` para mostrar o rótulo do ponto
    de vista de quem está lendo — ex.: se "Arkan -> Filho de -> Maria"
    existe, a lista de conexões de Maria mostra "Arkan -> Mãe de", desde
    que o inverso de "Filho de" esteja cadastrado como "Mãe de").
    """
    content_type = ContentType.objects.get_for_model(entidade)

    conexoes = (
        Conexao.objects.filter(
            Q(entidade1_tipo=content_type, entidade1_id=entidade.pk) |
            Q(entidade2_tipo=content_type, entidade2_id=entidade.pk)
        )
        .select_related("tipo", "tipo__inverso")
    )

    resultado = []

    for conexao in conexoes:
        e_origem = (
            conexao.entidade1_tipo_id == content_type.id
            and conexao.entidade1_id == entidade.pk
        )

        if e_origem:
            outro_tipo, outro_id = conexao.entidade2_tipo, conexao.entidade2_id
            outro_objeto = conexao.entidade2
            nome_tipo = conexao.tipo.nome
        else:
            outro_tipo, outro_id = conexao.entidade1_tipo, conexao.entidade1_id
            outro_objeto = conexao.entidade1
            # Do ponto de vista de quem NÃO é a origem, mostramos o
            # inverso cadastrado (se existir) — ex.: "Mãe de" em vez de
            # repetir "Filho de" também do lado de Maria.
            nome_tipo = conexao.tipo.inverso.nome if conexao.tipo.inverso_id else conexao.tipo.nome

        resultado.append({
            "id": conexao.id,
            "direcao": "origem" if e_origem else "destino",
            "tipo_id": conexao.tipo_id,
            "tipo_nome": nome_tipo,
            "descricao": conexao.descricao,
            "entidade": {
                "tipo": outro_tipo.model,
                "id": outro_id,
                "nome": str(outro_objeto) if outro_objeto is not None else None,
            },
        })

    return resultado


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------

class NPCSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    # Só leitura — alimenta o painel de "Conexões" do NPC no frontend sem
    # precisar de uma chamada extra por organização/relação.
    # `organizacoes_lideradas` é o related_name de Organizacao.lider_npc
    # (FK estruturada, não passa por Conexao). As demais relações (quem é
    # membro de quê, quem é amigo/inimigo/parente de quem — antes
    # RelacaoNPC/MembroOrganizacao) agora vêm todas de `conexoes`, via
    # Conexao (ver `conexoes_de_entidade` acima).
    organizacoes_lideradas = serializers.SerializerMethodField()
    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = NPC
        fields = "__all__"
        # `campanha` é sempre definida pela view a partir da URL, nunca pelo
        # corpo da requisição — evita que alguém "mova" um NPC pra outra
        # campanha sem querer (ou pra uma campanha que não é dele).
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_organizacoes_lideradas(self, obj):
        return [{"id": o.id, "nome": o.nome} for o in obj.organizacoes_lideradas.all()]

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate_localizacao(self, local):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if local and campanha and local.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "Este local não pertence à mesma campanha do NPC."
            )

        return local


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

class LocalSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    # Conexões ESTRUTURADAS (via FK/M2M direta, não via Conexao): quem
    # está localizado aqui, quem tem sede aqui, missões/mapas/eventos
    # ligados a este local. Os related_names usados vêm todos de
    # models.py: `npcs_localizados` (NPC.localizacao), `organizacoes_sede`
    # (Organizacao.sede), `missoes` (Missao.local), `mapas` (Mapa.local),
    # `eventos` (Evento.locais, M2M).
    conexoes_estruturadas = serializers.SerializerMethodField()
    # Conexões GENÉRICAS (via Conexao) — ex.: eventos históricos
    # cadastrados manualmente pelo mestre envolvendo este local.
    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Local
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_conexoes_estruturadas(self, obj):
        return {
            "npcs": [{"id": n.id, "nome": n.nome} for n in obj.npcs_localizados.all()],
            "organizacoes": [{"id": o.id, "nome": o.nome} for o in obj.organizacoes_sede.all()],
            "missoes": [{"id": m.id, "nome": m.titulo} for m in obj.missoes.all()],
            "mapas": [{"id": m.id, "nome": m.nome} for m in obj.mapas.all()],
            "eventos": [{"id": e.id, "nome": e.titulo} for e in obj.eventos.all()],
        }

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------

class OrganizacaoSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["logo"]

    lider_tipo = serializers.SerializerMethodField()
    lider_nome = serializers.SerializerMethodField()
    # Estruturadas: eventos ligados a esta organização (Evento.organizacoes,
    # M2M). Membros (antes MembroOrganizacao) agora são Conexao — ver
    # `conexoes` abaixo (tipo "Membro de"/"Possui membro").
    conexoes_estruturadas = serializers.SerializerMethodField()
    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Organizacao
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_lider_tipo(self, obj):
        if obj.lider_personagem_id:
            return "personagem"
        if obj.lider_npc_id:
            return "npc"
        return None

    def get_lider_nome(self, obj):
        return obj.lider.nome if obj.lider else None

    def get_conexoes_estruturadas(self, obj):
        return {
            "eventos": [{"id": e.id, "nome": e.titulo} for e in obj.eventos.all()],
        }

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate(self, attrs):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        # Em PATCH parcial, `attrs` só traz os campos que vieram na
        # requisição — para decidir corretamente se os dois líderes
        # ficariam preenchidos ao mesmo tempo, precisamos considerar o
        # valor já salvo no campo que não foi enviado agora.
        if "lider_personagem" in attrs:
            lider_personagem = attrs["lider_personagem"]
        else:
            lider_personagem = self.instance.lider_personagem if self.instance else None

        if "lider_npc" in attrs:
            lider_npc = attrs["lider_npc"]
        else:
            lider_npc = self.instance.lider_npc if self.instance else None

        sede = attrs.get("sede")

        # No máximo um líder — mas pode não ter nenhum ainda (a
        # Organização nasce sem líder na criação rápida do frontend; o
        # mestre define depois, um campo de cada vez, na página dedicada).
        if lider_personagem and lider_npc:
            raise serializers.ValidationError(
                "Escolha no máximo um líder: `lider_personagem` OU `lider_npc`, não os dois ao mesmo tempo."
            )

        if campanha:
            if lider_personagem and not lider_personagem.campanhas.filter(pk=campanha.id).exists():
                raise serializers.ValidationError(
                    "O líder (personagem) precisa participar desta campanha."
                )

            if lider_npc and lider_npc.campanha_id != campanha.id:
                raise serializers.ValidationError(
                    "O líder (NPC) precisa pertencer a esta campanha."
                )

            if sede and sede.campanha_id != campanha.id:
                raise serializers.ValidationError(
                    "A sede precisa ser um local desta campanha."
                )

        return attrs


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

class MapaSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Mapa
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate_local(self, local):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if local and campanha and local.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "Este local não pertence a esta campanha."
            )

        return local


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------

class SessaoSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Sessao
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate_numero(self, numero):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if campanha:
            existentes = Sessao.objects.filter(campanha=campanha, numero=numero)

            if self.instance:
                existentes = existentes.exclude(pk=self.instance.pk)

            if existentes.exists():
                raise serializers.ValidationError(
                    "Já existe uma sessão com este número nesta campanha."
                )

        return numero


# ---------------------------------------------------------------------------
# Missao
# ---------------------------------------------------------------------------

class MissaoSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Missao
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate_local(self, local):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if local and campanha and local.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "Este local não pertence a esta campanha."
            )

        return local


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------

class EventoSerializer(ValidaPastaDaCampanhaMixin, RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    # `locais`/`organizacoes` (nos campos padrão do model) já vêm como
    # listas de IDs — só leitura, para a UI conseguir exibir nomes em vez
    # de precisar resolvê-los com chamadas extras.
    locais_info = serializers.SerializerMethodField()
    organizacoes_info = serializers.SerializerMethodField()
    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Evento
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_locais_info(self, obj):
        return [{"id": l.id, "nome": l.nome} for l in obj.locais.all()]

    def get_organizacoes_info(self, obj):
        return [{"id": o.id, "nome": o.nome} for o in obj.organizacoes.all()]

    def get_conexoes(self, obj):
        return conexoes_de_entidade(obj)

    def validate_locais(self, locais):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if campanha and any(local.campanha_id != campanha.id for local in locais):
            raise serializers.ValidationError(
                "Todos os locais precisam pertencer a esta campanha."
            )

        return locais

    def validate_organizacoes(self, organizacoes):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if campanha and any(org.campanha_id != campanha.id for org in organizacoes):
            raise serializers.ValidationError(
                "Todas as organizações precisam pertencer a esta campanha."
            )

        return organizacoes


# ---------------------------------------------------------------------------
# Pasta — organização em árvore, estilo Obsidian
# ---------------------------------------------------------------------------

class PastaSerializer(serializers.ModelSerializer):

    subpastas_count = serializers.SerializerMethodField()

    class Meta:
        model = Pasta
        fields = "__all__"
        # `campanha` é sempre definida pela view a partir da URL, mesmo
        # padrão usado pelas entidades "de mundo" acima.
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_subpastas_count(self, obj):
        return obj.subpastas.count()

    def validate_pasta_pai(self, pasta_pai):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if pasta_pai is None:
            return pasta_pai

        # Regra 1 (seção 5 da tarefa): a pasta-pai precisa ser da MESMA
        # campanha — sem essa checagem, seria possível "mover" uma pasta
        # (e, por consequência, tudo que está dentro dela) para dentro da
        # árvore de outra campanha.
        if campanha and pasta_pai.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "A pasta-pai precisa pertencer à mesma campanha."
            )

        # Regra 2: proteção contra ciclos — uma pasta não pode ser
        # descendente de si mesma. Só se aplica em UPDATE (numa criação,
        # `self.instance` ainda não existe, então não há como o novo
        # registro já estar na árvore).
        if self.instance:
            if pasta_pai.pk == self.instance.pk:
                raise serializers.ValidationError(
                    "Uma pasta não pode ser pai de si mesma."
                )

            ancestral = pasta_pai
            visitados = set()

            while ancestral is not None:
                if ancestral.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        "Esta movimentação criaria um ciclo na árvore de pastas "
                        "(a pasta de destino é descendente da pasta que está sendo movida)."
                    )

                # Salvaguarda contra um ciclo JÁ existente no banco (não
                # deveria acontecer, dada esta mesma validação, mas evita
                # um loop infinito caso aconteça por alguma via externa).
                if ancestral.pk in visitados:
                    break

                visitados.add(ancestral.pk)
                ancestral = ancestral.pasta_pai

        return pasta_pai


# ---------------------------------------------------------------------------
# TipoConexao
# ---------------------------------------------------------------------------

class TipoConexaoSerializer(serializers.ModelSerializer):

    inverso_nome = serializers.CharField(source="inverso.nome", read_only=True)

    class Meta:
        model = TipoConexao
        fields = "__all__"


# ---------------------------------------------------------------------------
# Conexao — relacionamento genérico entre entidades de uma Campanha
# ---------------------------------------------------------------------------

class ConexaoSerializer(serializers.ModelSerializer):
    """
    `entidade1_tipo`/`entidade2_tipo` são aceitos/devolvidos pelo nome do
    model em minúsculo (ex.: "npc", "organizacao", "personagem") — mesmo
    padrão já usado por `NotaSerializer.content_type` — em vez do PK
    numérico interno de ContentType, que muda por instalação.
    """

    entidade1_tipo = serializers.SlugRelatedField(
        slug_field="model", queryset=ContentType.objects.all()
    )
    entidade2_tipo = serializers.SlugRelatedField(
        slug_field="model", queryset=ContentType.objects.all()
    )

    tipo_nome = serializers.CharField(source="tipo.nome", read_only=True)
    entidade1_info = serializers.SerializerMethodField()
    entidade2_info = serializers.SerializerMethodField()

    class Meta:
        model = Conexao
        fields = "__all__"
        # `campanha` é sempre definida pela view — nunca pelo corpo da
        # requisição (mesmo racional de NPC.campanha etc.): evita que
        # alguém crie uma Conexao "na campanha errada" só porque esqueceu
        # de trocar o campo, e é o valor que a validação de campanha usa
        # como referência (ver `validate` abaixo).
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_entidade1_info(self, obj):
        return {"nome": str(obj.entidade1)} if obj.entidade1 is not None else None

    def get_entidade2_info(self, obj):
        return {"nome": str(obj.entidade2)} if obj.entidade2 is not None else None

    def validate_entidade1_tipo(self, content_type):
        return self._valida_tipo_conectavel(content_type)

    def validate_entidade2_tipo(self, content_type):
        return self._valida_tipo_conectavel(content_type)

    def _valida_tipo_conectavel(self, content_type):
        modelo = content_type.model_class()

        if modelo not in modelos_conectaveis():
            permitidos = ", ".join(m.__name__ for m in modelos_conectaveis())
            raise serializers.ValidationError(
                f"Não é possível criar conexões com este tipo de entidade. "
                f"Tipos permitidos: {permitidos}."
            )

        return content_type

    def validate(self, attrs):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        e1_tipo = attrs.get("entidade1_tipo") or (self.instance.entidade1_tipo if self.instance else None)
        e1_id = attrs.get("entidade1_id") if "entidade1_id" in attrs else (self.instance.entidade1_id if self.instance else None)
        e2_tipo = attrs.get("entidade2_tipo") or (self.instance.entidade2_tipo if self.instance else None)
        e2_id = attrs.get("entidade2_id") if "entidade2_id" in attrs else (self.instance.entidade2_id if self.instance else None)

        entidade1 = entidade2 = None

        if e1_tipo and e1_id is not None:
            entidade1 = e1_tipo.model_class().objects.filter(pk=e1_id).first()

            if entidade1 is None:
                raise serializers.ValidationError(
                    "A entidade1 referenciada (entidade1_tipo/entidade1_id) não existe."
                )

        if e2_tipo and e2_id is not None:
            entidade2 = e2_tipo.model_class().objects.filter(pk=e2_id).first()

            if entidade2 is None:
                raise serializers.ValidationError(
                    "A entidade2 referenciada (entidade2_tipo/entidade2_id) não existe."
                )

        if e1_tipo and e2_tipo and e1_id is not None and e2_id is not None:
            if e1_tipo.id == e2_tipo.id and e1_id == e2_id:
                raise serializers.ValidationError(
                    "Uma entidade não pode se conectar a si mesma."
                )

        # Regra central (seção 9 da tarefa): as duas entidades da Conexao
        # precisam pertencer à MESMA campanha do endpoint — sem essa
        # checagem, seria possível ligar um NPC da Campanha A a um
        # Personagem da Campanha B.
        if campanha:
            for entidade in (entidade1, entidade2):
                if entidade is not None:
                    campanhas_da_entidade = {c.id for c in campanhas_do_objeto_notavel(entidade)}

                    if campanha.id not in campanhas_da_entidade:
                        raise serializers.ValidationError(
                            "Ambas as entidades da conexão precisam pertencer a esta campanha."
                        )

        return attrs


# ---------------------------------------------------------------------------
# Nota (genérica, via GenericForeignKey)
# ---------------------------------------------------------------------------

def _cor_identificacao(chave: str) -> str:
    """
    Gera uma cor HSL determinística a partir de uma chave estável (ex.:
    "personagem:12", "usuario:4") — sempre a MESMA cor para a mesma chave,
    sem precisar persistir nada no banco. Usada para identificar
    visualmente o autor de cada nota: a cor "nasce" na primeira vez que o
    personagem/usuário aparece e permanece igual dali em diante, em toda a
    campanha, porque é sempre recalculada a partir do mesmo id.
    """
    digest = hashlib.md5(chave.encode("utf-8")).hexdigest()
    hue = int(digest[:8], 16) % 360
    return f"hsl({hue}, 65%, 55%)"


class NotaSerializer(serializers.ModelSerializer):

    # Em vez de exigir o PK numérico interno de ContentType (que muda por
    # instalação e o frontend não tem como conhecer de antemão), aceita e
    # devolve o nome do model em minúsculo (ex.: "npc", "local",
    # "campanha") — o mesmo valor usado no filtro `?content_type=` de
    # nota_lista e em `tipo_objeto`.
    content_type = serializers.SlugRelatedField(
        slug_field="model",
        queryset=ContentType.objects.all()
    )

    # Personagem que "fala" a nota — opcional: fica nulo quando o usuário
    # não tem nenhum Personagem nesta campanha, caso em que a nota é
    # atribuída ao usuário mesmo (ver `get_autor`).
    personagem = serializers.PrimaryKeyRelatedField(
        queryset=Personagem.objects.all(), required=False, allow_null=True
    )

    tipo_objeto = serializers.SerializerMethodField()
    # Quem "fala" a nota: o Personagem escolhido, ou o usuário como
    # fallback. Notas são públicas para leitura entre os participantes da
    # campanha (ver nota_lista/nota_detalhe), por isso a UI precisa saber
    # quem escreveu cada uma — incluindo foto e cor de identificação.
    autor = serializers.SerializerMethodField()
    # Nome legível do objeto anotado (ex.: o `nome` do NPC), para a aba
    # "Minhas Notas" mostrar mais que só o tipo. None se o objeto já foi
    # excluído (nota "órfã").
    objeto_nome = serializers.SerializerMethodField()

    class Meta:
        model = Nota
        fields = [
            "id",
            "content_type",
            "object_id",
            "tipo_objeto",
            "objeto_nome",
            "titulo",
            "conteudo",
            "usuario",
            "personagem",
            "autor",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = ("usuario", "criado_em", "atualizado_em")

    def get_tipo_objeto(self, obj):
        return obj.content_type.model

    def get_autor(self, obj):
        if obj.personagem_id:
            foto = None
            try:
                foto = obj.personagem.foto.url if obj.personagem.foto else None
            except Exception:
                foto = None

            return {
                "tipo": "personagem",
                "id": obj.personagem_id,
                "nome": obj.personagem.nome,
                "foto": foto,
                "cor": _cor_identificacao(f"personagem:{obj.personagem_id}"),
            }

        return {
            "tipo": "usuario",
            "id": obj.usuario_id,
            "nome": obj.usuario.first_name or obj.usuario.username,
            "foto": None,
            "cor": _cor_identificacao(f"usuario:{obj.usuario_id}"),
        }

    def get_objeto_nome(self, obj):
        alvo = obj.objeto  # resolvido via GenericForeignKey
        return str(alvo) if alvo is not None else None

    def validate_content_type(self, content_type):
        modelo = content_type.model_class()

        if modelo not in _MODELOS_NOTAVEIS:
            permitidos = ", ".join(m.__name__ for m in _MODELOS_NOTAVEIS)
            raise serializers.ValidationError(
                f"Não é possível anexar notas a este tipo de objeto. "
                f"Tipos permitidos: {permitidos}."
            )

        return content_type

    def validate(self, attrs):
        content_type = attrs.get("content_type") or getattr(self.instance, "content_type", None)
        object_id = attrs.get("object_id") or getattr(self.instance, "object_id", None)
        objeto = None

        if content_type and object_id:
            modelo = content_type.model_class()
            objeto = modelo.objects.filter(pk=object_id).first()

            if objeto is None:
                raise serializers.ValidationError(
                    "O objeto referenciado por content_type/object_id não existe."
                )

        personagem = attrs.get("personagem")

        if personagem is not None:
            request = self.context.get("request")

            # Só pode "falar" pelos PRÓPRIOS personagens, nunca pelo de outra pessoa.
            if request and personagem.usuario_id != request.user.id:
                raise serializers.ValidationError(
                    "Você só pode escrever notas usando um personagem que seja seu."
                )

            if objeto is not None:
                campanhas_objeto = {c.id for c in campanhas_do_objeto_notavel(objeto)}
                campanhas_personagem = set(personagem.campanhas.values_list("id", flat=True))

                if not (campanhas_objeto & campanhas_personagem):
                    raise serializers.ValidationError(
                        "Este personagem não participa da campanha deste objeto."
                    )

        return attrs
