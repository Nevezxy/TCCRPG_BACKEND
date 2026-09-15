"""
Imagens na biblioteca do app Sistema.

O ciclo de vida das imagens em si (upload, troca, fila de exclusão) já é
coberto por `Midia/tests.py` — aqui o que importa é o que é específico
desta etapa:

  - os 5 models de biblioteca expõem a imagem e o enquadramento pela API,
    no mesmo formato de qualquer outra entidade com imagem;
  - a cópia biblioteca → ficha LEVA a imagem e o enquadramento junto;
  - e o arquivo compartilhado pelas duas linhas não é apagado quando uma
    delas some — a garantia de que a cópia por referência é segura.
"""

from unittest.mock import patch

from cloudinary import CloudinaryResource
from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from Midia.models import AjusteImagem, ExclusaoImagemPendente
from Midia.services import ler_ajustes
from Personagem.models import Arma, Armadura, Habilidade, Item, Personagem, Poder
from Sistema.models import (
    ArmaduraSistema,
    ArmaSistema,
    HabilidadeSistema,
    ItemSistema,
    PoderSistema,
    Sistema,
)
from Usuario.models import Usuario

IMAGENS_TESTE = {**settings.IMAGENS, "EXCLUSAO_ATIVA": True, "PROCESSAMENTO_SINCRONO": True}

FOTO = "tccrpg/sistema/itemsistema/foto/espada"
FOTO_DB = f"image/upload/v1/{FOTO}.webp"
AJUSTE = {"modo": "cobrir", "escala": 1.5, "offsetX": 0.2, "offsetY": -0.1}


def recurso(public_id):
    return CloudinaryResource(public_id, version="2", format="webp", type="upload", resource_type="image")


