from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase

from Usuario.models import Usuario
from .models import Personagem, Status, Habilidade, Aprimoramento, Bonus


class DoisUsuariosTestCase(APITestCase):
    """
    Base comum para os testes de permissão abaixo: cria dois usuários que
    não têm nenhuma relação entre si (não são mestre/jogador da mesma
    campanha, não compartilham personagens), e a ficha completa (Status,
    Habilidade, Aprimoramento, Bonus) pertence exclusivamente a `alice`.
    `bob` é usado em todos os testes para confirmar que ele NÃO consegue
    acessar nada que pertença a `alice`.
    """

    def setUp(self):
        self.alice = Usuario.objects.create_user(username="alice", password="SenhaForte123!")
        self.bob = Usuario.objects.create_user(username="bob", password="SenhaForte123!")

        self.personagem = Personagem.objects.create(usuario=self.alice, nome="Ficha da Alice")

        self.status_obj = Status.objects.create(
            personagem=self.personagem,
            nome="Pontos de Vida",
            valor_max=10,
            valor_atual=10,
        )

        self.habilidade = Habilidade.objects.create(
            personagem=self.personagem,
            nome="Bola de Fogo",
        )

        self.aprimoramento = Aprimoramento.objects.create(
            habilidade=self.habilidade,
            nome="Alcance Maior",
        )

        self.bonus = Bonus.objects.create(
            content_type=ContentType.objects.get_for_model(Status),
            object_id=self.status_obj.pk,
            nome="Bonus de Constituicao",
            valor=5,
        )

    def autentica_como(self, usuario):
        self.client.force_authenticate(user=usuario)


class BonusPermissionTests(DoisUsuariosTestCase):
    """
    Regressão para a falha de BOLA/IDOR corrigida em `bonus_lista` e
    `bonus_detalhe` (Personagem/views.py): antes da correção, QUALQUER
    usuário autenticado conseguia listar, ler, editar e excluir Bonus de
    QUALQUER personagem, bastando saber `tipo`/`object_id` ou o `pk` do
    Bonus. Estes testes falhavam (retornavam 200 em vez de 403) contra o
    código anterior à correção.
    """

    def test_bob_nao_pode_listar_bonus_do_status_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/status/{self.status_obj.pk}/bonus/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bob_nao_pode_criar_bonus_no_status_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/status/{self.status_obj.pk}/bonus/"
        response = self.client.post(url, {"nome": "Bonus malicioso", "valor": 999}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bob_nao_pode_ler_bonus_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/bonus/{self.bonus.pk}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bob_nao_pode_editar_bonus_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/bonus/{self.bonus.pk}/"
        response = self.client.patch(url, {"valor": 9999}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.bonus.refresh_from_db()
        self.assertEqual(self.bonus.valor, 5)  # valor original não foi alterado

    def test_bob_nao_pode_excluir_bonus_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/bonus/{self.bonus.pk}/"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Bonus.objects.filter(pk=self.bonus.pk).exists())

    def test_alice_pode_ler_e_editar_seu_proprio_bonus(self):
        # Controle: garante que a correção não bloqueou o dono legítimo.
        self.autentica_como(self.alice)

        url = f"/personagem/bonus/{self.bonus.pk}/"

        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        patch_response = self.client.patch(url, {"valor": 7}, format="json")
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.bonus.refresh_from_db()
        self.assertEqual(self.bonus.valor, 7)

    def test_alice_pode_criar_bonus_sem_enviar_object_id_manualmente(self):
        # Regressão para o bug do BonusSerializer: `object_id` não estava
        # em `read_only_fields`, então o POST falhava com
        # {"object_id": ["This field is required."]} mesmo o valor já
        # vindo da URL. Confirmado rodando a API real antes da correção.
        self.autentica_como(self.alice)

        url = f"/personagem/status/{self.status_obj.pk}/bonus/"
        response = self.client.post(url, {"nome": "Outro bonus", "valor": 3}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["object_id"], self.status_obj.pk)


class AprimoramentoPermissionTests(DoisUsuariosTestCase):
    """
    Regressão para a falha de BOLA/IDOR corrigida em `aprimoramento_detalhe`
    (Personagem/views.py): a view não chamava `check_object_permission` em
    nenhum momento.
    """

    def test_bob_nao_pode_ler_aprimoramento_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/aprimoramentos/{self.aprimoramento.pk}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bob_nao_pode_editar_aprimoramento_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/aprimoramentos/{self.aprimoramento.pk}/"
        response = self.client.patch(url, {"nome": "Nome alterado por bob"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.aprimoramento.refresh_from_db()
        self.assertEqual(self.aprimoramento.nome, "Alcance Maior")

    def test_bob_nao_pode_excluir_aprimoramento_de_alice(self):
        self.autentica_como(self.bob)

        url = f"/personagem/aprimoramentos/{self.aprimoramento.pk}/"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Aprimoramento.objects.filter(pk=self.aprimoramento.pk).exists())

    def test_alice_pode_ler_seu_proprio_aprimoramento(self):
        self.autentica_como(self.alice)

        url = f"/personagem/aprimoramentos/{self.aprimoramento.pk}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
