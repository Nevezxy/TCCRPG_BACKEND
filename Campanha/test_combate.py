"""
Combate do Escudo do Mestre: permissões, ordem, dano, turno, remoções em
cascata e o filtro de eventos por destinatário.
"""

import asyncio

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from Personagem.models import Personagem
from Usuario.models import Usuario

from . import combate
from .escudo import nome_grupo
from .models import NPC, Campanha, Combate, Criatura, ParticipanteCombate

CAMADA_MEMORIA = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


class PvDaFichaTests(SimpleTestCase):

    def test_formatos_do_editor(self):
        self.assertEqual(combate.pv_da_ficha({"template": "tcc", "staticInfo": {"hp": "30 / 45"}}), 45)
        self.assertEqual(combate.pv_da_ficha({"template": "dnd", "combat": {"hp": "200 (16d20+32)"}}), 200)
        self.assertEqual(combate.pv_da_ficha({"staticInfo": {"hp": "12"}}), 12)
        self.assertEqual(combate.pv_da_ficha({"staticInfo": {"hp": 18}}), 18)

    def test_irreconheciveis_viram_none(self):
        for ficha in (None, {}, {"staticInfo": {"hp": ""}}, {"combat": {"hp": "muito"}}, {"staticInfo": {"hp": True}}):
            self.assertIsNone(combate.pv_da_ficha(ficha))


class FiltrarEventoTests(SimpleTestCase):
    linha = {"id": 1, "versao": 2, "iniciativa": 10, "pv_atual": 5, "pv_max": 20}

    def test_mestre_recebe_tudo(self):
        evento = {"tipo": "combate_valores", "dados": self.linha}
        self.assertEqual(combate.filtrar_evento(evento, True, False), (evento, False))

    def test_jogador_sem_visibilidade_nao_recebe_linhas(self):
        evento = {"tipo": "combate_valores", "dados": self.linha}
        self.assertEqual(combate.filtrar_evento(evento, False, False), (None, False))

    def test_jogador_com_visibilidade_recebe_so_percentual(self):
        saida, _ = combate.filtrar_evento({"tipo": "combate_valores", "dados": self.linha}, False, True)
        self.assertNotIn("pv_atual", saida["dados"])
        self.assertNotIn("pv_max", saida["dados"])
        self.assertEqual(saida["dados"]["pv_percentual"], 25)

    def test_evento_de_combate_atualiza_visibilidade(self):
        evento = {"tipo": "combate", "dados": {"visivel_para_jogadores": True}}
        self.assertEqual(combate.filtrar_evento(evento, False, False), (evento, True))


@override_settings(CHANNEL_LAYERS=CAMADA_MEMORIA)
class CombateBase(APITestCase):

    def setUp(self):
        self.mestre = Usuario.objects.create_user(username="mestre", password="SenhaForte123!")
        self.moderador = Usuario.objects.create_user(username="moderador", password="SenhaForte123!")
        self.jogador = Usuario.objects.create_user(username="jogador", password="SenhaForte123!")
        self.estranho = Usuario.objects.create_user(username="estranho", password="SenhaForte123!")

        self.campanha = Campanha.objects.create(mestre=self.mestre, nome="Mesa")
        self.campanha.jogadores.add(self.jogador, self.moderador)
        self.campanha.moderadores.add(self.moderador)

        self.aria = Personagem.objects.create(usuario=self.jogador, nome="Aria", nivel=3)
        self.bram = Personagem.objects.create(usuario=self.jogador, nome="Bram", nivel=2)
        self.campanha.personagens.add(self.aria, self.bram)

        self.npc = NPC.objects.create(campanha=self.campanha, nome="Capitão", ficha={"staticInfo": {"hp": "40 / 40"}})
        self.goblin = Criatura.objects.create(
            campanha=self.campanha, nome="Goblin", ficha={"combat": {"hp": "7 (2d6)"}}
        )

        self.base = f"/campanha/{self.campanha.pk}/combate/"
        self.client.force_authenticate(self.mestre)

    def tearDown(self):
        # O UserRateThrottle (300/min) conta requisições no cache, que NÃO é
        # desfeito com a transação do teste — e o SQLite reaproveita os ids
        # de usuário entre testes. Sem limpar, as dezenas de requisições
        # desta suíte estouram a cota de testes que rodam depois (429).
        cache.clear()
        super().tearDown()

    def adicionar(self, *entidades, usuario=None):
        if usuario:
            self.client.force_authenticate(usuario)
        resposta = self.client.post(
            f"{self.base}participantes/",
            {"entidades": [{"tipo": t, "id": i, "quantidade": q} for t, i, q in entidades]},
            format="json",
        )
        return resposta

    def estado(self):
        return self.client.get(self.base).data


