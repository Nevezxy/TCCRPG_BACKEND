"""
Escudo do Mestre: snapshot, versionamento e eventos em tempo real.

O channel layer em memória é fixado aqui (e não herdado do ambiente) para o
teste nunca depender de um Redis de verdade.
"""

import asyncio
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from Personagem.models import Arma, Atributo, Bonus, Defesa, Personagem, Status
from Usuario.models import Usuario

from . import consumers
from .escudo import nome_grupo
from .models import Campanha
from .routing import websocket_urlpatterns

CAMADA_MEMORIA = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def _bonus(alvo, valor, **extra):
    return Bonus.objects.create(
        content_type=ContentType.objects.get_for_model(type(alvo)),
        object_id=alvo.pk,
        nome="Bônus",
        valor=valor,
        **extra,
    )


@override_settings(CHANNEL_LAYERS=CAMADA_MEMORIA)
class EscudoBase(APITestCase):

    def setUp(self):
        self.mestre = Usuario.objects.create_user(username="mestre", password="SenhaForte123!")
        self.jogador = Usuario.objects.create_user(username="jogador", password="SenhaForte123!")
        self.estranho = Usuario.objects.create_user(username="estranho", password="SenhaForte123!")

        self.campanha = Campanha.objects.create(mestre=self.mestre, nome="Mesa")
        self.campanha.jogadores.add(self.jogador)

        self.personagem = Personagem.objects.create(usuario=self.jogador, nome="Aria", nivel=3)
        self.campanha.personagens.add(self.personagem)
        self.atributo = Atributo.objects.create(personagem=self.personagem, nome="Vig", valor=2)
        self.vida = Status.objects.create(
            personagem=self.personagem, nome="Pontos de Vida", barra=True, valor_max=20, valor_atual=20
        )
        self.ca = Defesa.objects.create(personagem=self.personagem, nome="Classe de Armadura", valor=14)

        # As linhas criadas acima enfileiram callbacks de `on_commit` que,
        # num TestCase, NUNCA rodam — a transação é desfeita no fim. Numa
        # requisição de verdade o commit os executa e esvazia a fila; aqui
        # esvaziamos à mão, para cada teste partir do mesmo estado. Sem isto,
        # a deduplicação de `_agendar_ficha` enxerga um agendamento fantasma
        # da própria setUp e engole os eventos do teste.
        connection.run_on_commit.clear()

        self.camada = get_channel_layer()
        self.canal = async_to_sync(self.camada.new_channel)()
        async_to_sync(self.camada.group_add)(nome_grupo(self.campanha.pk), self.canal)

    def receber(self, espera=0.2):
        async def _receber():
            try:
                return await asyncio.wait_for(self.camada.receive(self.canal), espera)
            except asyncio.TimeoutError:
                return None

        mensagem = async_to_sync(_receber)()
        return mensagem["evento"] if mensagem else None

    def receber_todos(self):
        eventos = []
        while (evento := self.receber()) is not None:
            eventos.append(evento)
        return eventos


class VersionamentoTests(EscudoBase):

    def test_save_incrementa_versao_no_proprio_update(self):
        self.assertEqual(self.vida.versao, 1)
        self.vida.valor_atual = 19
        with CaptureQueriesContext(connection) as consultas:
            self.vida.save()
        # O valor volta pelo RETURNING do UPDATE: é um int, não uma expressão
        # F() pendurada, e não custou uma consulta de releitura.
        self.assertEqual(self.vida.versao, 2)
        self.assertEqual(len([q for q in consultas if q["sql"].startswith("UPDATE")]), 1)
        self.assertFalse(any(q["sql"].startswith("SELECT") for q in consultas))

    def test_save_com_update_fields_tambem_versiona(self):
        self.vida.valor_atual = 5
        self.vida.save(update_fields=["valor_atual"])
        self.vida.refresh_from_db()
        self.assertEqual((self.vida.valor_atual, self.vida.versao), (5, 2))