@override_settings(IMAGENS=IMAGENS_TESTE)
class BaseBiblioteca(APITestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(username="jogador", password="SenhaForte123!")
        self.client.force_authenticate(user=self.usuario)

        self.sistema = Sistema.objects.create(nome="Tormenta")
        self.personagem = Personagem.objects.create(usuario=self.usuario, nome="Arton")

        self.delete = patch("cloudinary.api.delete_resources").start()
        self.delete.side_effect = lambda ids, **kw: {"deleted": {p: "deleted" for p in ids}}
        self.addCleanup(patch.stopall)

    def com_ajuste(self, obj, campo="foto", dados=None):
        """Grava o enquadramento do objeto da biblioteca, como o admin faria."""
        from Midia.services import gravar_ajuste

        gravar_ajuste(obj, campo, dados or AJUSTE)
        return obj


class LeituraDaBibliotecaTests(BaseBiblioteca):

    def test_item_expoe_foto_e_enquadramento(self):
        item = self.com_ajuste(ItemSistema.objects.create(sistema=self.sistema, nome="Espada", foto=FOTO_DB))

        resposta = self.client.get(f"/sistema/{self.sistema.id}/itens/")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertIn(FOTO, resposta.data[0]["foto"])
        self.assertEqual(resposta.data[0]["foto_ajuste"], AJUSTE)
        # Recarregado do banco, o valor cru vira CloudinaryResource.
        item.refresh_from_db()
        self.assertEqual(item.foto.public_id, FOTO)

    def test_sem_imagem_devolve_nulo_nos_dois_campos(self):
        ItemSistema.objects.create(sistema=self.sistema, nome="Corda")

        resposta = self.client.get(f"/sistema/{self.sistema.id}/itens/")

        self.assertIsNone(resposta.data[0]["foto"])
        self.assertIsNone(resposta.data[0]["foto_ajuste"])

    def test_poder_e_habilidade_usam_midia(self):
        self.com_ajuste(
            PoderSistema.objects.create(sistema=self.sistema, nome="Bola de Fogo", midia=FOTO_DB), campo="midia"
        )
        HabilidadeSistema.objects.create(sistema=self.sistema, nome="Esquiva", midia=FOTO_DB)

        poderes = self.client.get(f"/sistema/{self.sistema.id}/poderes/")
        habilidades = self.client.get(f"/sistema/{self.sistema.id}/habilidades/")

        self.assertIn(FOTO, poderes.data[0]["midia"])
        self.assertEqual(poderes.data[0]["midia_ajuste"], AJUSTE)
        self.assertIn(FOTO, habilidades.data[0]["midia"])
        # Sem ajuste salvo, a chave existe e vem nula (o cliente cai no padrão do slot).
        self.assertIsNone(habilidades.data[0]["midia_ajuste"])


class CopiaParaFichaTests(BaseBiblioteca):
    """A cópia leva a imagem por REFERÊNCIA (mesmo public_id), não por upload."""

    def test_item_copiado_mantem_foto_e_enquadramento(self):
        item_sistema = self.com_ajuste(
            ItemSistema.objects.create(sistema=self.sistema, nome="Espada", foto=FOTO_DB)
        )

        resposta = self.client.post(
            f"/sistema/personagens/{self.personagem.id}/itens/{item_sistema.id}/copiar/", {}, format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get(pk=resposta.data["id"])
        self.assertEqual(item.foto.public_id, FOTO)
        self.assertEqual(ler_ajustes(Item, [item.pk], ["foto"])[item.pk]["foto"], AJUSTE)

    def test_arma_armadura_poder_e_habilidade_tambem_levam_a_imagem(self):
        arma_s = ArmaSistema.objects.create(sistema=self.sistema, nome="Machado", foto=FOTO_DB)
        armadura_s = ArmaduraSistema.objects.create(sistema=self.sistema, nome="Cota", foto=FOTO_DB)
        poder_s = PoderSistema.objects.create(sistema=self.sistema, nome="Fúria", midia=FOTO_DB)
        habilidade_s = HabilidadeSistema.objects.create(sistema=self.sistema, nome="Cura", midia=FOTO_DB)

        base = f"/sistema/personagens/{self.personagem.id}"
        self.client.post(f"{base}/armas/{arma_s.id}/copiar/", {}, format="json")
        self.client.post(f"{base}/armaduras/{armadura_s.id}/copiar/", {}, format="json")
        self.client.post(f"{base}/poderes/{poder_s.id}/copiar/", {}, format="json")
        self.client.post(f"{base}/habilidades/{habilidade_s.id}/copiar/", {}, format="json")

        self.assertEqual(Arma.objects.get().foto.public_id, FOTO)
        self.assertEqual(Armadura.objects.get().foto.public_id, FOTO)
        self.assertEqual(Poder.objects.filter(habilidade__isnull=True).get().midia.public_id, FOTO)
        self.assertEqual(Habilidade.objects.get().midia.public_id, FOTO)

    def test_item_da_biblioteca_sem_foto_copia_sem_quebrar(self):
        item_sistema = ItemSistema.objects.create(sistema=self.sistema, nome="Corda")

        resposta = self.client.post(
            f"/sistema/personagens/{self.personagem.id}/itens/{item_sistema.id}/copiar/", {}, format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        # A coluna da ficha não aceita NULL — a ausência de imagem é "".
        self.assertFalse(Item.objects.get(pk=resposta.data["id"]).foto)
        self.assertFalse(AjusteImagem.objects.filter(object_id=resposta.data["id"]).exists())


@override_settings(IMAGENS=IMAGENS_TESTE)
class ArquivoCompartilhadoTests(BaseBiblioteca):
    """
    A cópia por referência só é segura porque `processar_fila` recheca o uso
    do arquivo antes de apagar. Este teste trava esse contrato: se um dia a
    rechecagem sair, apagar o item da ficha levaria junto a arte da
    biblioteca — e de todas as outras fichas que copiaram o mesmo item.
    """

    def test_excluir_a_copia_nao_apaga_o_arquivo_da_biblioteca(self):
        item_sistema = ItemSistema.objects.create(sistema=self.sistema, nome="Espada", foto=FOTO_DB)
        resposta = self.client.post(
            f"/sistema/personagens/{self.personagem.id}/itens/{item_sistema.id}/copiar/", {}, format="json"
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(f"/personagem/itens/{resposta.data['id']}/")

        self.delete.assert_not_called()
        self.assertFalse(ExclusaoImagemPendente.objects.exists())
        item_sistema.refresh_from_db()
        self.assertEqual(item_sistema.foto.public_id, FOTO)

    def test_arquivo_e_apagado_quando_a_ultima_referencia_some(self):
        item_sistema = ItemSistema.objects.create(sistema=self.sistema, nome="Espada", foto=FOTO_DB)
        resposta = self.client.post(
            f"/sistema/personagens/{self.personagem.id}/itens/{item_sistema.id}/copiar/", {}, format="json"
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(f"/personagem/itens/{resposta.data['id']}/")
            item_sistema.delete()

        self.delete.assert_called_once()
        self.assertEqual(self.delete.call_args.args[0], [FOTO])
