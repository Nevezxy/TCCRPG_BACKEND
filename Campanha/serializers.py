import hashlib

from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType

from .models import (
    Campanha,
    NPC,
    RelacaoNPC,
    Local,
    Organizacao,
    MembroOrganizacao,
    Mapa,
    Sessao,
    Missao,
    Evento,
    Nota,
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
# NPC
# ---------------------------------------------------------------------------

class NPCSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    # Só leitura — alimenta o painel de "Conexões" do NPC no frontend sem
    # precisar de uma chamada extra por organização. `organizacoes_lideradas`
    # é o related_name de Organizacao.lider_npc; `membroorganizacao_set` é o
    # reverso padrão (sem related_name definido) de MembroOrganizacao.npc.
    organizacoes_lideradas = serializers.SerializerMethodField()
    organizacoes_membro = serializers.SerializerMethodField()
    # As relações onde ESTE NPC é a ORIGEM (obj.relacoes) já têm endpoint
    # próprio (RelacaoNPC, listado/editado via relacaoNpcApi). O que falta
    # é o sentido contrário: outros NPCs cuja relação aponta PARA este NPC
    # (`relacoes_com_outros_npcs`, related_name de RelacaoNPC.outro_npc) —
    # sem isso, "quem considera este NPC seu amigo" nunca aparecia em
    # lugar nenhum. Só leitura: a edição continua acontecendo do lado de
    # quem é a origem da relação.
    relacoes_reversas = serializers.SerializerMethodField()

    class Meta:
        model = NPC
        fields = "__all__"
        # `campanha` é sempre definida pela view a partir da URL, nunca pelo
        # corpo da requisição — evita que alguém "mova" um NPC pra outra
        # campanha sem querer (ou pra uma campanha que não é dele).
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_organizacoes_lideradas(self, obj):
        return [{"id": o.id, "nome": o.nome} for o in obj.organizacoes_lideradas.all()]

    def get_organizacoes_membro(self, obj):
        return [
            {"id": m.organizacao_id, "nome": m.organizacao.nome, "cargo": m.cargo}
            for m in obj.membroorganizacao_set.select_related("organizacao").all()
        ]

    def get_relacoes_reversas(self, obj):
        return [
            {"id": r.id, "npc_id": r.npc_id, "npc_nome": r.npc.nome, "tipo_relacao": r.tipo_relacao}
            for r in obj.relacoes_com_outros_npcs.select_related("npc").all()
        ]

    def validate_localizacao(self, local):
        campanha = self.instance.campanha if self.instance else self.context.get("campanha")

        if local and campanha and local.campanha_id != campanha.id:
            raise serializers.ValidationError(
                "Este local não pertence à mesma campanha do NPC."
            )

        return local


# ---------------------------------------------------------------------------
# RelacaoNPC
# ---------------------------------------------------------------------------

class RelacaoNPCSerializer(serializers.ModelSerializer):

    origem_tipo = serializers.SerializerMethodField()
    origem_nome = serializers.SerializerMethodField()

    # Campos write-only, não persistidos no model (removidos em create()) —
    # permitem ao frontend pedir a criação automática da relação inversa
    # (ex.: João→Amigo→Pedro também cria Pedro→Amigo→João). Só faz sentido
    # quando a origem é outro NPC (`outro_npc`): quando a origem é um
    # Personagem não existe "segunda ponta" no banco para gravar a
    # recíproca (Personagem não tem uma lista própria de relações), então
    # esses campos são simplesmente ignorados nesse caso.
    criar_reciproca = serializers.BooleanField(write_only=True, required=False, default=False)
    tipo_relacao_reciproca = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=""
    )

    class Meta:
        model = RelacaoNPC
        fields = "__all__"
        # `npc` é sempre a origem/dono da relação, definido pela view a
        # partir da URL (mesmo padrão de `campanha` acima).
        read_only_fields = ("npc",)

    def get_origem_tipo(self, obj):
        return "personagem" if obj.personagem_id else "npc"

    def get_origem_nome(self, obj):
        return obj.origem.nome if obj.origem else None

    def validate(self, attrs):
        npc = self.instance.npc if self.instance else self.context.get("npc")
        personagem = attrs.get("personagem")
        outro_npc = attrs.get("outro_npc")

        if bool(personagem) == bool(outro_npc):
            raise serializers.ValidationError(
                "Informe exatamente uma origem: `personagem` OU `outro_npc`."
            )

        if npc:
            if personagem and not personagem.campanhas.filter(pk=npc.campanha_id).exists():
                raise serializers.ValidationError(
                    "Este personagem não participa da campanha deste NPC."
                )

            if outro_npc and outro_npc.campanha_id != npc.campanha_id:
                raise serializers.ValidationError(
                    "O NPC de origem precisa pertencer à mesma campanha."
                )

            if outro_npc and outro_npc.pk == npc.pk:
                raise serializers.ValidationError(
                    "Um NPC não pode ter uma relação consigo mesmo."
                )

        return attrs

    def create(self, validated_data):
        criar_reciproca = validated_data.pop("criar_reciproca", False)
        tipo_reciproco = validated_data.pop("tipo_relacao_reciproca", "") or validated_data.get("tipo_relacao", "")

        relacao = super().create(validated_data)

        if criar_reciproca and relacao.outro_npc_id:
            ja_existe = RelacaoNPC.objects.filter(
                npc=relacao.outro_npc,
                outro_npc=relacao.npc,
                tipo_relacao=tipo_reciproco
            ).exists()

            # Se a recíproca já existir (usuário criou as duas manualmente
            # antes, por exemplo), não duplica — a unique constraint
            # `relacaonpc_npc_unica` rejeitaria mesmo, mas checar antes
            # evita estourar uma exceção de integridade no meio do request.
            if not ja_existe:
                RelacaoNPC.objects.create(
                    npc=relacao.outro_npc,
                    outro_npc=relacao.npc,
                    tipo_relacao=tipo_reciproco,
                    descricao=relacao.descricao
                )

        return relacao


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

class LocalSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    # Só leitura — alimenta o painel de "Conexões" do Local no frontend.
    # Os related_names usados vêm todos de models.py: `npcs_localizados`
    # (NPC.localizacao), `organizacoes_sede` (Organizacao.sede), `missoes`
    # (Missao.local), `mapas` (Mapa.local), `eventos` (Evento.locais, M2M).
    conexoes = serializers.SerializerMethodField()

    class Meta:
        model = Local
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_conexoes(self, obj):
        return {
            "npcs": [{"id": n.id, "nome": n.nome} for n in obj.npcs_localizados.all()],
            "organizacoes": [{"id": o.id, "nome": o.nome} for o in obj.organizacoes_sede.all()],
            "missoes": [{"id": m.id, "nome": m.titulo} for m in obj.missoes.all()],
            "mapas": [{"id": m.id, "nome": m.nome} for m in obj.mapas.all()],
            "eventos": [{"id": e.id, "nome": e.titulo} for e in obj.eventos.all()],
        }


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------

class OrganizacaoSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["logo"]

    lider_tipo = serializers.SerializerMethodField()
    lider_nome = serializers.SerializerMethodField()
    # Só leitura — Membros já tem endpoint próprio (MembroOrganizacao, com
    # CRUD completo), então aqui só entra o que ainda não tem outra tela:
    # eventos ligados a esta organização (Evento.organizacoes, M2M).
    # OBS: não existe hoje um model de relação Organização↔Organização —
    # por isso essa conexão específica não pode ser exibida ainda.
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

    def get_conexoes(self, obj):
        return {
            "eventos": [{"id": e.id, "nome": e.titulo} for e in obj.eventos.all()],
        }

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
# MembroOrganizacao
# ---------------------------------------------------------------------------

class MembroOrganizacaoSerializer(serializers.ModelSerializer):

    membro_tipo = serializers.SerializerMethodField()
    membro_nome = serializers.SerializerMethodField()

    class Meta:
        model = MembroOrganizacao
        fields = "__all__"
        read_only_fields = ("organizacao",)

    def get_membro_tipo(self, obj):
        return "personagem" if obj.personagem_id else "npc"

    def get_membro_nome(self, obj):
        return obj.membro.nome if obj.membro else None

    def validate(self, attrs):
        organizacao = self.instance.organizacao if self.instance else self.context.get("organizacao")
        personagem = attrs.get("personagem")
        npc = attrs.get("npc")

        if bool(personagem) == bool(npc):
            raise serializers.ValidationError(
                "Informe exatamente um membro: `personagem` OU `npc`."
            )

        if organizacao:
            if personagem and not personagem.campanhas.filter(pk=organizacao.campanha_id).exists():
                raise serializers.ValidationError(
                    "Este personagem não participa da campanha desta organização."
                )

            if npc and npc.campanha_id != organizacao.campanha_id:
                raise serializers.ValidationError(
                    "Este NPC não pertence à campanha desta organização."
                )

        return attrs


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

class MapaSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    class Meta:
        model = Mapa
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

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

class SessaoSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    class Meta:
        model = Sessao
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

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

class MissaoSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    class Meta:
        model = Missao
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

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

class EventoSerializer(RestringeCamposDeMestreMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["imagem"]

    # `locais`/`organizacoes` (nos campos padrão do model) já vêm como
    # listas de IDs — só leitura, para a UI conseguir exibir nomes em vez
    # de precisar resolvê-los com chamadas extras.
    locais_info = serializers.SerializerMethodField()
    organizacoes_info = serializers.SerializerMethodField()

    class Meta:
        model = Evento
        fields = "__all__"
        read_only_fields = ("campanha", "criado_em", "atualizado_em")

    def get_locais_info(self, obj):
        return [{"id": l.id, "nome": l.nome} for l in obj.locais.all()]

    def get_organizacoes_info(self, obj):
        return [{"id": o.id, "nome": o.nome} for o in obj.organizacoes.all()]

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
# Nota (genérica, via GenericForeignKey)
# ---------------------------------------------------------------------------

# Modelos aos quais uma Nota pode ser anexada. Mantém a superfície de ataque
# pequena: sem essa allowlist, qualquer content_type do projeto (inclusive
# de outros apps, como o próprio Usuario) poderia ser referenciado.
_MODELOS_NOTAVEIS = [Campanha, NPC, Local, Organizacao, Mapa, Sessao, Missao, Evento, Personagem]


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


def campanhas_do_objeto_notavel(objeto):
    """
    Retorna as Campanhas às quais um objeto anotável pertence — uma só
    para a maioria dos tipos (NPC, Local, Organizacao, Mapa, Sessao,
    Missao, Evento têm `campanha` direta; a própria Campanha é ela mesma),
    possivelmente várias para Personagem (M2M `campanhas`). Usado para
    validar se o Personagem escolhido como autor de uma nota participa da
    MESMA campanha do objeto anotado.
    """
    if isinstance(objeto, Campanha):
        return [objeto]
    if hasattr(objeto, "campanha_id"):
        return [objeto.campanha]
    if hasattr(objeto, "campanhas"):
        return list(objeto.campanhas.all())
    return []


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