class SnapshotTests(EscudoBase):

    def url(self):
        return f"/campanha/{self.campanha.pk}/escudo/"

    def test_participante_recebe_tudo_numa_requisicao(self):
        _bonus(self.vida, 5)
        arma = Arma.objects.create(personagem=self.personagem, nome="Espada")
        _bonus(arma, 99)  # alvo que o Escudo não exibe: fica de fora

        self.client.force_authenticate(user=self.jogador)
        resposta = self.client.get(self.url())

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        [p] = resposta.data["personagens"]
        self.assertEqual((p["id"], p["nome"], p["nivel"]), (self.personagem.pk, "Aria", 3))
        self.assertEqual([s["valor_atual"] for s in p["status"]], [20])
        self.assertEqual([a["nome"] for a in p["atributos"]], ["Vig"])
        self.assertEqual([d["valor"] for d in p["defesas"]], [14])
        self.assertEqual([(b["tipo"], b["valor"]) for b in p["bonus"]], [("status", 5)])
        self.assertIn("versao", p["status"][0])

    def test_nao_participante_nao_ve(self):
        self.client.force_authenticate(user=self.estranho)
        self.assertEqual(self.client.get(self.url()).status_code, status.HTTP_403_FORBIDDEN)

    def test_numero_de_consultas_nao_cresce_com_personagens(self):
        self.client.force_authenticate(user=self.mestre)
        with CaptureQueriesContext(connection) as com_um:
            self.client.get(self.url())

        for i in range(3):
            outro = Personagem.objects.create(usuario=self.jogador, nome=f"Extra {i}")
            self.campanha.personagens.add(outro)
            vida = Status.objects.create(personagem=outro, nome="PV", barra=True, valor_max=10, valor_atual=10)
            _bonus(vida, 1)
            Atributo.objects.create(personagem=outro, nome="For", valor=1)

        with CaptureQueriesContext(connection) as com_quatro:
            resposta = self.client.get(self.url())

        self.assertEqual(len(resposta.data["personagens"]), 4)
        self.assertEqual(len(com_quatro), len(com_um))


class OrdemTests(EscudoBase):
    """Ordem dos cards no Escudo, arrumada pelo mestre."""

    def setUp(self):
        super().setUp()
        self.bram = Personagem.objects.create(usuario=self.jogador, nome="Bram", nivel=2)
        self.cassia = Personagem.objects.create(usuario=self.jogador, nome="Cassia", nivel=2)
        self.campanha.personagens.add(self.bram, self.cassia)
        self.receber_todos()

    def ordenar(self, ids, usuario=None):
        self.client.force_authenticate(user=usuario or self.mestre)
        return self.client.put(f"/campanha/{self.campanha.pk}/escudo/ordem/", {"ids": ids}, format="json")

    def ids_do_snapshot(self):
        self.client.force_authenticate(user=self.jogador)
        dados = self.client.get(f"/campanha/{self.campanha.pk}/escudo/").data
        self.assertEqual(dados["ordem"], [p["id"] for p in dados["personagens"]])
        return dados["ordem"]

    def test_sem_ordem_definida_segue_o_id(self):
        self.assertEqual(self.ids_do_snapshot(), [self.personagem.pk, self.bram.pk, self.cassia.pk])

    def test_mestre_reordena_e_a_mesa_inteira_ve_a_nova_ordem(self):
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.ordenar([self.cassia.pk, self.personagem.pk, self.bram.pk])

        self.assertEqual(resposta.status_code, status.HTTP_200_OK, resposta.data)
        esperada = [self.cassia.pk, self.personagem.pk, self.bram.pk]
        self.assertEqual(resposta.data["ordem"], esperada)
        self.assertEqual(self.receber(), {"tipo": "ordem", "ids": esperada})
        self.assertEqual(self.ids_do_snapshot(), esperada)

    def test_lista_parcial_completa_com_os_que_faltaram_no_fim(self):
        resposta = self.ordenar([self.cassia.pk])
        self.assertEqual(resposta.data["ordem"], [self.cassia.pk, self.personagem.pk, self.bram.pk])

    def test_quem_entra_depois_vai_para_o_fim_e_quem_sai_some(self):
        self.ordenar([self.cassia.pk, self.bram.pk, self.personagem.pk])
        novo = Personagem.objects.create(usuario=self.jogador, nome="Dario", nivel=1)
        self.campanha.personagens.add(novo)
        self.campanha.personagens.remove(self.bram)
        self.assertEqual(self.ids_do_snapshot(), [self.cassia.pk, self.personagem.pk, novo.pk])

    def test_jogador_nao_reordena(self):
        self.assertEqual(self.ordenar([self.bram.pk], usuario=self.jogador).status_code, status.HTTP_403_FORBIDDEN)

    def test_ids_invalidos_sao_recusados(self):
        outro = Personagem.objects.create(usuario=self.estranho, nome="Intruso", nivel=1)
        for ids in ([outro.pk], [self.bram.pk, self.bram.pk], "abc", [True]):
            self.assertEqual(self.ordenar(ids).status_code, status.HTTP_400_BAD_REQUEST, ids)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.escudo_ordem, [])

    def test_patch_da_campanha_nao_altera_a_ordem(self):
        self.client.force_authenticate(user=self.mestre)
        self.client.patch(f"/campanha/{self.campanha.pk}/", {"escudo_ordem": [self.bram.pk]}, format="json")
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.escudo_ordem, [])


