from django.contrib.contenttypes.models import ContentType
from django.db import models


class AjusteImagem(models.Model):
    """
    Enquadramento (posição, zoom e modo) de UMA imagem de UM objeto,
    guardado separado do arquivo no Cloudinary.

    Por que uma tabela genérica em vez de um campo em cada model: são ~22
    `CloudinaryField` espalhados em três apps. Um JSONField ao lado de cada um
    exigiria mexer em todos esses models (e migrações em cascata); aqui é uma
    tabela só, lida/gravada pelo `CloudinaryUrlSerializerMixin`, que já está
    em todo serializer com imagem — nenhum model de entidade muda.

    `content_type` é o do model que DECLARA o campo (`field.model`), não o
    da instância: `Arma`/`Armadura` herdam `foto` de `Item` por herança
    multi-tabela e compartilham o mesmo pk, então a chave fica estável
    independente de por qual classe o objeto foi carregado.

    `dados` segue o mesmo formato do enquadramento do Canva no frontend
    (`modo`, `escala`, `offsetX`, `offsetY`, `ar`) — sempre validado por
    `services.sanitizar_ajuste` antes de gravar.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    campo = models.CharField(max_length=64)
    dados = models.JSONField(default=dict)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ajuste de imagem"
        verbose_name_plural = "Ajustes de imagem"
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "campo"],
                name="midia_ajuste_unico_por_campo",
            )
        ]
        indexes = [models.Index(fields=["content_type", "object_id"], name="midia_ajuste_objeto_idx")]

    def __str__(self):
        return f"{self.content_type.model}#{self.object_id}.{self.campo}"


class ExclusaoImagemPendente(models.Model):
    """
    Fila DURÁVEL de arquivos do Cloudinary que deixaram de ser usados.

    A linha é gravada na MESMA transação que troca ou exclui a imagem no
    banco. Isso garante a consistência nos dois sentidos:
      - se a transação falhar, a linha some junto (rollback) e nada é
        apagado — a imagem antiga continua referenciada e intacta;
      - se o commit acontecer mas a chamada ao Cloudinary falhar (rede,
        limite de API, processo reiniciado), a linha continua aqui e o
        comando `limpar_imagens --pendentes` termina o serviço depois.

    `public_id` é único: excluir em cascata um Personagem e seus itens, ou
    a mesma imagem ser enfileirada duas vezes (herança multi-tabela dispara
    o signal para a classe filha e para a mãe), não duplica o trabalho.
    """

    MOTIVOS = [
        ("substituida", "Substituída por outra imagem"),
        ("removida", "Removida pelo usuário"),
        ("excluida", "Objeto excluído"),
        ("upload_descartado", "Upload que não chegou ao banco"),
    ]

    public_id = models.CharField(max_length=255, unique=True)
    motivo = models.CharField(max_length=32, choices=MOTIVOS)
    criado_em = models.DateTimeField(auto_now_add=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    ultimo_erro = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Exclusão de imagem pendente"
        verbose_name_plural = "Exclusões de imagem pendentes"
        ordering = ["id"]

    def __str__(self):
        return self.public_id
