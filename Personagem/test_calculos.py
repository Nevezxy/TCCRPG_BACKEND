"""
Os valores finais da ficha (`Personagem/calculos.py`) e o sistema de bônus.

O que estes testes protegem, em ordem de importância:

  1. As FÓRMULAS não mudarem. Elas vieram do frontend, onde já valiam para
     todas as fichas existentes; qualquer alteração aqui muda números em
     fichas de gente que já joga. Em especial: `valor_temp` fora do total,
     bônus `somente_teste` fora do total, e Atributo × Nível nos Status que
     marcam `atributo_nivel`.
  2. Bônus por ENTIDADE ser uma referência viva, não uma cópia do número.
  3. Ciclos serem recusados na escrita e nunca derrubarem uma leitura.
  4. Arma/Armadura e Item compartilharem UM conjunto de bônus (herança
     multi-tabela).
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status as http
from rest_framework.test import APITestCase

from Usuario.models import Usuario

from . import calculos
from .models import (
    Aprimoramento,
    Arma,
    Armadura,
    Atributo,
    Bonus,
    Defesa,
    Habilidade,
    Item,
    Pericia,
    Personagem,
    Status,
    Tecnica,
)


def bonus_manual(alvo, valor, **extra):
    return Bonus.objects.create(
        content_type=ContentType.objects.get_for_model(calculos.modelo_base(alvo._meta.model_name)),
        object_id=alvo.pk,
        nome=extra.pop("nome", "Bônus"),
        valor=valor,
        **extra,
    )


class FichaBase(APITestCase):

    def setUp(self):
        self.usuario = Usuario.objects.create_user(username="ana", password="SenhaForte123!")
        self.personagem = Personagem.objects.create(usuario=self.usuario, nome="Ana", nivel=3)
        self.forca = Atributo.objects.create(personagem=self.personagem, nome="For", valor=4)
        self.client.force_authenticate(user=self.usuario)

    def final(self, obj):
        return calculos.ContextoCalculo().valor_final(obj)


class FormulasTests(FichaBase):

    def test_atributo_soma_bonus(self):
        bonus_manual(self.forca, 2)
        self.assertEqual(self.final(self.forca), 6)

    def test_defesa_soma_valor_atributo_e_bonus(self):
        defesa = Defesa.objects.create(
            personagem=self.personagem, nome="CA", valor=10, atributo=self.forca
        )
        bonus_manual(defesa, 1)
        self.assertEqual(self.final(defesa), 10 + 4 + 1)

    def test_defesa_usa_o_valor_FINAL_do_atributo(self):
        """Um bônus na Força chega na Defesa que depende dela."""
        defesa = Defesa.objects.create(
            personagem=self.personagem, nome="CA", valor=10, atributo=self.forca
        )
        bonus_manual(self.forca, 3)
        self.assertEqual(self.final(defesa), 10 + (4 + 3))

    def test_pericia_so_soma_o_atributo_quando_marcado(self):
        com = Pericia.objects.create(
            personagem=self.personagem, nome="Atletismo", treinamento=5,
            atributo=self.forca, somar_atributo=True,
        )
        sem = Pericia.objects.create(
            personagem=self.personagem, nome="Ofício", treinamento=5,
            atributo=self.forca, somar_atributo=False,
        )
        self.assertEqual(self.final(com), 5 + 4)
        self.assertEqual(self.final(sem), 5)

    def test_status_multiplica_o_atributo_pelo_nivel(self):
        vida = Status.objects.create(
            personagem=self.personagem, nome="PV", barra=True,
            valor_max=10, valor_atual=8, atributo=self.forca, atributo_nivel=True,
        )
        bonus_manual(vida, 2)
        contexto = calculos.ContextoCalculo()
        # Nível 3 × Força 4 = 12.
        self.assertEqual(contexto.valor_max_final(vida), 10 + 12 + 2)
        self.assertEqual(contexto.valor_final(vida), 8 + 12 + 2)

    def test_status_nao_soma_valor_temp(self):
        """
        `valor_temp` é exibido à parte, entre parênteses, e NUNCA entrou no
        total — somá-lo mudaria o número de toda ficha que já existe.
        """
        vida = Status.objects.create(
            personagem=self.personagem, nome="PV", valor_max=10, valor_atual=8, valor_temp=5,
        )
        self.assertEqual(self.final(vida), 8)

    def test_bonus_somente_teste_e_inativo_ficam_de_fora(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        bonus_manual(defesa, 100, somente_teste=True)
        bonus_manual(defesa, 50, ativo=False)
        bonus_manual(defesa, 1)
        self.assertEqual(self.final(defesa), 11)

    def test_folhas_usam_o_valor_digitado(self):
        item = Item.objects.create(personagem=self.personagem, nome="Corda", valor_final=7)
        tecnica = Tecnica.objects.create(personagem=self.personagem, nome="Foco", valor_final=3)
        self.assertEqual((self.final(item), self.final(tecnica)), (7, 3))

    def test_armadura_espelha_defesa_em_valor_final(self):
        armadura = Armadura.objects.create(personagem=self.personagem, nome="Cota", defesa=6)
        self.assertEqual(armadura.valor_final, 6)
        # E a MESMA linha vista como Item concorda — é o que impede o número
        # de mudar entre a aba Inventário e a aba Combate.
        self.assertEqual(Item.objects.get(pk=armadura.pk).valor_final, 6)

        armadura.defesa = 9
        armadura.save()
        self.assertEqual(Item.objects.get(pk=armadura.pk).valor_final, 9)

        # `update_fields` também: `defesa` é coluna da Armadura e
        # `valor_final` é do Item (herança multi-tabela), e o save precisa
        # gravar as duas tabelas. É o caminho que um PATCH parcial usa.
        armadura.defesa = 12
        armadura.save(update_fields=["defesa"])
        self.assertEqual(Item.objects.get(pk=armadura.pk).valor_final, 12)


class BonusPorEntidadeTests(FichaBase):

    def url_bonus(self, tipo, obj):
        return f"/personagem/{tipo}/{obj.pk}/bonus/"

    def test_bonus_acompanha_a_origem_em_vez_de_copiar_o_numero(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        resposta = self.client.post(
            self.url_bonus("defesa", defesa),
            {"nome": "Força", "tipo_origem": "entidade", "origem_tipo": "atributo",
             "origem_id": self.forca.pk},
            format="json",
        )
        self.assertEqual(resposta.status_code, http.HTTP_201_CREATED, resposta.data)
        self.assertEqual(resposta.data["valor_efetivo"], 4)
        self.assertEqual(self.final(defesa), 14)

        # A origem sobe -> o bônus sobe junto, sem ninguém reeditar nada.
        self.forca.valor = 9
        self.forca.save()
        self.assertEqual(self.final(defesa), 19)

    def test_origem_de_outro_personagem_e_recusada(self):
        outro = Personagem.objects.create(usuario=self.usuario, nome="Outro")
        atributo_alheio = Atributo.objects.create(personagem=outro, nome="For", valor=99)
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)

        resposta = self.client.post(
            self.url_bonus("defesa", defesa),
            {"nome": "Roubo", "tipo_origem": "entidade", "origem_tipo": "atributo",
             "origem_id": atributo_alheio.pk},
            format="json",
        )
        self.assertEqual(resposta.status_code, http.HTTP_400_BAD_REQUEST)
        self.assertIn("mesmo personagem", str(resposta.data["origem_id"]))

    def test_entidade_nao_pode_ser_origem_de_si_mesma(self):
        resposta = self.client.post(
            self.url_bonus("atributo", self.forca),
            {"nome": "Eu", "tipo_origem": "entidade", "origem_tipo": "atributo",
             "origem_id": self.forca.pk},
            format="json",
        )
        self.assertEqual(resposta.status_code, http.HTTP_400_BAD_REQUEST)

    def test_ciclo_e_recusado_na_escrita(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        # Defesa recebe da Força: ok.
        self.client.post(
            self.url_bonus("defesa", defesa),
            {"nome": "Força", "tipo_origem": "entidade", "origem_tipo": "atributo",
             "origem_id": self.forca.pk},
            format="json",
        )
        # Força receber da Defesa fecharia o ciclo.
        resposta = self.client.post(
            self.url_bonus("atributo", self.forca),
            {"nome": "Volta", "tipo_origem": "entidade", "origem_tipo": "defesa",
             "origem_id": defesa.pk},
            format="json",
        )
        self.assertEqual(resposta.status_code, http.HTTP_400_BAD_REQUEST)
        self.assertIn("circular", str(resposta.data["origem_id"]))

    def test_ciclo_ja_gravado_nao_derruba_a_leitura(self):
        """
        Rede de segurança da LEITURA: dado legado, ou dois POSTs concorrentes
        que passem pela validação ao mesmo tempo, não podem transformar um
        GET da ficha num RecursionError.
        """
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        ct_atributo = ContentType.objects.get_for_model(Atributo)
        ct_defesa = ContentType.objects.get_for_model(Defesa)
        Bonus.objects.create(
            content_type=ct_defesa, object_id=defesa.pk, nome="a",
            tipo_origem=Bonus.TIPO_ENTIDADE,
            origem_content_type=ct_atributo, origem_object_id=self.forca.pk,
        )
        Bonus.objects.create(
            content_type=ct_atributo, object_id=self.forca.pk, nome="b",
            tipo_origem=Bonus.TIPO_ENTIDADE,
            origem_content_type=ct_defesa, origem_object_id=defesa.pk,
        )

        contexto = calculos.ContextoCalculo()
        self.assertEqual(contexto.valor_final(defesa), 10 + 4)
        self.assertTrue(contexto.incompleto(defesa))

    def test_origem_excluida_vira_bonus_manual_com_o_ultimo_valor(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        self.client.post(
            self.url_bonus("defesa", defesa),
            {"nome": "Força", "tipo_origem": "entidade", "origem_tipo": "atributo",
             "origem_id": self.forca.pk},
            format="json",
        )
        self.forca.delete()

        bonus = Bonus.objects.get(object_id=defesa.pk)
        self.assertEqual(bonus.tipo_origem, Bonus.TIPO_MANUAL)
        self.assertIsNone(bonus.origem_content_type_id)
        self.assertEqual(bonus.valor, 4)
        self.assertEqual(self.final(defesa), 14)


class HerancaMultiTabelaTests(FichaBase):

    def test_arma_e_item_compartilham_os_bonus(self):
        arma = Arma.objects.create(personagem=self.personagem, nome="Espada")

        criada = self.client.post(
            f"/personagem/arma/{arma.pk}/bonus/", {"nome": "Afiada", "valor": 2}, format="json"
        )
        self.assertEqual(criada.status_code, http.HTTP_201_CREATED, criada.data)

        # A MESMA linha, pedida pela rota de Item, enxerga o mesmo bônus.
        pela_rota_item = self.client.get(f"/personagem/item/{arma.pk}/bonus/")
        self.assertEqual([b["nome"] for b in pela_rota_item.data], ["Afiada"])

        # E foi gravado sob o model base.
        self.assertEqual(
            Bonus.objects.get(pk=criada.data["id"]).content_type,
            ContentType.objects.get_for_model(Item),
        )

    def test_habilidade_e_poder_compartilham_os_bonus(self):
        habilidade = Habilidade.objects.create(personagem=self.personagem, nome="Bola de Fogo")
        self.client.post(
            f"/personagem/habilidade/{habilidade.pk}/bonus/",
            {"nome": "Ampliada", "valor": 1}, format="json",
        )
        pela_rota_poder = self.client.get(f"/personagem/poder/{habilidade.pk}/bonus/")
        self.assertEqual([b["nome"] for b in pela_rota_poder.data], ["Ampliada"])


class AprimoramentoBonusTests(FichaBase):
    """
    O frontend já declarava `BONUS_TIPO.aprimoramento`, mas o tipo faltava em
    `MODELOS_BONUS` (400) e o model não tinha `personagem`, então
    `check_object_permission` negava até para o dono (403).
    """

    def setUp(self):
        super().setUp()
        self.habilidade = Habilidade.objects.create(personagem=self.personagem, nome="Bola de Fogo")
        self.aprimoramento = Aprimoramento.objects.create(
            habilidade=self.habilidade, nome="Alcance Maior"
        )

    def test_dono_pode_criar_bonus_em_aprimoramento(self):
        resposta = self.client.post(
            f"/personagem/aprimoramento/{self.aprimoramento.pk}/bonus/",
            {"nome": "Extra", "valor": 2}, format="json",
        )
        self.assertEqual(resposta.status_code, http.HTTP_201_CREATED, resposta.data)

    def test_estranho_nao_pode(self):
        bob = Usuario.objects.create_user(username="bob", password="SenhaForte123!")
        self.client.force_authenticate(user=bob)
        resposta = self.client.get(f"/personagem/aprimoramento/{self.aprimoramento.pk}/bonus/")
        self.assertEqual(resposta.status_code, http.HTTP_403_FORBIDDEN)


class UsarTests(FichaBase):

    def setUp(self):
        super().setUp()
        self.tecnica = Tecnica.objects.create(personagem=self.personagem, nome="Foco")

    def test_usar_liga_os_bonus_por_uma_hora(self):
        desligado = bonus_manual(self.tecnica, 3, ativo=False)

        resposta = self.client.post(f"/personagem/tecnica/{self.tecnica.pk}/usar/")
        self.assertEqual(resposta.status_code, http.HTTP_200_OK, resposta.data)

        desligado.refresh_from_db()
        self.assertTrue(desligado.ativo)
        self.assertIsNotNone(desligado.expira_em)
        restante = desligado.expira_em - timezone.now()
        self.assertTrue(timedelta(minutes=59) < restante <= timedelta(hours=1))

    def test_usar_nao_poe_prazo_em_bonus_permanente(self):
        """Um bônus que o jogador deixou ligado de propósito não vira um
        bônus de uma hora só porque a técnica foi usada."""
        permanente = bonus_manual(self.tecnica, 3, ativo=True)
        self.client.post(f"/personagem/tecnica/{self.tecnica.pk}/usar/")
        permanente.refresh_from_db()
        self.assertTrue(permanente.ativo)
        self.assertIsNone(permanente.expira_em)

    def test_bonus_vencido_nao_conta_mesmo_antes_do_varredor(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        bonus_manual(defesa, 5, ativo=True, expira_em=timezone.now() - timedelta(minutes=1))
        # Ainda gravado como ativo, mas já não soma: a leitura nunca depende
        # de o varredor ter rodado.
        self.assertEqual(self.final(defesa), 10)

    def test_varredor_persiste_a_expiracao(self):
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        vencido = bonus_manual(defesa, 5, expira_em=timezone.now() - timedelta(minutes=1))

        self.client.get(f"/personagem/defesa/{defesa.pk}/bonus/")

        vencido.refresh_from_db()
        self.assertFalse(vencido.ativo)
        self.assertIsNone(vencido.expira_em)

    def test_abrir_o_painel_de_bonus_e_barato_quando_nada_venceu(self):
        """
        O painel de bônus abre a cada card expandido da ficha. A varredura de
        expirados ali é por ALVO (uma consulta indexada), não pela ficha
        inteira — que precisaria levantar os ids das dez tabelas só para, no
        caso comum, não atualizar linha nenhuma.
        """
        defesa = Defesa.objects.create(personagem=self.personagem, nome="CA", valor=10)
        bonus_manual(defesa, 2)
        url = f"/personagem/defesa/{defesa.pk}/bonus/"

        self.client.get(url)  # aquece o cache de ContentType
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(url)

        # Sem um teto explícito o teste não protege nada; 12 dá folga para as
        # consultas de permissão e ainda pega uma volta da varredura por
        # personagem (que sozinha traz oito consultas de id).
        self.assertLess(len(consultas), 12, [q["sql"][:80] for q in consultas])


class CalculosFichaEndpointTests(FichaBase):

    def test_devolve_a_ficha_inteira_com_os_totais(self):
        defesa = Defesa.objects.create(
            personagem=self.personagem, nome="CA", valor=10, atributo=self.forca
        )
        bonus_manual(defesa, 1)
        Pericia.objects.create(
            personagem=self.personagem, nome="Atletismo", treinamento=2,
            atributo=self.forca, somar_atributo=True,
        )

        resposta = self.client.get(f"/personagem/{self.personagem.pk}/calculos/")
        self.assertEqual(resposta.status_code, http.HTTP_200_OK)

        [dados_defesa] = resposta.data["defesas"]
        self.assertEqual(dados_defesa["valor_final"], 15)
        self.assertEqual((dados_defesa["atributo_total"], dados_defesa["bonus_total"]), (4, 1))

        [dados_pericia] = resposta.data["pericias"]
        self.assertEqual(dados_pericia["valor_final"], 6)

        self.assertEqual([b["valor_efetivo"] for b in resposta.data["bonus"]], [1])

    def test_numero_de_consultas_nao_cresce_com_o_tamanho_da_ficha(self):
        """
        O motivo de este endpoint existir: antes, cada card pedia os próprios
        bônus, e uma ficha de D&D (6 atributos + 3 status + 9 defesas + 21
        perícias) disparava ~39 requisições só para exibir os totais.
        """
        url = f"/personagem/{self.personagem.pk}/calculos/"

        for i in range(10):
            Pericia.objects.create(
                personagem=self.personagem, nome=f"P{i}", treinamento=1, atributo=self.forca
            )
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(url)

        for i in range(30):
            Pericia.objects.create(
                personagem=self.personagem, nome=f"Q{i}", treinamento=1, atributo=self.forca
            )
        with CaptureQueriesContext(connection) as muitas:
            self.client.get(url)

        self.assertEqual(len(muitas), len(poucas))


class ListagensTests(FichaBase):
    """
    As listagens normais da ficha (`/pericias/`, `/status/`, ...) também
    publicam `valor_final`. Sem um contexto de cálculo compartilhado por
    resposta, cada linha pediria os próprios bônus e o próprio atributo — o
    mesmo N+1 que o frontend tinha com um `useBonusTotal` por card, só que do
    lado do servidor.
    """

    def test_listagem_de_pericias_nao_cresce_em_consultas(self):
        url = f"/personagem/{self.personagem.pk}/pericias/"

        for i in range(5):
            Pericia.objects.create(
                personagem=self.personagem, nome=f"P{i}", treinamento=1,
                atributo=self.forca, somar_atributo=True,
            )
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(url)

        for i in range(25):
            Pericia.objects.create(
                personagem=self.personagem, nome=f"Q{i}", treinamento=1,
                atributo=self.forca, somar_atributo=True,
            )
        with CaptureQueriesContext(connection) as muitas:
            resposta = self.client.get(url)

        self.assertEqual(len(resposta.data), 30)
        self.assertEqual(len(muitas), len(poucas))

    def test_listagem_publica_o_total_e_a_decomposicao(self):
        pericia = Pericia.objects.create(
            personagem=self.personagem, nome="Atletismo", treinamento=2,
            atributo=self.forca, somar_atributo=True,
        )
        bonus_manual(pericia, 1)
        bonus_manual(self.forca, 3)

        [dados] = self.client.get(f"/personagem/{self.personagem.pk}/pericias/").data
        # treinamento 2 + Força final (4 + 3) + bônus 1
        self.assertEqual(dados["valor_final"], 10)
        self.assertEqual((dados["atributo_total"], dados["bonus_total"]), (7, 1))
        self.assertFalse(dados["valor_final_incompleto"])
