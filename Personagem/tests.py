from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase

from Usuario.models import Usuario
from .models import Arma, Armadura, Aprimoramento, Bonus, Habilidade, Item, Personagem, Status


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


class PesoInventarioConfigTests(DoisUsuariosTestCase):
    """
    Preferências do cálculo do Peso Atual (`peso_multiplica_quantidade` e
    `peso_ajuste_manual`). Antes viviam no navegador; agora são gravadas no
    Personagem para valerem em qualquer aparelho. O total em si continua sendo
    calculado pelo frontend e gravado em `peso_atual`.
    """

    def setUp(self):
        super().setUp()
        self.url = f"/personagem/{self.personagem.pk}/"
        self.autentica_como(self.alice)

    def patch(self, dados):
        return self.client.patch(self.url, dados, format="json")

    def test_ficha_nova_comeca_com_os_padroes(self):
        # Ligado (o comportamento de sempre) e ajuste "nunca definido" (None,
        # que NÃO é o mesmo que 0: é o sinal para o frontend adotar o
        # `peso_atual` já salvo em vez de sobrescrevê-lo).
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIs(response.data["peso_multiplica_quantidade"], True)
        self.assertIsNone(response.data["peso_ajuste_manual"])

    def test_patch_grava_a_opcao_de_multiplicar_e_persiste(self):
        response = self.patch({"peso_multiplica_quantidade": False})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIs(response.data["peso_multiplica_quantidade"], False)
        self.personagem.refresh_from_db()
        self.assertFalse(self.personagem.peso_multiplica_quantidade)

        self.patch({"peso_multiplica_quantidade": True})
        self.personagem.refresh_from_db()
        self.assertTrue(self.personagem.peso_multiplica_quantidade)

    def test_patch_grava_o_ajuste_manual_positivo_e_negativo(self):
        for enviado, esperado in [("2.50", Decimal("2.50")), ("-1.25", Decimal("-1.25")), (3, Decimal("3.00"))]:
            with self.subTest(enviado=enviado):
                response = self.patch({"peso_ajuste_manual": enviado})

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.personagem.refresh_from_db()
                self.assertEqual(self.personagem.peso_ajuste_manual, esperado)

    def test_zero_e_nulo_sao_coisas_diferentes(self):
        self.patch({"peso_ajuste_manual": "0.00"})
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.peso_ajuste_manual, Decimal("0.00"))  # "sem ajuste"

        response = self.patch({"peso_ajuste_manual": None})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.personagem.refresh_from_db()
        self.assertIsNone(self.personagem.peso_ajuste_manual)  # "nunca definido"

    def test_gravar_so_a_config_nao_mexe_no_peso(self):
        self.personagem.peso_atual = Decimal("7.50")
        self.personagem.peso_maximo = Decimal("15.00")
        self.personagem.save()

        self.patch({"peso_multiplica_quantidade": False, "peso_ajuste_manual": "1.00"})

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.peso_atual, Decimal("7.50"))
        self.assertEqual(self.personagem.peso_maximo, Decimal("15.00"))

    def test_gravar_so_o_peso_nao_mexe_na_config(self):
        self.patch({"peso_multiplica_quantidade": False, "peso_ajuste_manual": "2.00"})

        self.patch({"peso_atual": "9.00"})

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.peso_atual, Decimal("9.00"))
        self.assertFalse(self.personagem.peso_multiplica_quantidade)
        self.assertEqual(self.personagem.peso_ajuste_manual, Decimal("2.00"))

    def test_um_unico_patch_grava_peso_e_config_juntos(self):
        # É assim que o frontend grava: uma fila serializada que funde os
        # pedidos pendentes num só PATCH.
        response = self.patch(
            {"peso_atual": "12.00", "peso_multiplica_quantidade": False, "peso_ajuste_manual": "2.00"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.peso_atual, Decimal("12.00"))
        self.assertFalse(self.personagem.peso_multiplica_quantidade)
        self.assertEqual(self.personagem.peso_ajuste_manual, Decimal("2.00"))

    def test_rejeita_valores_invalidos_sem_alterar_nada(self):
        for dados in [
            {"peso_ajuste_manual": "abc"},
            {"peso_ajuste_manual": "1.234"},  # mais de 2 casas decimais
            {"peso_ajuste_manual": "123456789.00"},  # estoura max_digits=10
            {"peso_multiplica_quantidade": "talvez"},
        ]:
            with self.subTest(dados=dados):
                response = self.patch(dados)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.personagem.refresh_from_db()
                self.assertTrue(self.personagem.peso_multiplica_quantidade)
                self.assertIsNone(self.personagem.peso_ajuste_manual)

    def test_bob_nao_pode_alterar_a_config_da_ficha_de_alice(self):
        self.autentica_como(self.bob)

        response = self.patch({"peso_multiplica_quantidade": False, "peso_ajuste_manual": "99.00"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.personagem.refresh_from_db()
        self.assertTrue(self.personagem.peso_multiplica_quantidade)
        self.assertIsNone(self.personagem.peso_ajuste_manual)

    def test_a_config_e_independente_por_personagem(self):
        outra = Personagem.objects.create(usuario=self.alice, nome="Outra ficha")

        self.patch({"peso_multiplica_quantidade": False, "peso_ajuste_manual": "5.00"})

        outra.refresh_from_db()
        self.assertTrue(outra.peso_multiplica_quantidade)
        self.assertIsNone(outra.peso_ajuste_manual)


class ItemArmaArmaduraCompartilhamTests(DoisUsuariosTestCase):
    """
    Contrato em que o cálculo do Peso Atual do frontend se apoia: Arma e
    Armadura herdam de Item (herança multi-tabela), então a MESMA linha — mesmo
    id, mesmos `peso`/`quantidade` — aparece em `/itens/` e em `/arma/` (ou
    `/armadura/`), e editar ou remover por qualquer das rotas vale para todas.
    O frontend tem um cache por rota e os mantém em sincronia com base nisto;
    se um destes testes quebrar, o peso do inventário volta a errar.
    """

    def setUp(self):
        super().setUp()
        self.autentica_como(self.alice)
        self.item = Item.objects.create(personagem=self.personagem, nome="Corda", peso=Decimal("1.0"), quantidade=3)
        self.arma = Arma.objects.create(personagem=self.personagem, nome="Adaga", peso=Decimal("0.5"), quantidade=2)
        self.armadura = Armadura.objects.create(personagem=self.personagem, nome="Escudo", peso=Decimal("4.0"), quantidade=1)

    def ids(self, rota):
        response = self.client.get(f"/personagem/{self.personagem.pk}/{rota}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {linha["id"]: linha for linha in response.data}

    def test_a_lista_de_itens_inclui_as_armas_e_armaduras_com_o_mesmo_peso_e_quantidade(self):
        itens = self.ids("itens")
        armas = self.ids("arma")
        armaduras = self.ids("armadura")

        self.assertEqual(set(itens), {self.item.pk, self.arma.pk, self.armadura.pk})
        for linha, visao in [(self.arma, armas), (self.armadura, armaduras)]:
            self.assertEqual(itens[linha.pk]["peso"], visao[linha.pk]["peso"])
            self.assertEqual(itens[linha.pk]["quantidade"], visao[linha.pk]["quantidade"])

    def test_alterar_a_quantidade_pela_rota_de_itens_vale_para_a_rota_da_arma(self):
        response = self.client.patch(f"/personagem/itens/{self.arma.pk}/", {"quantidade": 5}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids("arma")[self.arma.pk]["quantidade"], 5)

    def test_alterar_o_peso_pela_rota_da_arma_vale_para_a_rota_de_itens(self):
        response = self.client.patch(f"/personagem/armas/{self.arma.pk}/", {"peso": "3.5"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(self.ids("itens")[self.arma.pk]["peso"]), Decimal("3.5"))

    def test_remover_pela_rota_da_arma_remove_da_lista_de_itens(self):
        response = self.client.delete(f"/personagem/armas/{self.arma.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotIn(self.arma.pk, self.ids("itens"))

    def test_remover_pela_rota_de_itens_remove_da_lista_de_armaduras(self):
        response = self.client.delete(f"/personagem/itens/{self.armadura.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotIn(self.armadura.pk, self.ids("armadura"))


class TemaPersonagemTests(DoisUsuariosTestCase):
    """
    `Personagem.tema` — paleta e aparência da ficha, antes no localStorage de
    cada aparelho. JSON livre no banco, validado no serializer: é o que vira
    CSS na tela de quem abrir a ficha.
    """

    def setUp(self):
        super().setUp()
        self.url = f"/personagem/{self.personagem.pk}/"
        self.autentica_como(self.alice)

    def patch(self, tema):
        return self.client.patch(self.url, {"tema": tema}, format="json")

    def test_ficha_nova_comeca_sem_tema(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["tema"], {})
        self.assertIsNone(response.data["fundo"])

    def test_patch_grava_cores_e_aparencia(self):
        tema = {"cores": {"primary": "#ff0066", "bg-card": "#101010"}, "aparencia": {"opacidadeCards": 60, "desfoque": 8.5}}

        response = self.patch(tema)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.tema, tema)

    def test_objeto_vazio_volta_ao_padrao(self):
        self.patch({"cores": {"primary": "#ff0066"}})

        response = self.patch({})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.tema, {})

    def test_recusa_o_que_viraria_css_invalido(self):
        invalidos = [
            "azul",
            {"fonte": "Comic Sans"},
            {"cores": {"primary": "red; background: url(x)"}},
            {"cores": {"--qualquer": "#000000"}},
            {"aparencia": {"opacidadeCards": 5}},
            {"aparencia": {"desfoque": True}},
            {"aparencia": {"zoom": 2}},
        ]
        for tema in invalidos:
            with self.subTest(tema=tema):
                response = self.patch(tema)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.tema, {})

    def test_outro_usuario_nao_altera_o_tema(self):
        self.autentica_como(self.bob)

        response = self.patch({"cores": {"primary": "#000000"}})

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.tema, {})
