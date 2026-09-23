from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework import serializers
from Sistema.serializers import SincronizaSistemasMixin
from drf_spectacular.utils import extend_schema_field

# O mixin mora no app Midia (upload seguro + enquadramento + limpeza do
# Cloudinary); reexportado aqui porque o Campanha já o importa deste módulo.
from Midia.serializers import CloudinaryUrlSerializerMixin  # noqa: F401

from . import calculos
from .models import *


class ValorFinalMixin(serializers.Serializer):
    """
    Publica `valor_final` (e a decomposição que o card exibe) para Atributo,
    Status, Defesa e Perícia — as quatro entidades cujo número o backend
    deriva. As fórmulas moram todas em `Personagem/calculos.py`; aqui só as
    expomos.

    HERDA DE `serializers.Serializer` de propósito, apesar de ser um mixin: a
    metaclasse do DRF só recolhe campos declarados de bases que já tenham
    `_declared_fields`, e num mixin "solto" (herdando de `object`) os quatro
    campos abaixo seriam silenciosamente ignorados — `fields = "__all__"`
    devolveria a linha sem `valor_final`, sem erro nenhum. Use sempre ANTES
    do `ModelSerializer` na lista de bases, para o `get_fields()` dele
    continuar valendo.

    O CONTEXTO DE CÁLCULO É COMPARTILHADO por toda a resposta. Sem isso,
    serializar 21 perícias faria 21 consultas de bônus + 21 de atributo (o
    mesmo N+1 que o frontend tinha com um `useBonusTotal` por card). Ele é
    guardado no serializer RAIZ: num `many=True` a raiz é o ListSerializer,
    então os 21 filhos compartilham um contexto só.

    Uma view que já sabe de quais personagens se trata pode passar um
    contexto pré-carregado em `context={"calculo": ContextoCalculo([ids])}` —
    é o que `calculos_ficha` e o snapshot do Escudo fazem.
    """

    valor_final = serializers.SerializerMethodField()
    bonus_total = serializers.SerializerMethodField()
    atributo_total = serializers.SerializerMethodField()
    valor_final_incompleto = serializers.SerializerMethodField()

    CAMPOS_CALCULADOS = ("valor_final", "bonus_total", "atributo_total", "valor_final_incompleto")

    def contexto_calculo(self):
        raiz = self.root
        contexto = getattr(raiz, "_contexto_calculo", None)
        if contexto is None:
            contexto = self.context.get("calculo") or calculos.ContextoCalculo()
            raiz._contexto_calculo = contexto
        return contexto

    @extend_schema_field(serializers.IntegerField())
    def get_valor_final(self, obj):
        return self.contexto_calculo().valor_final(obj)

    @extend_schema_field(serializers.IntegerField())
    def get_bonus_total(self, obj):
        """Soma dos bônus vigentes — o "+ Bônus 3" da legenda do card."""
        return self.contexto_calculo().componentes(obj)["bonus"]

    @extend_schema_field(serializers.IntegerField())
    def get_atributo_total(self, obj):
        """Contribuição do Atributo vinculado, já multiplicada pelo Nível
        quando `Status.atributo_nivel` está marcado."""
        return self.contexto_calculo().componentes(obj)["atributo"]

    @extend_schema_field(serializers.BooleanField())
    def get_valor_final_incompleto(self, obj):
        """True quando um ciclo de bônus truncou o cálculo — o frontend avisa
        o jogador em vez de exibir um número silenciosamente errado."""
        return self.contexto_calculo().incompleto(obj)


