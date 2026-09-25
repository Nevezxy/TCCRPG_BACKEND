"""
Testes do ciclo de vida das imagens: upload, enquadramento, substituição,
remoção e exclusão — com o Cloudinary 100% mockado (nenhuma chamada real).

As garantias que importam aqui são as de SEGURANÇA da limpeza:
  - a imagem antiga só é apagada DEPOIS do commit da troca;
  - se o save falhar depois do upload, o arquivo NOVO é desfeito e o antigo
    fica intacto;
  - um arquivo ainda referenciado em outro lugar (ex.: a URL colada num
    objeto do Canva) nunca é apagado;
  - com o interruptor desligado, nada é apagado — só enfileirado.
"""

import json
from io import StringIO
from unittest.mock import patch

from cloudinary import CloudinaryResource
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from Campanha.models import NPC, Campanha, Canva, Local
from Campanha.serializers import NPCSerializer
from Personagem.models import Arma, Personagem
from Usuario.models import Usuario

from .models import AjusteImagem, ExclusaoImagemPendente
from .services import referencias_ativas, sanitizar_ajuste

ANTIGA = "tccrpg/campanha/npc/foto/antiga"
ANTIGA_DB = f"image/upload/v1/{ANTIGA}.jpg"

IMAGENS_TESTE = {
    **settings.IMAGENS,
    "PASTA_RAIZ": "tccrpg",
    "EXCLUSAO_ATIVA": True,
    "PROCESSAMENTO_SINCRONO": True,
}


def recurso(public_id):
    return CloudinaryResource(public_id, version="2", format="webp", type="upload", resource_type="image")


def arquivo(nome="nova.webp", tipo="image/webp"):
    return SimpleUploadedFile(nome, b"conteudo-de-imagem", content_type=tipo)


def apagado(public_ids):
    """Resposta do `delete_resources` para o mock."""
    return {"deleted": {p: "deleted" for p in public_ids}}


@override_settings(IMAGENS=IMAGENS_TESTE)
class BaseMidia(APITestCase):
    def setUp(self):
        self.mestre = Usuario.objects.create_user(username="mestre", password="SenhaForte123!")
        self.campanha = Campanha.objects.create(mestre=self.mestre, nome="Campanha")
        self.campanha.jogadores.add(self.mestre)
        self.npc = NPC.objects.create(campanha=self.campanha, nome="Arkan", foto=ANTIGA_DB)
        self.client.force_authenticate(user=self.mestre)

        self.upload = patch("cloudinary.uploader.upload_resource").start()
        self.delete = patch("cloudinary.api.delete_resources").start()
        self.destroy = patch("cloudinary.uploader.destroy").start()
        self.delete.side_effect = lambda ids, **kw: apagado(ids)
        self.addCleanup(patch.stopall)

    def url_npc(self):
        return f"/campanha/npcs/{self.npc.id}/"


