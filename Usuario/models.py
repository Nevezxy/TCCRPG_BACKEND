from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField

# Quantos links sociais o perfil aceita. O limite existe para o cabeçalho do
# perfil não virar uma parede de pílulas no celular — e para um PATCH não
# conseguir gravar uma lista arbitrariamente grande num JSONField.
MAX_LINKS_SOCIAIS = 6


def validar_links_sociais(valor):
    """
    `links_sociais` é uma lista de `{"rotulo": str, "url": str}`.

    Só `http://` e `https://` passam: o frontend renderiza cada `url` como
    `<a href>`, e aceitar `javascript:` ou `data:` aqui seria um XSS
    guardado no perfil de alguém, disparado no clique de qualquer visitante.
    """
    if not isinstance(valor, list):
        raise ValidationError("Envie uma lista de links.")
    if len(valor) > MAX_LINKS_SOCIAIS:
        raise ValidationError(f"No máximo {MAX_LINKS_SOCIAIS} links.")
    for link in valor:
        if not isinstance(link, dict):
            raise ValidationError("Cada link precisa ter `rotulo` e `url`.")
        rotulo = link.get("rotulo")
        url = link.get("url")
        if not isinstance(rotulo, str) or not rotulo.strip() or len(rotulo) > 40:
            raise ValidationError("Cada link precisa de um rótulo de até 40 caracteres.")
        if not isinstance(url, str) or len(url) > 300 or not url.lower().startswith(("http://", "https://")):
            raise ValidationError("A URL de cada link precisa começar com http:// ou https://.")
        if set(link) - {"rotulo", "url"}:
            raise ValidationError("Cada link aceita só `rotulo` e `url`.")


class Usuario(AbstractUser):
    foto = CloudinaryField('Foto', blank=True)
    banner = CloudinaryField('Banner', blank=True)
    descricao = models.TextField(blank=True, default="", max_length=1000)
    # Cor de identificação do perfil (anel do avatar, fundo do banner vazio).
    # É CONTEÚDO do usuário, como a cor própria de uma entidade do mundo —
    # não entra no tema do app, que continua sendo decidido por quem olha.
    cor_perfil = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use uma cor no formato #RRGGBB.")],
    )
    links_sociais = models.JSONField(default=list, blank=True, validators=[validar_links_sociais])
    # `null=True` porque as linhas que já existem não têm como saber quando
    # foram alteradas pela última vez; `auto_now` preenche a partir do
    # próximo save.
    data_atualizacao = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.username
