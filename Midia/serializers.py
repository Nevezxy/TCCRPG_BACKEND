"""
`CloudinaryUrlSerializerMixin` — a porta de entrada das imagens na API.

Já estava em TODO serializer com imagem (Personagem e Campanha), por isso é
aqui que o enquadramento e o upload seguro entram, sem tocar em nenhum
serializer de entidade. Tudo é ADITIVO — um cliente que não conhece as
chaves novas continua funcionando igual:

  Leitura
    `<campo>`          URL do Cloudinary (como antes) ou null.
    `<campo>_ajuste`   enquadramento salvo (`modo`, `escala`, `offsetX`,
                       `offsetY`, `ar`) ou null.

  Escrita
    `<campo>`          arquivo (multipart) → upload; null ou "" → remove a
                       imagem. Uma URL em texto é recusada (o antigo "Colar
                       URL" gravava lixo no campo), exceto se for o próprio
                       valor atual — aí é só ignorada.
    `<campo>_ajuste`   objeto (JSON) ou string JSON (multipart) → grava o
                       enquadramento sem reenviar a imagem; null → apaga.
"""

from cloudinary.exceptions import Error as CloudinaryError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from rest_framework import serializers

from .services import (
    apagar_ajuste,
    descartar_uploads,
    enviar_imagem,
    gravar_ajuste,
    ler_ajustes,
    sanitizar_ajuste,
    url_de,
    validar_arquivo,
)

_CHAVE_CACHE = "_midia_cache_ajustes"


def ajustes_do_objeto(serializer, instance, campos):
    """
    `{campo: dados}` do objeto, carregando em LOTE quando ele faz parte de
    uma listagem (`many=True`): na primeira chamada, busca os ajustes de
    todos os objetos da lista numa consulta só e guarda no `context` —
    as demais chamadas da mesma lista não vão ao banco. Sem isso, listar 200
    NPCs custaria 200 consultas extras.
    """
    contexto = serializer.context if isinstance(serializer.context, dict) else {}
    cache = contexto.setdefault(_CHAVE_CACHE, {})
    model = type(instance)
    chave = (model, instance.pk)

    if chave not in cache:
        lote = [instance]
        pai = getattr(serializer, "parent", None)
        if isinstance(pai, serializers.ListSerializer) and pai.instance is not None:
            try:
                # A ListSerializer já avaliou o queryset para iterar, então
                # isto lê o cache dele — nenhuma consulta nova.
                lote = [o for o in pai.instance if isinstance(o, model)] or [instance]
            except TypeError:
                lote = [instance]
        pks = {o.pk for o in lote if (model, o.pk) not in cache}
        pks.add(instance.pk)
        lidos = ler_ajustes(model, pks, campos)
        for pk in pks:
            cache[(model, pk)] = lidos.get(pk, {})

    return cache[chave]


class CloudinaryUrlSerializerMixin:
    media_fields = []

    # -- campos -------------------------------------------------------------

    def get_fields(self):
        fields = super().get_fields()
        for campo in self.media_fields:
            campo_serializer = fields.get(campo)
            if campo_serializer is not None and not campo_serializer.read_only:
                # "Remover imagem" = mandar null, inclusive onde a coluna não
                # aceita NULL (Personagem.foto) — lá o valor gravado vira "".
                campo_serializer.allow_null = True
                campo_serializer.required = False
        return fields

    # -- leitura ------------------------------------------------------------

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.media_fields:
            return data

        ajustes = ajustes_do_objeto(self, instance, self.media_fields)
        for campo in self.media_fields:
            url = url_de(getattr(instance, campo, None))
            data[campo] = url
            data[f"{campo}_ajuste"] = ajustes.get(campo) if url else None
        return data

    # -- validação ----------------------------------------------------------

    def to_internal_value(self, data):
        valores = super().to_internal_value(data)
        erros = {}
        ajustes = {}

        for campo in self.media_fields:
            if campo in data:
                bruto = data.get(campo)
                if isinstance(bruto, UploadedFile):
                    try:
                        validar_arquivo(bruto)
                    except ValueError as exc:
                        erros[campo] = [str(exc)]
                elif isinstance(bruto, str) and bruto.strip():
                    atual = getattr(self.instance, campo, None) if self.instance is not None else None
                    if atual and bruto.strip() in (url_de(atual), atual.public_id):
                        # Reenvio do próprio valor atual (ex.: um formulário
                        # que manda tudo): não é troca, não mexe em nada.
                        valores.pop(campo, None)
                    else:
                        erros[campo] = ["Envie um arquivo de imagem — endereços (URLs) não são aceitos."]

            chave = f"{campo}_ajuste"
            if chave in data:
                try:
                    ajustes[campo] = sanitizar_ajuste(data.get(chave))
                except ValueError as exc:
                    erros[chave] = [str(exc)]

        if erros:
            raise serializers.ValidationError(erros)

        self._midia_ajustes = ajustes
        return valores

    # -- escrita ------------------------------------------------------------

    def create(self, validated_data):
        enviados = self._preparar_imagens(validated_data)
        try:
            with transaction.atomic():
                instance = super().create(validated_data)
                self._gravar_ajustes(instance)
        except Exception:
            descartar_uploads(enviados)
            raise
        return instance

    def update(self, instance, validated_data):
        enviados = self._preparar_imagens(validated_data)
        try:
            with transaction.atomic():
                instance = super().update(instance, validated_data)
                self._gravar_ajustes(instance)
        except Exception:
            # O arquivo novo já está no Cloudinary mas o banco não o
            # referencia: sem isto, ele viraria órfão. A imagem ANTIGA fica
            # intacta — a fila de exclusão dela foi desfeita no rollback.
            descartar_uploads(enviados)
            raise
        return instance

    def _preparar_imagens(self, validated_data):
        """
        Faz o upload dos arquivos novos ANTES do save (em vez de deixar para o
        `CloudinaryField.pre_save`), para conhecer os `public_id`s e poder
        desfazê-los. Normaliza a remoção para o vazio que a coluna aceita.
        """
        model = self.Meta.model
        enviados = []
        try:
            for campo in self.media_fields:
                if campo not in validated_data:
                    continue
                valor = validated_data[campo]
                if isinstance(valor, UploadedFile):
                    try:
                        recurso = enviar_imagem(valor, model, campo)
                    except CloudinaryError as exc:
                        raise serializers.ValidationError(
                            {campo: [f"Não foi possível processar a imagem: {exc}"]}
                        ) from exc
                    validated_data[campo] = recurso
                    enviados.append(recurso.public_id)
                elif not valor:
                    validated_data[campo] = None if model._meta.get_field(campo).null else ""
        except Exception:
            # Divindade envia foto e símbolo juntos: se o segundo falhar, o
            # primeiro não pode ficar solto no Cloudinary.
            descartar_uploads(enviados)
            raise
        return enviados

    def _gravar_ajustes(self, instance):
        ajustes = getattr(self, "_midia_ajustes", None) or {}
        for campo, dados in ajustes.items():
            if dados is None or not getattr(instance, campo, None):
                apagar_ajuste(instance, campo)
            else:
                gravar_ajuste(instance, campo, dados)
        if ajustes and isinstance(self.context, dict):
            # A resposta desta mesma requisição precisa ler o que acabou de
            # ser gravado, não o cache de antes.
            self.context.pop(_CHAVE_CACHE, None)