class SubstituicaoTests(BaseMidia):
    def test_troca_apaga_a_antiga_so_depois_do_commit(self):
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with self.captureOnCommitCallbacks() as callbacks:
            resposta = self.client.patch(self.url_npc(), {"foto": arquivo()}, format="multipart")

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("tccrpg/campanha/npc/foto/nova", resposta.data["foto"])
        # Antes do commit: enfileirada, mas NADA apagado ainda.
        self.delete.assert_not_called()
        self.assertTrue(ExclusaoImagemPendente.objects.filter(public_id=ANTIGA, motivo="substituida").exists())

        for callback in callbacks:
            callback()

        self.delete.assert_called_once()
        self.assertEqual(self.delete.call_args.args[0], [ANTIGA])
        self.assertFalse(ExclusaoImagemPendente.objects.exists())

    def test_upload_usa_pasta_do_contexto_e_formatos_seguros(self):
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(self.url_npc(), {"foto": arquivo()}, format="multipart")

        opcoes = self.upload.call_args.kwargs
        self.assertEqual(opcoes["folder"], "tccrpg/campanha/npc/foto")
        self.assertNotIn("svg", opcoes["allowed_formats"])
        self.assertEqual(opcoes["transformation"][0]["crop"], "limit")

    def test_save_com_erro_desfaz_o_upload_novo_e_mantem_a_antiga(self):
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with patch("Midia.serializers.gravar_ajuste", side_effect=RuntimeError("banco caiu")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    self.client.patch(
                        self.url_npc(),
                        {"foto": arquivo(), "foto_ajuste": json.dumps({"modo": "cobrir"})},
                        format="multipart",
                    )

        self.destroy.assert_called_once()
        self.assertEqual(self.destroy.call_args.args[0], "tccrpg/campanha/npc/foto/nova")
        self.npc.refresh_from_db()
        self.assertEqual(self.npc.foto.public_id, ANTIGA)
        self.delete.assert_not_called()
        self.assertFalse(ExclusaoImagemPendente.objects.exists())

    def test_arquivo_ainda_usado_no_canva_nao_e_apagado(self):
        # O CanvaImagemModal grava a URL de uma imagem dentro do `dados`.
        Canva.objects.create(
            campanha=self.campanha,
            nome="Quadro",
            dados={"objetos": [{"tipo": "imagem", "conteudo": f"https://res.cloudinary.com/demo/{ANTIGA_DB}"}]},
        )
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(self.url_npc(), {"foto": arquivo()}, format="multipart")

        self.delete.assert_not_called()
        self.assertFalse(ExclusaoImagemPendente.objects.exists())

    def test_referencia_exata_nao_confunde_prefixo(self):
        # "antiga" não pode proteger "antiga-2" (e vice-versa).
        NPC.objects.create(campanha=self.campanha, nome="Outro", foto=f"image/upload/v1/{ANTIGA}-2.jpg")
        self.assertEqual(referencias_ativas({f"{ANTIGA}-x"}), set())
        self.assertEqual(referencias_ativas({ANTIGA}), {ANTIGA})

    @override_settings(IMAGENS={**IMAGENS_TESTE, "EXCLUSAO_ATIVA": False})
    def test_interruptor_desligado_so_enfileira(self):
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(self.url_npc(), {"foto": arquivo()}, format="multipart")

        self.delete.assert_not_called()
        self.assertTrue(ExclusaoImagemPendente.objects.filter(public_id=ANTIGA).exists())

    def test_heranca_multitabela_arma(self):
        dono = Personagem.objects.create(usuario=self.mestre, nome="Herói")
        arma = Arma.objects.create(personagem=dono, nome="Espada", foto="image/upload/v1/tccrpg/arma-antiga.jpg")
        self.upload.return_value = recurso("tccrpg/personagem/item/foto/nova")

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(f"/personagem/armas/{arma.id}/", {"foto": arquivo()}, format="multipart")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(self.delete.call_args.args[0], ["tccrpg/arma-antiga"])

    def test_fundo_da_ficha_usa_o_mesmo_pipeline(self):
        # `Personagem.fundo` não tem código próprio: estar em `media_fields`
        # tem de bastar para o upload e a limpeza do arquivo antigo.
        dono = Personagem.objects.create(usuario=self.mestre, nome="Herói", fundo="image/upload/v1/tccrpg/fundo-antigo.jpg")
        self.upload.return_value = recurso("tccrpg/personagem/personagem/fundo/novo")

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(f"/personagem/{dono.id}/", {"fundo": arquivo()}, format="multipart")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertIn("fundo/novo", resposta.data["fundo"])
        self.assertEqual(self.delete.call_args.args[0], ["tccrpg/fundo-antigo"])


class RemocaoEExclusaoTests(BaseMidia):
    def test_remover_imagem_com_null(self):
        AjusteImagem.objects.create(
            content_type_id=self._ct_npc(), object_id=self.npc.id, campo="foto", dados={"modo": "cobrir"}
        )

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(self.url_npc(), {"foto": None}, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertIsNone(resposta.data["foto"])
        self.assertIsNone(resposta.data["foto_ajuste"])
        self.assertEqual(self.delete.call_args.args[0], [ANTIGA])
        self.assertFalse(AjusteImagem.objects.exists())

    def test_remover_em_coluna_sem_null_grava_vazio(self):
        # Personagem.foto é blank=True sem null=True.
        personagem = Personagem.objects.create(
            usuario=self.mestre, nome="Herói", foto="image/upload/v1/tccrpg/personagem-antiga.jpg"
        )

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(f"/personagem/{personagem.id}/", {"foto": None}, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        personagem.refresh_from_db()
        self.assertFalse(personagem.foto)
        self.assertEqual(self.delete.call_args.args[0], ["tccrpg/personagem-antiga"])

    def test_excluir_campanha_em_cascata_apaga_todas_as_imagens(self):
        Local.objects.create(campanha=self.campanha, nome="Vila", imagem="image/upload/v1/tccrpg/local.jpg")
        Canva.objects.create(campanha=self.campanha, nome="Quadro", imagem="image/upload/v1/tccrpg/capa.jpg")
        Campanha.objects.filter(pk=self.campanha.pk).update(banner="image/upload/v1/tccrpg/banner.jpg")
        self.campanha.refresh_from_db()

        with self.captureOnCommitCallbacks(execute=True):
            self.campanha.delete()

        apagados = {p for chamada in self.delete.call_args_list for p in chamada.args[0]}
        self.assertEqual(apagados, {ANTIGA, "tccrpg/local", "tccrpg/capa", "tccrpg/banner"})
        self.assertFalse(ExclusaoImagemPendente.objects.exists())

    def _ct_npc(self):
        from django.contrib.contenttypes.models import ContentType

        return ContentType.objects.get_for_model(NPC).id


class AjusteTests(BaseMidia):
    def test_so_ajuste_nao_reenvia_imagem_e_e_sanitizado(self):
        ajuste = {"modo": "conter", "escala": 99, "offsetX": -3, "offsetY": 0.25, "ar": 1.5, "lixo": "<script>"}

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(self.url_npc(), {"foto_ajuste": ajuste}, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.upload.assert_not_called()
        self.delete.assert_not_called()
        self.assertEqual(
            resposta.data["foto_ajuste"], {"modo": "conter", "escala": 4.0, "offsetX": -1.0, "offsetY": 0.25, "ar": 1.5}
        )
        self.assertEqual(self.client.get(self.url_npc()).data["foto_ajuste"]["modo"], "conter")

    def test_upload_com_ajuste_em_string_json_no_multipart(self):
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")
        ajuste = {"modo": "cobrir", "escala": 1.5, "offsetX": 0.2, "offsetY": -0.1, "ar": 0.75}

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(
                self.url_npc(), {"foto": arquivo(), "foto_ajuste": json.dumps(ajuste)}, format="multipart"
            )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["foto_ajuste"]["escala"], 1.5)

    def test_trocar_imagem_sem_ajuste_descarta_o_enquadramento_antigo(self):
        self.client.patch(self.url_npc(), {"foto_ajuste": {"modo": "conter"}}, format="json")
        self.upload.return_value = recurso("tccrpg/campanha/npc/foto/nova")

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(self.url_npc(), {"foto": arquivo()}, format="multipart")

        self.assertIsNone(resposta.data["foto_ajuste"])
        self.assertFalse(AjusteImagem.objects.exists())

    def test_leitura_em_lote_faz_uma_consulta_so(self):
        npcs = [NPC.objects.create(campanha=self.campanha, nome=f"N{i}", foto=ANTIGA_DB) for i in range(6)]
        for npc in npcs:
            self.client.patch(f"/campanha/npcs/{npc.id}/", {"foto_ajuste": {"escala": 2}}, format="json")

        with CaptureQueriesContext(connection) as consultas:
            dados = NPCSerializer(NPC.objects.filter(campanha=self.campanha), many=True).data

        self.assertTrue(all(d["foto_ajuste"] and d["foto_ajuste"]["escala"] == 2.0 for d in dados if d["nome"] != "Arkan"))
        no_ajuste = [q for q in consultas.captured_queries if "midia_ajusteimagem" in q["sql"].lower()]
        self.assertEqual(len(no_ajuste), 1)

    def test_sanitizar_ajuste(self):
        self.assertIsNone(sanitizar_ajuste(None))
        self.assertIsNone(sanitizar_ajuste("null"))
        self.assertEqual(sanitizar_ajuste("{}")["modo"], "cobrir")
        with self.assertRaises(ValueError):
            sanitizar_ajuste("{nao-e-json")
        with self.assertRaises(ValueError):
            sanitizar_ajuste([1, 2])
        # Booleano não é número; `ar` absurdo é descartado.
        self.assertEqual(sanitizar_ajuste({"escala": True, "ar": 1e9}), {"modo": "cobrir", "escala": 1.0, "offsetX": 0.0, "offsetY": 0.0})


class ValidacaoTests(BaseMidia):
    def test_url_em_texto_e_recusada(self):
        resposta = self.client.patch(self.url_npc(), {"foto": "https://exemplo.com/x.jpg"}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("foto", resposta.data)

    def test_reenviar_a_propria_url_atual_nao_muda_nada(self):
        atual = self.client.get(self.url_npc()).data["foto"]

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.patch(self.url_npc(), {"foto": atual, "nome": "Arkan II"}, format="json")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.npc.refresh_from_db()
        self.assertEqual(self.npc.foto.public_id, ANTIGA)
        self.delete.assert_not_called()

    def test_svg_e_recusado_sem_gastar_upload(self):
        resposta = self.client.patch(
            self.url_npc(), {"foto": arquivo("x.svg", "image/svg+xml")}, format="multipart"
        )
        self.assertEqual(resposta.status_code, 400)
        self.upload.assert_not_called()

    def test_ajuste_malformado_e_recusado(self):
        resposta = self.client.patch(self.url_npc(), {"foto_ajuste": "{quebrado"}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("foto_ajuste", resposta.data)


class ComandoLimparImagensTests(BaseMidia):
    def _recursos(self, **kwargs):
        antigo = "2020-01-01T00:00:00Z"
        agora = timezone.now().isoformat()
        todos = [
            {"public_id": ANTIGA, "created_at": antigo, "bytes": 1000},  # referenciado pelo NPC
            {"public_id": "tccrpg/orfa-velha", "created_at": antigo, "bytes": 2000},
            {"public_id": "tccrpg/orfa-recente", "created_at": agora, "bytes": 3000},  # upload em andamento?
            {"public_id": "raiz-legada", "created_at": antigo, "bytes": 4000},
            {"public_id": "outro-projeto/foto", "created_at": antigo, "bytes": 5000},
        ]
        prefixo = kwargs.get("prefix")
        return {"resources": [r for r in todos if not prefixo or r["public_id"].startswith(prefixo)]}

    def test_orfaos_dry_run_nao_apaga(self):
        with patch("cloudinary.api.resources", side_effect=self._recursos):
            saida = StringIO()
            call_command("limpar_imagens", "--orfaos", stdout=saida)

        self.delete.assert_not_called()
        self.assertIn("tccrpg/orfa-velha", saida.getvalue())
        self.assertNotIn("orfa-recente", saida.getvalue())
        self.assertNotIn("raiz-legada", saida.getvalue())

    def test_orfaos_apply_so_apaga_orfaos_do_escopo(self):
        with patch("cloudinary.api.resources", side_effect=self._recursos):
            call_command("limpar_imagens", "--orfaos", "--incluir-raiz", "--apply", stdout=StringIO())

        apagados = set(self.delete.call_args.args[0])
        self.assertEqual(apagados, {"tccrpg/orfa-velha", "raiz-legada"})

    def test_pendentes_apply_drena_a_fila(self):
        ExclusaoImagemPendente.objects.create(public_id="tccrpg/pendente", motivo="substituida")

        call_command("limpar_imagens", "--pendentes", stdout=StringIO())
        self.delete.assert_not_called()

        call_command("limpar_imagens", "--pendentes", "--apply", stdout=StringIO())
        self.assertEqual(self.delete.call_args.args[0], ["tccrpg/pendente"])
        self.assertFalse(ExclusaoImagemPendente.objects.exists())
