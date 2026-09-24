"""
Vários bônus fornecidos pela mesma entidade (`BonusFornecido`) e a escolha
de UM deles como origem de um bônus (`Bonus.origem_fornecido`).

O que estes testes protegem:

  1. Um bônus que aponta para "+4 CA" vale 4 — não o total da entidade —, e
     acompanha a linha se ela mudar.
  2. Os bônus por entidade antigos (sem bônus nomeado escolhido) continuam
     valendo o `valor_final` da origem: nada existente muda de número.
  3. Não dá para apontar para um bônus nomeado de OUTRA entidade.
  4. Apagar o bônus nomeado (ou a entidade inteira) congela os dependentes
     como manuais com o último valor — a regra que já valia para a origem.
  5. A listagem publica os bônus nomeados de todas as linhas sem N+1.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework import status as http

from . import calculos
from .models import Aprimoramento, Arma, Bonus, BonusFornecido, Defesa, Habilidade, Item
from .test_calculos import FichaBase


class BonusFornecidoTests(FichaBase):

    def setUp(self):
        super().setUp()
        self.postura = Habilidade.objects.create(personagem=self.personagem, nome="Postura Defensiva", valor_final=9)
        self.ca = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        self.dt = Defesa.objects.create(personagem=self.personagem, nome="DT", valor=12)

    def criar_fornecido(self, entidade, tipo, nome, valor):
        resposta = self.client.post(
            f"/personagem/{tipo}/{entidade.pk}/bonus-fornecidos/", {"nome": nome, "valor": valor}, format="json"
        )
        self.assertEqual(resposta.status_code, http.HTTP_201_CREATED, resposta.data)
        return resposta.data

    def usar_como_origem(self, alvo, tipo_alvo, origem_tipo, origem_id, fornecido=None):
        corpo = {"nome": "x", "tipo_origem": "entidade", "origem_tipo": origem_tipo, "origem_id": origem_id}
        if fornecido is not None:
            corpo["origem_fornecido"] = fornecido
        return self.client.post(f"/personagem/{tipo_alvo}/{alvo.pk}/bonus/", corpo, format="json")

    def test_cada_referencia_vale_o_bonus_escolhido(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        mais2 = self.criar_fornecido(self.postura, "habilidade", "DT", 2)

        r1 = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"])
        r2 = self.usar_como_origem(self.dt, "defesa", "habilidade", self.postura.pk, mais2["id"])
        self.assertEqual(r1.status_code, http.HTTP_201_CREATED, r1.data)
        self.assertEqual((r1.data["valor_efetivo"], r1.data["origem_fornecido_nome"]), (4, "CA"))
        self.assertEqual(r2.data["valor_efetivo"], 2)
        self.assertEqual(self.final(self.ca), 14)
        self.assertEqual(self.final(self.dt), 14)

    def test_mesma_entidade_referenciada_varias_vezes(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"])
        self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk)  # o total, como antes
        self.assertEqual(self.final(self.ca), 10 + 4 + 9)

    def test_referencia_acompanha_o_valor_do_bonus_nomeado(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"])
        self.client.patch(f"/personagem/bonus-fornecidos/{mais4['id']}/", {"valor": 6}, format="json")
        self.assertEqual(self.final(self.ca), 16)

    def test_bonus_antigo_continua_valendo_o_total(self):
        resposta = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk)
        self.assertIsNone(resposta.data["origem_fornecido"])
        self.assertEqual(resposta.data["valor_efetivo"], 9)

    def test_recusa_bonus_nomeado_de_outra_entidade(self):
        outra = Item.objects.create(personagem=self.personagem, nome="Escudo")
        alheio = self.criar_fornecido(outra, "item", "CA", 2)
        resposta = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, alheio["id"])
        self.assertEqual(resposta.status_code, http.HTTP_400_BAD_REQUEST)
        self.assertIn("origem_fornecido", resposta.data)

    def test_trocar_de_origem_esquece_a_escolha_antiga(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        bonus = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"]).data
        outra = Item.objects.create(personagem=self.personagem, nome="Anel", valor_final=1)
        resposta = self.client.patch(
            f"/personagem/bonus/{bonus['id']}/", {"origem_tipo": "item", "origem_id": outra.pk}, format="json"
        )
        self.assertIsNone(resposta.data["origem_fornecido"])
        self.assertEqual(resposta.data["valor_efetivo"], 1)

    def test_apagar_o_bonus_nomeado_congela_o_dependente(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        bonus = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"]).data
        self.client.delete(f"/personagem/bonus-fornecidos/{mais4['id']}/")
        congelado = Bonus.objects.get(pk=bonus["id"])
        self.assertEqual((congelado.tipo_origem, congelado.valor, congelado.origem_fornecido_id), ("manual", 4, None))
        self.assertEqual(self.final(self.ca), 14)

    def test_apagar_a_entidade_leva_os_bonus_nomeados_e_congela_no_valor_escolhido(self):
        mais4 = self.criar_fornecido(self.postura, "habilidade", "CA", 4)
        bonus = self.usar_como_origem(self.ca, "defesa", "habilidade", self.postura.pk, mais4["id"]).data
        self.postura.delete()
        self.assertFalse(BonusFornecido.objects.filter(pk=mais4["id"]).exists())
        self.assertEqual(Bonus.objects.get(pk=bonus["id"]).valor, 4)

    def test_arma_e_item_compartilham_os_bonus_nomeados(self):
        arma = Arma.objects.create(personagem=self.personagem, nome="Espada")
        self.criar_fornecido(arma, "arma", "Ataque", 2)
        itens = self.client.get(f"/personagem/{self.personagem.pk}/itens/")
        linha = next(i for i in itens.data if i["id"] == arma.pk)
        self.assertEqual([f["nome"] for f in linha["bonus_fornecidos"]], ["Ataque"])

    def test_aprimoramento_fornece_e_aparece_no_resumo_da_habilidade(self):
        apr = Aprimoramento.objects.create(habilidade=self.postura, nome="Guarda Alta")
        self.criar_fornecido(apr, "aprimoramento", "CA", 1)
        resposta = self.client.get(f"/personagem/{self.personagem.pk}/habilidades/")
        resumo = resposta.data[0]["aprimoramentos_resumo"]
        self.assertEqual(resumo[0]["nome"], "Guarda Alta")
        self.assertEqual(resumo[0]["bonus_fornecidos"][0]["valor"], 1)

    def test_listagem_sem_consulta_por_linha(self):
        for i in range(6):
            item = Item.objects.create(personagem=self.personagem, nome=f"Item {i}")
            BonusFornecido.objects.create(
                content_type_id=calculos.ContentType.objects.get_for_model(Item).id, object_id=item.pk, nome="X", valor=i
            )
        url = f"/personagem/{self.personagem.pk}/itens/"
        with CaptureQueriesContext(connection) as poucos:
            self.client.get(url)
        Item.objects.create(personagem=self.personagem, nome="Mais um")
        with CaptureQueriesContext(connection) as mais:
            self.client.get(url)
        self.assertEqual(len(poucos.captured_queries), len(mais.captured_queries))

    def test_entidade_calculada_nao_fornece_bonus_nomeado(self):
        resposta = self.client.post(
            f"/personagem/defesa/{self.ca.pk}/bonus-fornecidos/", {"nome": "X", "valor": 1}, format="json"
        )
        self.assertEqual(resposta.status_code, http.HTTP_400_BAD_REQUEST)

    def test_outro_usuario_nao_mexe(self):
        from Usuario.models import Usuario

        estranho = Usuario.objects.create_user(username="zed", password="SenhaForte123!")
        self.client.force_authenticate(user=estranho)
        resposta = self.client.post(
            f"/personagem/habilidade/{self.postura.pk}/bonus-fornecidos/", {"nome": "X", "valor": 1}, format="json"
        )
        self.assertEqual(resposta.status_code, http.HTTP_403_FORBIDDEN)
