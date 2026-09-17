"""
Notas — quem "fala" a nota (`NotaSerializer.get_autor`).

BUGFIX: o avatar da nota mostrava sempre o centro geométrico da foto do
personagem, ignorando o recorte/zoom salvo (`foto_ajuste`) — porque
`get_autor` nunca enviava esse campo, diferente de todo outro lugar do app
que mostra a mesma foto (Escudo, cards, cabeçalho da ficha).
"""

from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase

from Midia.services import gravar_ajuste
from Personagem.models import Personagem
from Usuario.models import Usuario

from .models import NPC, Campanha, Nota

AJUSTE = {"modo": "cobrir", "escala": 1.6, "offsetX": 0.15, "offsetY": -0.2}


class AutorNotaTests(APITestCase):

    def setUp(self):
        self.mestre = Usuario.objects.create_user(username="mestre", password="SenhaForte123!")
        self.jogador = Usuario.objects.create_user(username="jogador", password="SenhaForte123!")
        self.campanha = Campanha.objects.create(mestre=self.mestre, nome="Mesa")
        self.campanha.jogadores.add(self.jogador)
        self.npc = NPC.objects.create(campanha=self.campanha, nome="Taverneiro")
        self.client.force_authenticate(self.jogador)

    def _criar_nota(self, personagem=None):
        return self.client.post(
            "/campanha/notas/",
            {
                "content_type": "npc",
                "object_id": self.npc.pk,
                "conteudo": "Anotação de teste.",
                "personagem": personagem.pk if personagem else None,
            },
            format="json",
        )

    def test_autor_personagem_leva_o_enquadramento_salvo_da_foto(self):
        personagem = Personagem.objects.create(usuario=self.jogador, nome="Aria", nivel=1, foto="fichas/aria.jpg")
        self.campanha.personagens.add(personagem)
        gravar_ajuste(personagem, "foto", AJUSTE)

        resposta = self._criar_nota(personagem)

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        autor = resposta.data["autor"]
        self.assertEqual(autor["tipo"], "personagem")
        self.assertIsNotNone(autor["foto"])
        self.assertEqual(autor["foto_ajuste"], AJUSTE)

    def test_autor_personagem_sem_ajuste_salvo_nao_quebra(self):
        personagem = Personagem.objects.create(usuario=self.jogador, nome="Bram", nivel=1, foto="fichas/bram.jpg")
        self.campanha.personagens.add(personagem)

        resposta = self._criar_nota(personagem)

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertIsNone(resposta.data["autor"]["foto_ajuste"])

    def test_autor_usuario_sem_personagem_nao_tem_foto_nem_ajuste(self):
        resposta = self._criar_nota()

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        autor = resposta.data["autor"]
        self.assertEqual(autor["tipo"], "usuario")
        self.assertIsNone(autor["foto"])
        self.assertIsNone(autor["foto_ajuste"])

    def test_listagem_tambem_leva_o_ajuste(self):
        personagem = Personagem.objects.create(usuario=self.jogador, nome="Cassia", nivel=1, foto="fichas/cassia.jpg")
        self.campanha.personagens.add(personagem)
        gravar_ajuste(personagem, "foto", AJUSTE)
        self._criar_nota(personagem)

        ct = ContentType.objects.get_for_model(NPC).model
        resposta = self.client.get(f"/campanha/notas/?content_type={ct}&object_id={self.npc.pk}")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        [nota] = resposta.data
        self.assertEqual(nota["autor"]["foto_ajuste"], AJUSTE)

    def test_nao_vaza_o_ajuste_de_outro_personagem(self):
        """Regressão de cache: duas notas de personagens DIFERENTES na mesma
        listagem não podem compartilhar o `foto_ajuste` um do outro."""
        aria = Personagem.objects.create(usuario=self.jogador, nome="Aria", nivel=1, foto="fichas/aria.jpg")
        bram = Personagem.objects.create(usuario=self.jogador, nome="Bram", nivel=1, foto="fichas/bram.jpg")
        self.campanha.personagens.add(aria, bram)
        gravar_ajuste(aria, "foto", AJUSTE)
        self._criar_nota(aria)
        self._criar_nota(bram)

        ct = ContentType.objects.get_for_model(NPC).model
        resposta = self.client.get(f"/campanha/notas/?content_type={ct}&object_id={self.npc.pk}")

        por_nome = {n["autor"]["nome"]: n["autor"]["foto_ajuste"] for n in resposta.data}
        self.assertEqual(por_nome["Aria"], AJUSTE)
        self.assertIsNone(por_nome["Bram"])

    def test_nota_orfa_de_personagem_excluido_nao_quebra(self):
        """`personagem` é SET_NULL: a nota sobrevive à exclusão do
        personagem, e `get_autor` cai no ramo de usuário sem levantar erro."""
        personagem = Personagem.objects.create(usuario=self.jogador, nome="Temp", nivel=1)
        self.campanha.personagens.add(personagem)
        nota = Nota.objects.create(
            usuario=self.jogador,
            personagem=personagem,
            content_type=ContentType.objects.get_for_model(NPC),
            object_id=self.npc.pk,
            conteudo="x",
        )
        personagem.delete()
        nota.refresh_from_db()
        self.assertIsNone(nota.personagem_id)

        ct = ContentType.objects.get_for_model(NPC).model
        resposta = self.client.get(f"/campanha/notas/?content_type={ct}&object_id={self.npc.pk}")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data[0]["autor"]["tipo"], "usuario")