class PermissoesTests(CombateBase):

    def test_mestre_e_moderador_controlam(self):
        self.assertEqual(self.client.get(self.base).status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.moderador)
        self.assertEqual(self.adicionar(("npc", self.npc.pk, 1)).status_code, status.HTTP_201_CREATED)

    def test_jogador_nao_ve_combate_oculto_nem_edita(self):
        self.client.force_authenticate(self.jogador)
        self.assertEqual(self.client.get(self.base).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.adicionar(("npc", self.npc.pk, 1)).status_code, status.HTTP_403_FORBIDDEN)
        resposta = self.client.patch(self.base, {"visivel_para_jogadores": True}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        # A leitura do jogador não cria combate.
        self.assertFalse(Combate.objects.exists())

    def test_jogador_ve_combate_compartilhado_sem_numeros_de_pv(self):
        self.adicionar(("npc", self.npc.pk, 1))
        self.client.patch(self.base, {"visivel_para_jogadores": True}, format="json")
        self.client.force_authenticate(self.jogador)
        dados = self.client.get(self.base).data
        self.assertFalse(dados["pode_gerenciar"])
        linha = dados["participantes"][0]
        self.assertNotIn("pv_atual", linha)
        self.assertEqual(linha["pv_percentual"], 100)

    def test_estranho_e_bloqueado(self):
        self.client.force_authenticate(self.estranho)
        self.assertEqual(self.client.get(self.base).status_code, status.HTTP_403_FORBIDDEN)

    def test_entidade_de_outra_campanha_e_recusada(self):
        outra = Campanha.objects.create(mestre=self.mestre, nome="Outra")
        intruso = NPC.objects.create(campanha=outra, nome="Intruso")
        resposta = self.adicionar(("npc", intruso.pk, 1))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ParticipanteCombate.objects.exists())

    def test_participante_de_outra_campanha_da_404(self):
        outra = Campanha.objects.create(mestre=self.mestre, nome="Outra")
        npc = NPC.objects.create(campanha=outra, nome="Longe")
        combate_outro = combate.obter(outra, criar=True)
        participante = ParticipanteCombate.objects.create(combate=combate_outro, tipo="npc", npc=npc, pv_atual=5)
        resposta = self.client.post(f"{self.base}participantes/{participante.pk}/dano/", {"valor": 1}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)