class EventosTests(EscudoBase):

    def test_patch_de_status_publica_so_a_linha_alterada(self):
        self.client.force_authenticate(user=self.jogador)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f"/personagem/status/{self.vida.pk}/", {"valor_atual": 19}, format="json")

        evento = self.receber()
        self.assertEqual(evento["tipo"], "upsert")
        self.assertEqual(evento["entidade"], "status")
        self.assertEqual(evento["personagem"], self.personagem.pk)
        self.assertEqual((evento["dados"]["id"], evento["dados"]["valor_atual"]), (self.vida.pk, 19))
        self.assertEqual(evento["dados"]["versao"], 2)
        self.assertIsNone(self.receber())

    def test_gravacao_sem_mudanca_visivel_nao_gera_evento(self):
        self.client.force_authenticate(user=self.jogador)
        with self.captureOnCommitCallbacks(execute=True):
            # Anotações não aparecem no Escudo.
            self.client.patch(f"/personagem/{self.personagem.pk}/", {"anotacoes": "texto"}, format="json")
            # Mesmo valor que já estava gravado.
            self.client.patch(f"/personagem/status/{self.vida.pk}/", {"valor_atual": 20}, format="json")
        self.assertIsNone(self.receber())

    def test_nome_do_personagem_publica_resumo(self):
        self.client.force_authenticate(user=self.jogador)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.patch(f"/personagem/{self.personagem.pk}/", {"nivel": 4}, format="json")
        evento = self.receber()
        self.assertEqual((evento["entidade"], evento["dados"]["nivel"]), ("personagem", 4))

    def test_bonus_de_alvo_exibido_e_ignorado_para_os_demais(self):
        arma = Arma.objects.create(personagem=self.personagem, nome="Espada")
        with self.captureOnCommitCallbacks(execute=True):
            _bonus(arma, 3)
            bonus = _bonus(self.ca, 2)

        eventos = self.receber_todos()

        # Só o bônus da Defesa gera evento de BÔNUS — o da Arma é de um alvo
        # que o Escudo não exibe.
        de_bonus = [e for e in eventos if e["entidade"] == "bonus"]
        self.assertEqual(
            [(e["entidade"], e["dados"]["tipo"]) for e in de_bonus],
            [("bonus", "defesa")],
        )

        # E o alvo é republicado com o total já recalculado: `valor_final` é
        # derivado, então a linha da Defesa muda sem a `versao` dela subir —
        # sem este reenvio o Escudo ficaria com o total velho até reconectar.
        defesa = next(
            e for e in eventos if e["entidade"] == "defesa" and e["dados"]["id"] == self.ca.pk
        )
        self.assertEqual(defesa["dados"]["valor_final"], self.ca.valor + 2)

        pk = bonus.pk
        with self.captureOnCommitCallbacks(execute=True):
            bonus.delete()
        eventos = self.receber_todos()
        remocao = next(e for e in eventos if e["entidade"] == "bonus")
        self.assertEqual((remocao["tipo"], remocao["id"]), ("remover", pk))
        # Removido o bônus, o total do alvo volta ao que era.
        defesa = next(
            e for e in eventos if e["entidade"] == "defesa" and e["dados"]["id"] == self.ca.pk
        )
        self.assertEqual(defesa["dados"]["valor_final"], self.ca.valor)

    def test_recalculo_vem_marcado_para_o_cliente_nao_descartar(self):
        """
        A `versao` de uma linha recalculada NÃO muda — ela não foi gravada; o
        que mudou foi um total derivado dela. Sem a marca `recalculo`, o
        cliente aplicaria a regra normal ("só aceito versão maior") e
        descartaria o evento em silêncio, deixando o Escudo com o número
        velho até a reconexão. Era o que acontecia.
        """
        versao_antes = self.ca.versao
        with self.captureOnCommitCallbacks(execute=True):
            _bonus(self.ca, 4)

        defesa = next(
            e for e in self.receber_todos()
            if e["entidade"] == "defesa" and e["dados"]["id"] == self.ca.pk
        )
        self.assertTrue(defesa.get("recalculo"))
        self.assertEqual(defesa["dados"]["versao"], versao_antes)
        self.assertEqual(defesa["dados"]["valor_final"], self.ca.valor + 4)

    def test_mudar_a_origem_do_bonus_republica_o_alvo(self):
        """
        Uma Técnica não aparece no Escudo, mas o `valor_final` dela pode ser
        a origem do bônus de uma Defesa que aparece. Antes, mexer na Técnica
        não gerava evento nenhum.
        """
        from Personagem.models import Tecnica

        tecnica = Tecnica.objects.create(personagem=self.personagem, nome="Foco", valor_final=2)
        # Dentro do bloco de captura porque criar o bônus também agenda uma
        # republicação: deixá-la pendente bloquearia (pela deduplicação) a
        # que o save da Técnica deve disparar logo abaixo.
        with self.captureOnCommitCallbacks(execute=True):
            Bonus.objects.create(
                content_type=ContentType.objects.get_for_model(Defesa),
                object_id=self.ca.pk,
                nome="Foco",
                tipo_origem=Bonus.TIPO_ENTIDADE,
                origem_content_type=ContentType.objects.get_for_model(Tecnica),
                origem_object_id=tecnica.pk,
            )
        self.receber_todos()

        with self.captureOnCommitCallbacks(execute=True):
            tecnica.valor_final = 7
            tecnica.save()

        defesa = next(
            e for e in self.receber_todos()
            if e["entidade"] == "defesa" and e["dados"]["id"] == self.ca.pk
        )
        self.assertEqual(defesa["dados"]["valor_final"], self.ca.valor + 7)

    def test_entidade_que_nao_e_origem_de_nada_nao_gera_evento(self):
        """A trava contra spam: a maioria dos itens de um inventário não é
        origem de bônus nenhum, e para esses não sai mensagem alguma."""
        from Personagem.models import Item

        item = Item.objects.create(personagem=self.personagem, nome="Corda", valor_final=3)
        self.receber_todos()

        with self.captureOnCommitCallbacks(execute=True):
            item.valor_final = 9
            item.save()

        self.assertIsNone(self.receber())

    def test_varios_bonus_de_uma_vez_publicam_a_ficha_uma_vez_so(self):
        """O botão "Usar" liga vários bônus numa transação só. Sem a
        deduplicação, a ficha inteira ia pelo WebSocket uma vez por bônus."""
        with self.captureOnCommitCallbacks(execute=True):
            _bonus(self.ca, 1)
            _bonus(self.vida, 2)
            _bonus(self.atributo, 3)

        eventos = self.receber_todos()
        defesas = [e for e in eventos if e["entidade"] == "defesa" and e["dados"]["id"] == self.ca.pk]
        self.assertEqual(len(defesas), 1, [e["entidade"] for e in eventos])

    def test_exclusao_de_status(self):
        pk = self.vida.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.vida.delete()
        evento = self.receber()
        self.assertEqual((evento["tipo"], evento["entidade"], evento["id"]), ("remover", "status", pk))

    def test_personagem_fora_de_campanha_nao_publica(self):
        solto = Personagem.objects.create(usuario=self.jogador, nome="Solto")
        with self.captureOnCommitCallbacks(execute=True):
            Status.objects.create(personagem=solto, nome="PV", valor_max=1, valor_atual=1)
        self.assertIsNone(self.receber())

    def test_entrada_e_saida_de_personagem(self):
        novo = Personagem.objects.create(usuario=self.jogador, nome="Novo")
        Status.objects.create(personagem=novo, nome="PV", barra=True, valor_max=8, valor_atual=8)
        self.receber_todos()

        with self.captureOnCommitCallbacks(execute=True):
            self.campanha.personagens.add(novo)
        evento = self.receber()
        self.assertEqual(evento["tipo"], "personagem_entrou")
        self.assertEqual([s["valor_max"] for s in evento["dados"]["status"]], [8])

        with self.captureOnCommitCallbacks(execute=True):
            novo.campanhas.remove(self.campanha)  # lado reverso do M2M
        self.assertEqual(self.receber(), {"tipo": "personagem_saiu", "personagem": novo.pk})

    def test_excluir_personagem_publica_so_a_saida(self):
        pk = self.personagem.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.personagem.delete()
        # Os Status/Atributos/Defesas apagados em cascata não geram eventos.
        self.assertEqual(self.receber_todos(), [{"tipo": "personagem_saiu", "personagem": pk}])

    def test_jogador_removido_recebe_revogacao(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.campanha.jogadores.remove(self.jogador)
        self.assertEqual(self.receber(), {"tipo": "acesso_revogado", "usuarios": [self.jogador.pk]})


class AutorizacaoTests(EscudoBase):
    """A regra de acesso do WebSocket (a parte síncrona, que consulta o banco)."""

    def autorizar(self, usuario_id):
        return consumers._autorizar.func(usuario_id, self.campanha.pk)

    def test_participantes_passam(self):
        # (código, gerencia, combate visível): só o mestre gerencia.
        self.assertEqual(self.autorizar(self.mestre.pk), (None, True, False))
        self.assertEqual(self.autorizar(self.jogador.pk), (None, False, False))

    def test_estranho_e_campanha_inexistente(self):
        self.assertEqual(self.autorizar(self.estranho.pk)[0], consumers.FECHA_PROIBIDO)
        self.assertEqual(consumers._autorizar.func(self.mestre.pk, 999999)[0], consumers.FECHA_NAO_ENCONTRADO)


@override_settings(CHANNEL_LAYERS=CAMADA_MEMORIA)
class ConsumerTests(SimpleTestCase):
    """
    Fluxo do WebSocket de ponta a ponta, SEM banco: a consulta de autorização
    é substituída (ela é coberta em `AutorizacaoTests`). O Channels fecha as
    conexões "velhas" do banco a cada mensagem do consumer — dentro da
    transação de um TestCase isso derrubaria a conexão do próprio teste.
    """

    def setUp(self):
        # Não salvo: o token só precisa do id.
        self.usuario = Usuario(pk=4242, username="ws")
        self.token = str(AccessToken.for_user(self.usuario))

    def rodar(self, corrotina):
        async_to_sync(corrotina)()

    def conectar(self, campanha_id=7):
        return WebsocketCommunicator(URLRouter(websocket_urlpatterns), f"/ws/campanha/{campanha_id}/escudo/")

    @staticmethod
    def autorizacao(resultado, gerencia=False, visivel=False):
        async def falso(_user_id, _campanha_id):
            return resultado, gerencia, visivel

        return mock.patch.object(consumers, "_autorizar", falso)

    def test_token_invalido_fecha_com_4401(self):
        async def fluxo():
            ws = self.conectar()
            await ws.connect()
            await ws.send_json_to({"tipo": "auth", "token": "lixo"})
            saida = await ws.receive_output()
            self.assertEqual((saida["type"], saida["code"]), ("websocket.close", 4401))

        self.rodar(fluxo)

    def test_nao_participante_fecha_com_4403(self):
        async def fluxo():
            ws = self.conectar()
            await ws.connect()
            await ws.send_json_to({"tipo": "auth", "token": self.token})
            saida = await ws.receive_output()
            self.assertEqual(saida["code"], 4403)

        with self.autorizacao(consumers.FECHA_PROIBIDO):
            self.rodar(fluxo)

    def test_participante_recebe_pronto_e_eventos(self):
        async def fluxo():
            ws = self.conectar()
            await ws.connect()
            await ws.send_json_to({"tipo": "auth", "token": self.token})
            self.assertEqual(await ws.receive_json_from(), {"tipo": "pronto"})

            camada = get_channel_layer()
            evento = {"tipo": "upsert", "entidade": "status", "personagem": 1, "dados": {"id": 1}}
            await camada.group_send(nome_grupo(7), {"type": "escudo.evento", "evento": evento})
            self.assertEqual(await ws.receive_json_from(), evento)

            await ws.send_json_to({"tipo": "ping"})
            self.assertEqual(await ws.receive_json_from(), {"tipo": "pong"})

            # Revogação de OUTRO usuário não afeta esta conexão...
            revoga_outro = {"tipo": "acesso_revogado", "usuarios": [self.usuario.pk + 1]}
            await camada.group_send(nome_grupo(7), {"type": "escudo.evento", "evento": revoga_outro})
            self.assertTrue(await ws.receive_nothing(0.1))
            # ...a dele encerra.
            revoga = {"tipo": "acesso_revogado", "usuarios": [self.usuario.pk]}
            await camada.group_send(nome_grupo(7), {"type": "escudo.evento", "evento": revoga})
            self.assertEqual((await ws.receive_output())["code"], 4403)

        with self.autorizacao(None):
            self.rodar(fluxo)

    def test_sem_autenticacao_no_prazo_fecha(self):
        async def fluxo():
            ws = self.conectar()
            await ws.connect()
            saida = await ws.receive_output(timeout=1)
            self.assertEqual(saida["code"], 4401)

        with mock.patch.object(consumers, "PRAZO_AUTENTICACAO", 0.05):
            self.rodar(fluxo)
