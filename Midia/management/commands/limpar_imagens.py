"""
Manutenção dos arquivos de imagem no Cloudinary.

    python manage.py limpar_imagens --pendentes [--apply]
    python manage.py limpar_imagens --orfaos [--incluir-raiz] [--idade-horas N] [--apply]

SEM `--apply` nada é apagado: o comando só lista o que faria (dry-run).

--pendentes  Termina a fila de exclusões (`ExclusaoImagemPendente`) — o que
             ficou para trás por falha de rede, processo reiniciado ou
             `IMAGENS["EXCLUSAO_ATIVA"]` desligado.

--orfaos     Compara os arquivos que EXISTEM no Cloudinary com os que o
             BANCO referencia e lista os que sobram. Escopo, do mais seguro
             ao mais amplo:
               - por padrão, só a pasta `IMAGENS["PASTA_RAIZ"]/`;
               - `--incluir-raiz` soma os arquivos soltos na raiz da conta
                 (os uploads antigos, anteriores à pasta padronizada).
             Arquivos de OUTRAS pastas nunca entram. Arquivos mais novos que
             `--idade-horas` também não (um upload em andamento ainda não
             chegou ao banco e pareceria órfão).

ATENÇÃO: rode `--orfaos --apply` só contra o banco que é DONO do Cloudinary
(produção). Contra uma cópia local desatualizada, arquivos que a produção
usa pareceriam órfãos.
"""

from datetime import datetime, timedelta

import cloudinary.api
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import TextField
from django.db.models.functions import Cast
from django.utils import timezone

from Midia.models import ExclusaoImagemPendente
from Midia.services import (
    apagar_no_cloudinary,
    campos_de_texto,
    colunas_cloudinary,
    config,
    processar_fila,
    public_id_de,
    referencias_ativas,
)


class Command(BaseCommand):
    help = "Termina a fila de exclusões de imagem ou lista/apaga arquivos órfãos no Cloudinary (dry-run por padrão)."

    def add_arguments(self, parser):
        modo = parser.add_mutually_exclusive_group(required=True)
        modo.add_argument("--pendentes", action="store_true", help="Processa a fila de exclusões pendentes.")
        modo.add_argument("--orfaos", action="store_true", help="Procura arquivos sem referência no banco.")
        parser.add_argument("--apply", action="store_true", help="Apaga de fato (sem isto, só lista).")
        parser.add_argument(
            "--incluir-raiz", action="store_true", help="Inclui os arquivos soltos na raiz da conta (uploads antigos)."
        )
        parser.add_argument("--idade-horas", type=int, default=None, help="Ignora arquivos mais novos que isto.")

    def handle(self, *args, **opcoes):
        if settings.DEBUG and opcoes["apply"]:
            self.stderr.write(
                self.style.WARNING(
                    "DEBUG está ligado: confira se este banco é mesmo o dono do Cloudinary antes de apagar."
                )
            )
        if opcoes["pendentes"]:
            self._pendentes(opcoes["apply"])
        else:
            self._orfaos(opcoes["apply"], opcoes["incluir_raiz"], opcoes["idade_horas"])

    # -- fila ---------------------------------------------------------------

    def _pendentes(self, aplicar):
        pendentes = ExclusaoImagemPendente.objects.order_by("id")
        total = pendentes.count()
        self.stdout.write(f"{total} exclusão(ões) pendente(s).")
        for p in pendentes[:50]:
            erro = f" — {p.tentativas} tentativa(s), último erro: {p.ultimo_erro}" if p.tentativas else ""
            self.stdout.write(f"  {p.public_id} ({p.motivo}){erro}")

        if not aplicar:
            self.stdout.write(self.style.NOTICE("Dry-run: nada foi apagado. Use --apply para processar."))
            return

        resumo = {"apagadas": 0, "em_uso": 0, "falhas": 0}
        while True:
            parcial = processar_fila()
            for chave in resumo:
                resumo[chave] += parcial[chave]
            # Para quando não houve progresso — só sobraram falhas, que
            # continuariam falhando neste mesmo loop.
            if parcial["apagadas"] + parcial["em_uso"] == 0:
                break
        self.stdout.write(self.style.SUCCESS(
            f"Apagadas: {resumo['apagadas']} · mantidas por ainda estarem em uso: {resumo['em_uso']} · "
            f"falhas: {ExclusaoImagemPendente.objects.count()}"
        ))

    # -- órfãos -------------------------------------------------------------

    def _orfaos(self, aplicar, incluir_raiz, idade_horas):
        cfg = config()
        raiz = cfg["PASTA_RAIZ"].strip("/")
        idade = timedelta(hours=idade_horas if idade_horas is not None else cfg["IDADE_MINIMA_ORFAO_HORAS"])
        limite_data = timezone.now() - idade

        referenciados = self._referenciados()
        textos = self._textos()

        candidatos = {}
        for recurso in self._listar(prefixo=f"{raiz}/"):
            candidatos[recurso["public_id"]] = recurso
        if incluir_raiz:
            for recurso in self._listar(prefixo=None):
                if "/" not in recurso["public_id"]:
                    candidatos[recurso["public_id"]] = recurso

        orfaos = []
        for public_id, recurso in sorted(candidatos.items()):
            if public_id in referenciados or any(public_id in t for t in textos):
                continue
            criado = _data(recurso.get("created_at"))
            if criado and criado > limite_data:
                continue
            orfaos.append(recurso)

        total_bytes = sum(r.get("bytes", 0) for r in orfaos)
        self.stdout.write(
            f"{len(candidatos)} arquivo(s) no escopo · {len(orfaos)} órfão(s) · "
            f"{total_bytes / (1024 * 1024):.1f} MB recuperáveis."
        )
        for r in orfaos:
            self.stdout.write(f"  {r['public_id']}  {r.get('created_at', '?')}  {r.get('bytes', 0) / 1024:.0f} KB")

        if not aplicar:
            self.stdout.write(self.style.NOTICE("Dry-run: nada foi apagado. Use --apply para apagar a lista acima."))
            return

        ids = [r["public_id"] for r in orfaos]
        # Rechecagem final — algo pode ter passado a usar um deles enquanto a
        # listagem (paginada, lenta) acontecia.
        em_uso = referencias_ativas(ids)
        apagadas, falhas = apagar_no_cloudinary([p for p in ids if p not in em_uso])
        self.stdout.write(self.style.SUCCESS(f"Apagadas: {len(apagadas)} · falhas: {len(falhas)}"))
        for public_id, erro in falhas.items():
            self.stderr.write(f"  falhou {public_id}: {erro}")

    def _referenciados(self):
        referenciados = set()
        for model, campo in colunas_cloudinary():
            for valor in model._base_manager.values_list(campo.name, flat=True):
                public_id = public_id_de(valor)
                if public_id:
                    referenciados.add(public_id)
        return referenciados

    def _textos(self):
        textos = []
        for model, campo in campos_de_texto():
            textos.extend(
                t
                for t in model._base_manager.annotate(_midia_txt=Cast(campo.name, TextField())).values_list(
                    "_midia_txt", flat=True
                )
                if t and "cloudinary" in t
            )
        return textos

    def _listar(self, prefixo):
        cursor = None
        while True:
            parametros = {"type": "upload", "resource_type": "image", "max_results": 500}
            if prefixo:
                parametros["prefix"] = prefixo
            if cursor:
                parametros["next_cursor"] = cursor
            resposta = cloudinary.api.resources(**parametros)
            yield from resposta.get("resources", [])
            cursor = resposta.get("next_cursor")
            if not cursor:
                break


def _data(texto):
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