class ParticipantesTests(CombateBase):

    def test_adiciona_repeticoes_com_pv_da_ficha(self):
        resposta = self.adicionar(("criatura", self.goblin.pk, 3), ("npc", self.npc.pk, 1))
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resposta.data), 4)
        goblins = [linha for linha in resposta.data if linha["tipo"] == "criatura"]
        self.assertEqual({(g["pv_atual"], g["pv_max"], g["nome"]) for g in goblins}, {(7, 7, "Goblin")})
        self.assertEqual(len({g["id"] for g in goblins}), 3)

    def test_adicionar_todos_nao_duplica_personagens(self):
        self.adicionar(("personagem", self.aria.pk, 1))
        resposta = self.client.post(f"{self.base}participantes/", {"todos_personagens": True}, format="json")
        self.assertEqual([linha["entidade_id"] for linha in resposta.data], [self.bram.pk])
        segunda = self.client.post(f"{self.base}participantes/", {"todos_personagens": True}, format="json")
        self.assertEqual(segunda.data, [])
        self.assertEqual(ParticipanteCombate.objects.filter(tipo="personagem").count(), 2)

    def test_ordem_por_iniciativa_com_empate_estavel(self):
        ids = [linha["id"] for linha in self.adicionar(("criatura", self.goblin.pk, 3)).data]
        self.client.patch(f"{self.base}participantes/{ids[2]}/", {"iniciativa": 15}, format="json")
        self.client.patch(f"{self.base}participantes/{ids[0]}/", {"iniciativa": 10}, format="json")
        self.client.patch(f"{self.base}participantes/{ids[1]}/", {"iniciativa": 10}, format="json")
        ordem = [linha["id"] for linha in self.estado()["participantes"]]
        # Empatados em 10: quem entrou antes (id menor) vem antes.
        self.assertEqual(ordem, [ids[2], ids[0], ids[1]])

    def test_patch_incrementa_versao(self):
        linha = self.adicionar(("npc", self.npc.pk, 1)).data[0]
        resposta = self.client.patch(f"{self.base}participantes/{linha['id']}/", {"iniciativa": 12}, format="json")
        self.assertEqual(resposta.data["iniciativa"], 12)
        self.assertEqual(resposta.data["versao"], linha["versao"] + 1)
        self.assertEqual(set(resposta.data), set(combate.CAMPOS_VALORES))

    def test_patch_valida(self):
        linha = self.adicionar(("npc", self.npc.pk, 1)).data[0]
        url = f"{self.base}participantes/{linha['id']}/"
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.patch(url, {"pv_atual": -1}, format="json").status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_remover_selecionados_e_so_personagens(self):
        linhas = self.adicionar(("npc", self.npc.pk, 2), ("personagem", self.aria.pk, 1)).data
        npc_ids = [linha["id"] for linha in linhas if linha["tipo"] == "npc"]
        resposta = self.client.post(f"{self.base}participantes/remover/", {"ids": [npc_ids[0]]}, format="json")
        self.assertEqual(resposta.data["removidos"], [npc_ids[0]])

        resposta = self.client.post(f"{self.base}participantes/remover/", {"escopo": "personagens"}, format="json")
        self.assertEqual(len(resposta.data["removidos"]), 1)
        self.assertEqual([linha["id"] for linha in self.estado()["participantes"]], [npc_ids[1]])

        self.client.post(f"{self.base}participantes/remover/", {"escopo": "todos"}, format="json")
        self.assertEqual(self.estado()["participantes"], [])

    def test_limite_de_participantes(self):
        resposta = self.client.post(
            f"{self.base}participantes/",
            {"entidades": [{"tipo": "criatura", "id": self.goblin.pk, "quantidade": 20}] * 11},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ParticipanteCombate.objects.exists())