class PersonagemSerializer(SincronizaSistemasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto", "banner"]

    # Ids das campanhas das quais este personagem participa (M2M reverso de
    # `Campanha.personagens`). Só leitura: quem entra/sai de uma campanha é
    # decidido pelos endpoints da própria Campanha, nunca por um PATCH na
    # ficha. Exposto porque a Biblioteca precisa saber quais campanhas
    # consultar para oferecer os equipamentos exclusivos delas — mesmo papel
    # que `sistemas` já cumpre para as bibliotecas de regras.
    campanhas = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Personagem
        fields = "__all__"
        read_only_fields = ("usuario",)


class StatusSerializer(ValorFinalMixin, serializers.ModelSerializer):

    # Status é a única entidade com DOIS finais. Num status de barra o
    # Atributo e os bônus somam ao TETO (`valor_max_final`), não ao valor
    # atual — é como a ficha sempre se comportou; num status simples o que
    # aparece no card é o `valor_final`. `valor_temp` continua FORA dos dois,
    # exibido à parte entre parênteses.
    valor_max_final = serializers.SerializerMethodField()

    class Meta:
        model = Status
        fields = "__all__"
        read_only_fields = ("personagem",)

    @extend_schema_field(serializers.IntegerField())
    def get_valor_max_final(self, obj):
        return self.contexto_calculo().valor_max_final(obj)


class AtributoSerializer(ValorFinalMixin, serializers.ModelSerializer):

    class Meta:
        model = Atributo
        fields = "__all__"
        read_only_fields = ("personagem",)


class DefesaSerializer(ValorFinalMixin, serializers.ModelSerializer):

    class Meta:
        model = Defesa
        fields = "__all__"
        read_only_fields = ("personagem",)


class PericiaSerializer(ValorFinalMixin, serializers.ModelSerializer):

    class Meta:
        model = Pericia
        fields = "__all__"
        read_only_fields = ("personagem",)


class SincronizaVendasMixin:
    """
    Faz `Item.vendas` valer de verdade: marcado, o item é anunciado no
    Comércio Livre da campanha (preço = `valor`, quantidade = a que o
    personagem tem); desmarcado, é retirado da venda.

    Sem isto o booleano seria só decoração — a ficha diria "à venda" e não
    haveria anúncio nenhum para os outros jogadores comprarem.

    Só age quando o campo VEIO na requisição: um PATCH que mexe no peso não
    tem por que recriar (nem encerrar) um anúncio. O import é tardio porque
    `Campanha` importa `Personagem`, nunca o contrário.

    Uma regra de comércio violada (personagem sem campanha, ou em várias, e
    por isso ambígua) vira erro de validação no campo `vendas`. O save e a
    sincronização ficam na MESMA transação de propósito: sem ela o item já
    estaria gravado com `vendas=True` quando o erro subisse, e a ficha
    passaria a mentir — diria "à venda" sem existir anúncio nenhum.
    """

    def _com_sincronizacao(self, salvar, veio_no_payload):
        from Campanha.comercio import ErroComercio, sincronizar_vendas

        if not veio_no_payload:
            return salvar()

        try:
            with transaction.atomic():
                instance = salvar()
                sincronizar_vendas(instance)
        except ErroComercio as exc:
            raise serializers.ValidationError({"vendas": [exc.mensagem]}) from exc

        return instance

    def create(self, validated_data):
        return self._com_sincronizacao(
            lambda: super(SincronizaVendasMixin, self).create(validated_data),
            "vendas" in validated_data,
        )

    def update(self, instance, validated_data):
        return self._com_sincronizacao(
            lambda: super(SincronizaVendasMixin, self).update(instance, validated_data),
            "vendas" in validated_data,
        )


class ItemSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Item
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Arma
        fields = "__all__"
        read_only_fields = ("personagem",)


class ArmaduraSerializer(SincronizaVendasMixin, CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["foto"]

    class Meta:
        model = Armadura
        fields = "__all__"
        # `defesa` CONTINUA sendo o campo que o jogador edita na armadura; o
        # `valor_final` herdado de `Item` é só o espelho dela, mantido pelo
        # `Armadura.save()`. Deixá-lo editável permitiria gravar um número
        # diferente de `defesa`, que o próximo save desfaria sem avisar.
        read_only_fields = ("personagem", "valor_final")


class TecnicaSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Tecnica
        fields = "__all__"
        read_only_fields = ("personagem",)


class PoderSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Poder
        fields = "__all__"
        read_only_fields = ("personagem",)


class PoderUsuarioSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):
    """Poder da conta (ver `PoderUsuario`)."""

    media_fields = ["midia"]

    class Meta:
        model = PoderUsuario
        fields = "__all__"
        read_only_fields = ("usuario", "criado_em", "atualizado_em")


class HabilidadeSerializer(CloudinaryUrlSerializerMixin, serializers.ModelSerializer):

    media_fields = ["midia"]

    class Meta:
        model = Habilidade
        fields = "__all__"
        read_only_fields = ("personagem",)


class AprimoramentoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Aprimoramento
        fields = "__all__"
        read_only_fields = ("personagem", "habilidade")


class BonusSerializer(serializers.ModelSerializer):
    """
    Um bônus tem duas formas, escolhidas por `tipo_origem`:

      - `manual`   — o número é `valor`, digitado pelo jogador.
      - `entidade` — o número é o `valor_final` de outra entidade da MESMA
        ficha, indicada por `origem_tipo` + `origem_id`. É uma referência:
        subiu a Força, sobe todo bônus que a usa como origem, sem ninguém
        reabrir o painel. `valor` é ignorado nessa forma.

    `valor_efetivo` é o que o bônus vale AGORA (já resolvido), e é o número
    que o frontend exibe. `valor` continua existindo para o caso manual e
    para não perder o que o jogador tinha digitado caso ele volte atrás.
    """

    tipo = serializers.SerializerMethodField(read_only=True)
    alvo_nome = serializers.SerializerMethodField(read_only=True)

    # A origem entra e sai como par (tipo, id) — o cliente nunca precisa
    # conhecer ids de ContentType, do mesmo jeito que a URL de bônus usa
    # "/personagem/defesa/7/bonus/" e não o id do content type.
    origem_tipo = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, write_only=False
    )
    origem_id = serializers.IntegerField(required=False, allow_null=True)
    origem_nome = serializers.SerializerMethodField(read_only=True)
    valor_efetivo = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bonus
        fields = [
            "id",
            "content_type",
            "object_id",
            "tipo",
            "alvo_nome",
            "nome",
            "valor",
            "ativo",
            "somente_teste",
            "tipo_origem",
            "origem_tipo",
            "origem_id",
            "origem_nome",
            "valor_efetivo",
            "expira_em",
            "versao",
        ]
        read_only_fields = [
            "content_type",
            # AUDIT FIX: `object_id` já é atribuído pela view a partir da
            # URL (`bonus_lista`, via `serializer.save(object_id=object_id)`),
            # exatamente como `content_type`. Sem isso no read_only_fields,
            # todo POST para criar um Bonus falhava com
            # `{"object_id": ["This field is required."]}` a menos que o
            # cliente reenviasse manualmente o mesmo `object_id` já
            # presente na URL — e mesmo assim o valor enviado era
            # ignorado, porque os kwargs de `.save()` sempre sobrescrevem
            # `validated_data`. Bug confirmado rodando a API de verdade
            # (POST em `/personagem/status/<id>/bonus/` retornava 400).
            "object_id",
            "tipo",
            "alvo_nome",
            "origem_nome",
            "valor_efetivo",
            # Quem mexe no prazo é o endpoint "usar" (1 hora) ou o próprio
            # jogador ligando/desligando o bônus — nunca um PATCH solto, que
            # poderia inventar um prazo de um ano.
            "expira_em",
            "versao",
        ]

    # -- leitura ----------------------------------------------------------

    @extend_schema_field(serializers.CharField())
    def get_tipo(self, obj):
        return obj.content_type.model

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_alvo_nome(self, obj):
        if obj.alvo is None:
            return None

        if hasattr(obj.alvo, "nome"):
            return obj.alvo.nome

        return str(obj.alvo)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_origem_nome(self, obj):
        """Nome da entidade de origem, para o painel não precisar buscá-la."""
        if obj.tipo_origem != Bonus.TIPO_ENTIDADE or obj.origem is None:
            return None
        return getattr(obj.origem, "nome", str(obj.origem))

    @extend_schema_field(serializers.IntegerField())
    def get_valor_efetivo(self, obj):
        contexto = self.context.get("calculo")
        if contexto is None:
            raiz = self.root
            contexto = getattr(raiz, "_contexto_calculo", None)
            if contexto is None:
                contexto = calculos.ContextoCalculo()
                raiz._contexto_calculo = contexto
        return contexto.valor_bonus(obj)

    def to_representation(self, instance):
        dados = super().to_representation(instance)
        # `origem_tipo`/`origem_id` são virtuais: o model guarda
        # `origem_content_type`/`origem_object_id`.
        dados["origem_tipo"] = (
            instance.origem_content_type.model if instance.origem_content_type_id else None
        )
        dados["origem_id"] = instance.origem_object_id
        return dados

    # -- escrita ----------------------------------------------------------

    def validate(self, attrs):
        """
        Três regras, nesta ordem (a seguinte só faz sentido se a anterior
        passou):

        1. Bônus por entidade precisa de uma origem que exista.
        2. A origem tem de ser do MESMO personagem que o alvo. Sem isto um
           jogador leria o `valor_final` da ficha de outro — e
           `check_object_permission` não pegaria, porque o ALVO é dele.
        3. A aresta nova não pode fechar um ciclo (Força → Defesa →
           Atletismo → Força), que deixaria o cálculo sem ponto fixo.
        """
        instancia = self.instance

        # Desligar à mão apaga o prazo. `expira_em` só existe para o bônus
        # que o botão "Usar" acendeu por 1 hora; com o bônus desligado ele
        # não significa mais nada, e deixá-lo gravado faria a ficha seguir
        # exibindo uma contagem regressiva para algo que já está apagado.
        # `expira_em` é read-only na escrita (quem o define é o "Usar"), por
        # isso ele entra aqui e não vem do payload.
        if attrs.get("ativo") is False:
            attrs["expira_em"] = None

        tipo_origem = attrs.get(
            "tipo_origem",
            instancia.tipo_origem if instancia else Bonus.TIPO_MANUAL,
        )

        origem_tipo = attrs.pop("origem_tipo", serializers.empty)
        origem_id = attrs.pop("origem_id", serializers.empty)

        if origem_tipo is serializers.empty and instancia is not None:
            origem_tipo = (
                instancia.origem_content_type.model
                if instancia.origem_content_type_id
                else None
            )
        if origem_id is serializers.empty and instancia is not None:
            origem_id = instancia.origem_object_id

        origem_tipo = None if origem_tipo is serializers.empty else origem_tipo
        origem_id = None if origem_id is serializers.empty else origem_id

        if tipo_origem != Bonus.TIPO_ENTIDADE:
            # Voltar para manual limpa a referência: um bônus manual com
            # origem pendurada confundiria a limpeza e o grafo de ciclos.
            attrs["origem_content_type"] = None
            attrs["origem_object_id"] = None
            return attrs

        if not origem_tipo or origem_id is None:
            raise serializers.ValidationError(
                {"origem_id": ["Escolha a entidade que serve de origem do bônus."]}
            )

        modelo = calculos.modelo_base(origem_tipo)
        if modelo is None:
            raise serializers.ValidationError(
                {"origem_tipo": [f"Tipo de origem inválido: {origem_tipo}."]}
            )

        origem = modelo.objects.filter(pk=origem_id).first()
        if origem is None:
            raise serializers.ValidationError(
                {"origem_id": ["A entidade escolhida como origem não existe."]}
            )

        alvo = self._alvo(attrs)
        if alvo is not None:
            if calculos.personagem_de(origem) != calculos.personagem_de(alvo):
                raise serializers.ValidationError(
                    {"origem_id": ["A origem do bônus precisa ser do mesmo personagem."]}
                )

            alvo_tipo, alvo_id = calculos.chave_de(alvo)
            origem_base = calculos.chave_de(origem)

            if origem_base == (alvo_tipo, alvo_id):
                raise serializers.ValidationError(
                    {"origem_id": ["Uma entidade não pode ser origem de bônus dela mesma."]}
                )

            rota = calculos.rota_ate(*origem_base, alvo_tipo, alvo_id)
            if rota is not None:
                raise serializers.ValidationError(
                    {
                        "origem_id": [
                            "Este bônus criaria uma dependência circular: "
                            f"{calculos.descrever_rota([(alvo_tipo, alvo_id), *rota])}."
                        ]
                    }
                )

        # `modelo` já é o model BASE da cadeia de herança (foi assim que
        # buscamos a origem), então a referência nasce normalizada — uma arma
        # é gravada como `item`, uma habilidade como `poder`.
        attrs["origem_content_type"] = ContentType.objects.get_for_model(modelo)
        attrs["origem_object_id"] = origem.pk
        return attrs

    def _alvo(self, attrs):
        """
        O objeto que RECEBE o bônus. Na criação ele ainda não está em
        `attrs` (a view o passa em `.save(...)`), então a view o adianta em
        `context["alvo"]`; na edição, vem da própria instância.
        """
        if self.instance is not None:
            return self.instance.alvo
        return self.context.get("alvo")