class AvulsoTests(CombateBase):

    def test_adiciona_avulso_pelo_nome_sem_pv(self):
        resposta = self.client.post(
            f"{self.base}participantes/",
            {"entidades": [{"tipo": "avulso", "nome": "Bandido aleatório", "quantidade": 1}]},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        linha = resposta.data[0]
        self.assertEqual(linha["tipo"], "avulso")
        self.assertEqual(linha["nome"], "Bandido aleatório")
        self.assertIsNone(linha["foto"])
        self.assertIsNone(linha["pv_atual"])
        self.assertIsNone(linha["pv_max"])
        self.assertEqual(linha["entidade_id"], ParticipanteCombate.objects.get().pk)

    def test_avulso_pode_repetir_quantidade_e_misturar_com_entidades_reais(self):
        resposta = self.client.post(
            f"{self.base}participantes/",
            {
                "entidades": [
                    {"tipo": "npc", "id": self.npc.pk, "quantidade": 1},
                    {"tipo": "avulso", "nome": "Capanga", "quantidade": 2},
                ]
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resposta.data), 3)
        avulsos = [linha for linha in resposta.data if linha["tipo"] == "avulso"]
        self.assertEqual({linha["nome"] for linha in avulsos}, {"Capanga"})
        self.assertEqual(len({linha["id"] for linha in avulsos}), 2)

    def test_avulso_sem_nome_e_recusado(self):
        resposta = self.client.post(
            f"{self.base}participantes/",
            {"entidades": [{"tipo": "avulso", "quantidade": 1}]},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ParticipanteCombate.objects.exists())

    def test_avulso_entra_na_ordem_e_pode_editar_iniciativa_e_pv(self):
        linha = self.client.post(
            f"{self.base}participantes/",
            {"entidades": [{"tipo": "avulso", "nome": "Sombra", "quantidade": 1}]},
            format="json",
        ).data[0]
        resposta = self.client.patch(
            f"{self.base}participantes/{linha['id']}/", {"iniciativa": 18, "pv_atual": 10, "pv_max": 10},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        estado = self.estado()
        self.assertEqual(estado["participantes"][0]["nome"], "Sombra")
        self.assertEqual(estado["participantes"][0]["iniciativa"], 18)


class DanoTests(CombateBase):

    def setUp(self):
        super().setUp()
        self.linha = self.adicionar(("npc", self.npc.pk, 1)).data[0]
        self.url = f"{self.base}participantes/{self.linha['id']}/dano/"

    def test_danos_consecutivos_se_somam(self):
        self.client.post(self.url, {"valor": 5}, format="json")
        resposta = self.client.post(self.url, {"valor": 7}, format="json")
        self.assertEqual(resposta.data["pv_atual"], 28)
        self.assertEqual(resposta.data["versao"], self.linha["versao"] + 2)

    def test_pv_nunca_fica_negativo(self):
        resposta = self.client.post(self.url, {"valor": 999}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["pv_atual"], 0)

    def test_valor_invalido(self):
        for valor in (0, -3, "abc", None):
            self.assertEqual(
                self.client.post(self.url, {"valor": valor}, format="json").status_code,
                status.HTTP_400_BAD_REQUEST,
            )

    def test_personagem_nao_tem_pv_de_combate(self):
        linha = self.adicionar(("personagem", self.aria.pk, 1)).data[0]
        resposta = self.client.post(f"{self.base}participantes/{linha['id']}/dano/", {"valor": 1}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)


class TurnoTests(CombateBase):

    def setUp(self):
        super().setUp()
        linhas = self.adicionar(("criatura", self.goblin.pk, 3)).data
        self.ids = [linha["id"] for linha in linhas]

    def turno(self, acao="proximo"):
        return self.client.post(f"{self.base}turno/", {"acao": acao}, format="json").data

    def test_avanca_e_vira_rodada(self):
        self.assertEqual(self.turno()["turno_participante"], self.ids[0])
        self.turno()
        self.turno()
        dados = self.turno()
        self.assertEqual((dados["turno_participante"], dados["rodada"]), (self.ids[0], 2))
        dados = self.turno("anterior")
        self.assertEqual((dados["turno_participante"], dados["rodada"]), (self.ids[2], 1))

    def test_anterior_na_primeira_rodada_para_no_primeiro(self):
        self.turno()
        dados = self.turno("anterior")
        self.assertEqual((dados["turno_participante"], dados["rodada"]), (self.ids[0], 1))

    def test_mudar_iniciativa_nao_muda_quem_age(self):
        self.turno()
        self.turno()  # ids[1] age
        self.client.patch(f"{self.base}participantes/{self.ids[1]}/", {"iniciativa": 30}, format="json")
        self.assertEqual(self.estado()["combate"]["turno_participante"], self.ids[1])

    def test_remover_quem_age_passa_a_vez(self):
        self.turno()
        self.turno()  # ids[1]
        resposta = self.client.post(f"{self.base}participantes/remover/", {"ids": [self.ids[1]]}, format="json")
        self.assertEqual(resposta.data["combate"]["turno_participante"], self.ids[2])

    def test_remover_ultimo_que_age_vira_rodada(self):
        for _ in range(3):
            self.turno()  # ids[2]
        resposta = self.client.post(f"{self.base}participantes/remover/", {"ids": [self.ids[2]]}, format="json")
        self.assertEqual(
            (resposta.data["combate"]["turno_participante"], resposta.data["combate"]["rodada"]), (self.ids[0], 2)
        )

    def test_esvaziar_volta_a_rodada_um(self):
        for _ in range(4):
            self.turno()
        resposta = self.client.post(f"{self.base}participantes/remover/", {"escopo": "todos"}, format="json")
        self.assertEqual((resposta.data["combate"]["rodada"], resposta.data["combate"]["turno_participante"]), (1, None))

    def test_reiniciar(self):
        for _ in range(4):
            self.turno()
        dados = self.client.post(f"{self.base}reiniciar/").data
        self.assertEqual((dados["rodada"], dados["turno_participante"]), (1, None))

    def test_sem_participantes_e_erro(self):
        self.client.post(f"{self.base}participantes/remover/", {"escopo": "todos"}, format="json")
        resposta = self.client.post(f"{self.base}turno/", {"acao": "proximo"}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)


class CascataTests(CombateBase):

    def test_excluir_entidade_que_age_passa_a_vez(self):
        npc = self.adicionar(("npc", self.npc.pk, 1)).data[0]
        goblin = self.adicionar(("criatura", self.goblin.pk, 1)).data[0]
        self.client.post(f"{self.base}turno/", {"acao": "proximo"}, format="json")  # npc age
        self.npc.delete()
        dados = self.estado()
        self.assertEqual([linha["id"] for linha in dados["participantes"]], [goblin["id"]])
        self.assertEqual(dados["combate"]["turno_participante"], goblin["id"])
        self.assertFalse(ParticipanteCombate.objects.filter(pk=npc["id"]).exists())

    def test_personagem_que_sai_da_campanha_sai_do_combate(self):
        self.adicionar(("personagem", self.aria.pk, 1), ("personagem", self.bram.pk, 1))
        self.campanha.personagens.remove(self.aria)
        nomes = [linha["nome"] for linha in self.estado()["participantes"]]
        self.assertEqual(nomes, ["Bram"])

    def test_excluir_campanha_nao_quebra(self):
        self.adicionar(("npc", self.npc.pk, 1), ("personagem", self.aria.pk, 1))
        self.client.post(f"{self.base}turno/", {"acao": "proximo"}, format="json")
        self.campanha.delete()
        self.assertFalse(Combate.objects.exists())


@override_settings(CHANNEL_LAYERS=CAMADA_MEMORIA)
class EventosTests(CombateBase):

    def setUp(self):
        super().setUp()
        self.camada = get_channel_layer()
        self.canal = async_to_sync(self.camada.new_channel)()
        async_to_sync(self.camada.group_add)(nome_grupo(self.campanha.pk), self.canal)

    def receber(self):
        async def _receber():
            try:
                return await asyncio.wait_for(self.camada.receive(self.canal), 0.2)
            except asyncio.TimeoutError:
                return None

        mensagem = async_to_sync(_receber)()
        return mensagem["evento"] if mensagem else None

    def test_eventos_publicados_apos_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            linhas = self.adicionar(("npc", self.npc.pk, 1)).data
        evento = self.receber()
        self.assertEqual(evento["tipo"], "combate_participantes")
        self.assertEqual(evento["dados"][0]["id"], linhas[0]["id"])

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{self.base}participantes/{linhas[0]['id']}/dano/", {"valor": 4}, format="json")
        evento = self.receber()
        self.assertEqual((evento["tipo"], evento["dados"]["pv_atual"]), ("combate_valores", 36))

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{self.base}participantes/remover/", {"escopo": "todos"}, format="json")
        self.assertEqual(self.receber(), {"tipo": "combate_removidos", "ids": [linhas[0]["id"]]})
