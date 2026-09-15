from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from Usuario.models import Usuario
from Personagem.models import Personagem
from Sistema.models import Sistema
from Personagem.models import Arma, Armadura, Item
from Sistema.models import ArmaduraSistema, ArmaSistema, ItemSistema
from . import loja
from .models import (
    Campanha, NPC, Local, Organizacao, Pasta, TipoConexao, Conexao, Imagem,
    ItemCampanha, ArmaCampanha, ArmaduraCampanha,
    CategoriaLoja, ProdutoLoja,
)


class DuasCampanhasTestCase(APITestCase):
    """
    Base comum: duas campanhas totalmente independentes (mestres,
    jogadores, NPCs e pastas distintos), usada por praticamente todos os
    testes abaixo para garantir que nada de uma campanha vaza para/
    interfere na outra (seção 16: "bloqueio de entidades de campanhas
    diferentes").

    Campanha A: mestre `mestre_a`, jogador `jogador_a`, NPC `npc_a1`.
    Campanha B: mestre `mestre_b`, jogador `jogador_b`, NPC `npc_b1`.
    """

    def setUp(self):
        self.mestre_a = Usuario.objects.create_user(username="mestre_a", password="SenhaForte123!")
        self.jogador_a = Usuario.objects.create_user(username="jogador_a", password="SenhaForte123!")
        self.mestre_b = Usuario.objects.create_user(username="mestre_b", password="SenhaForte123!")
        self.jogador_b = Usuario.objects.create_user(username="jogador_b", password="SenhaForte123!")

        self.campanha_a = Campanha.objects.create(mestre=self.mestre_a, nome="Campanha A")
        self.campanha_a.jogadores.add(self.mestre_a, self.jogador_a)

        self.campanha_b = Campanha.objects.create(mestre=self.mestre_b, nome="Campanha B")
        self.campanha_b.jogadores.add(self.mestre_b, self.jogador_b)

        self.npc_a1 = NPC.objects.create(campanha=self.campanha_a, nome="Arkan")
        self.npc_a2 = NPC.objects.create(campanha=self.campanha_a, nome="Maria")
        self.npc_b1 = NPC.objects.create(campanha=self.campanha_b, nome="Estranho")

    def autentica_como(self, usuario):
        self.client.force_authenticate(user=usuario)


# ---------------------------------------------------------------------------
# Pasta
# ---------------------------------------------------------------------------

class PastaTests(DuasCampanhasTestCase):

    def test_mestre_cria_pasta_raiz(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/pastas/",
            {"nome": "Mundo"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["nome"], "Mundo")
        self.assertIsNone(response.data["pasta_pai"])

    def test_mestre_cria_subpasta(self):
        self.autentica_como(self.mestre_a)

        raiz = Pasta.objects.create(campanha=self.campanha_a, nome="Mundo")

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/pastas/",
            {"nome": "Regiões", "pasta_pai": raiz.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["pasta_pai"], raiz.id)

    def test_editar_renomear_pasta(self):
        self.autentica_como(self.mestre_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Antigo Nome")

        response = self.client.patch(
            f"/campanha/pastas/{pasta.id}/",
            {"nome": "Novo Nome"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nome"], "Novo Nome")

    def test_excluir_pasta(self):
        self.autentica_como(self.mestre_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Descartável")

        response = self.client.delete(f"/campanha/pastas/{pasta.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Pasta.objects.filter(pk=pasta.id).exists())

    def test_ordenacao_via_campo_ordem(self):
        self.autentica_como(self.mestre_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Sessões", ordem=5)

        response = self.client.patch(
            f"/campanha/pastas/{pasta.id}/",
            {"ordem": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["ordem"], 1)

    def test_mover_pasta_endpoint_dedicado(self):
        self.autentica_como(self.mestre_a)

        destino = Pasta.objects.create(campanha=self.campanha_a, nome="Destino")
        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Origem")

        response = self.client.post(
            f"/campanha/pastas/{pasta.id}/mover/",
            {"pasta_pai": destino.id, "ordem": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pasta_pai"], destino.id)
        self.assertEqual(response.data["ordem"], 3)

    def test_previne_ciclo_direto(self):
        """Uma pasta não pode ser pai de si mesma."""
        self.autentica_como(self.mestre_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Sozinha")

        response = self.client.patch(
            f"/campanha/pastas/{pasta.id}/",
            {"pasta_pai": pasta.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_previne_ciclo_indireto(self):
        """
        Mundo > Regiões > Cidades — tentar tornar "Mundo" filho de
        "Cidades" (sua própria descendente) deve ser rejeitado (seção 5 da
        tarefa de refatoração).
        """
        self.autentica_como(self.mestre_a)

        mundo = Pasta.objects.create(campanha=self.campanha_a, nome="Mundo")
        regioes = Pasta.objects.create(campanha=self.campanha_a, nome="Regiões", pasta_pai=mundo)
        cidades = Pasta.objects.create(campanha=self.campanha_a, nome="Cidades", pasta_pai=regioes)

        response = self.client.patch(
            f"/campanha/pastas/{mundo.id}/",
            {"pasta_pai": cidades.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        mundo.refresh_from_db()
        self.assertIsNone(mundo.pasta_pai)

    def test_pasta_pai_precisa_pertencer_a_mesma_campanha(self):
        self.autentica_como(self.mestre_a)

        pasta_da_b = Pasta.objects.create(campanha=self.campanha_b, nome="Pasta de B")

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/pastas/",
            {"nome": "Nova", "pasta_pai": pasta_da_b.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_entidade_nao_pode_receber_pasta_de_outra_campanha(self):
        """
        Seção 5: um NPC da Campanha A não pode ser associado a uma pasta
        da Campanha B.
        """
        self.autentica_como(self.mestre_a)

        pasta_da_b = Pasta.objects.create(campanha=self.campanha_b, nome="Pasta de B")

        response = self.client.patch(
            f"/campanha/npcs/{self.npc_a1.id}/",
            {"pasta": pasta_da_b.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.npc_a1.refresh_from_db()
        self.assertIsNone(self.npc_a1.pasta)

    def test_entidade_pode_ficar_sem_pasta(self):
        self.autentica_como(self.mestre_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Temporária")
        self.npc_a1.pasta = pasta
        self.npc_a1.save(update_fields=["pasta"])

        response = self.client.patch(
            f"/campanha/npcs/{self.npc_a1.id}/",
            {"pasta": None},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["pasta"])

    # --- Permissões ---

    def test_jogador_nao_pode_criar_pasta(self):
        self.autentica_como(self.jogador_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/pastas/",
            {"nome": "Tentativa"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_jogador_nao_pode_editar_pasta(self):
        self.autentica_como(self.jogador_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Protegida")

        response = self.client.patch(
            f"/campanha/pastas/{pasta.id}/",
            {"nome": "Hackeada"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_jogador_nao_pode_excluir_pasta(self):
        self.autentica_como(self.jogador_a)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Protegida")

        response = self.client.delete(f"/campanha/pastas/{pasta.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Pasta.objects.filter(pk=pasta.id).exists())

    def test_jogador_de_outra_campanha_nao_acessa_pastas_de_a(self):
        """IDOR/BOLA: jogador_b não participa da Campanha A."""
        self.autentica_como(self.jogador_b)

        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Privada")

        response = self.client.get(f"/campanha/pastas/{pasta.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_mestre_de_b_nao_cria_pasta_na_campanha_a(self):
        """IDOR/BOLA: mestre só manda na própria campanha."""
        self.autentica_como(self.mestre_b)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/pastas/",
            {"nome": "Invasão"},
            format="json",
        )

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))


# ---------------------------------------------------------------------------
# Conteúdo em Markdown (`conteudo`)
# ---------------------------------------------------------------------------

class ConteudoMarkdownTests(DuasCampanhasTestCase):

    def test_serializer_aceita_e_devolve_conteudo(self):
        self.autentica_como(self.mestre_a)

        markdown = "## Aparência\n\nAlto e sombrio.\n\n## Segredo\n\nÉ um espião."

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/npcs/",
            {"nome": "Sombra", "conteudo": markdown},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["conteudo"], markdown)

        npc = NPC.objects.get(pk=response.data["id"])
        self.assertEqual(npc.conteudo, markdown)

    def test_api_retorna_conteudo_no_get(self):
        npc = NPC.objects.create(
            campanha=self.campanha_a, nome="Testado", conteudo="## Nota\n\nAlgo"
        )

        self.autentica_como(self.mestre_a)

        response = self.client.get(f"/campanha/npcs/{npc.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["conteudo"], "## Nota\n\nAlgo")

    def test_conteudo_pode_ficar_em_branco(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/npcs/",
            {"nome": "Vazio"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["conteudo"], "")

    def test_campos_narrativos_antigos_nao_existem_mais_no_modelo(self):
        """
        Confirma que o consolidamento em `conteudo` de fato substituiu os
        campos antigos (e não apenas os manteve em paralelo).
        """
        campos_do_model = {f.name for f in NPC._meta.get_fields()}

        for campo_antigo in (
            "aparencia", "personalidade", "familia", "maior_desejo",
            "maior_prazer", "peculiaridade", "ocupacao", "status_social",
            "segredo", "anotacoes",
        ):
            self.assertNotIn(campo_antigo, campos_do_model)

        self.assertIn("conteudo", campos_do_model)

    def test_local_organizacao_tambem_tem_conteudo(self):
        """Mesma consolidação em outras entidades além de NPC."""
        local = Local.objects.create(campanha=self.campanha_a, nome="Vila", conteudo="## Clima\n\nFrio")
        organizacao = Organizacao.objects.create(
            campanha=self.campanha_a, nome="Guilda", conteudo="## História\n\nAntiga"
        )

        self.assertEqual(local.conteudo, "## Clima\n\nFrio")
        self.assertEqual(organizacao.conteudo, "## História\n\nAntiga")


# ---------------------------------------------------------------------------
# Conexao / TipoConexao
# ---------------------------------------------------------------------------

class ConexaoTests(DuasCampanhasTestCase):

    def setUp(self):
        super().setUp()

        self.tipo_amigo = TipoConexao.objects.create(nome="Amigo de")

        self.tipo_filho = TipoConexao.objects.create(nome="Filho de")
        self.tipo_mae = TipoConexao.objects.create(nome="Mãe de", inverso=self.tipo_filho)
        self.tipo_filho.inverso = self.tipo_mae
        self.tipo_filho.save(update_fields=["inverso"])

        self.organizacao_a = Organizacao.objects.create(campanha=self.campanha_a, nome="Guilda dos Magos")

        self.usuario_com_personagem = self.jogador_a
        self.personagem_a = Personagem.objects.create(usuario=self.jogador_a, nome="Arkan (PJ)")
        self.campanha_a.personagens.add(self.personagem_a)

    def _cria_conexao(self, cliente, campanha, entidade1, entidade2, tipo, **extra):
        payload = {
            "entidade1_tipo": entidade1._meta.model_name,
            "entidade1_id": entidade1.id,
            "entidade2_tipo": entidade2._meta.model_name,
            "entidade2_id": entidade2.id,
            "tipo": tipo.id,
        }
        payload.update(extra)

        return cliente.post(f"/campanha/{campanha.id}/conexoes/", payload, format="json")

    # --- Combinações válidas ---

    def test_conexao_npc_npc(self):
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_conexao_npc_personagem(self):
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.personagem_a, self.npc_a1, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_conexao_npc_organizacao(self):
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.organizacao_a, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_conexao_personagem_organizacao(self):
        """Substitui o antigo MembroOrganizacao."""
        self.autentica_como(self.mestre_a)

        tipo_membro = TipoConexao.objects.create(nome="Membro de")

        response = self._cria_conexao(
            self.client, self.campanha_a, self.personagem_a, self.organizacao_a, tipo_membro,
            descricao="## Cargo\n\nBibliotecário",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["descricao"], "## Cargo\n\nBibliotecário")

    def test_conexao_entidade_e_sessao(self):
        from .models import Sessao
        from django.utils import timezone

        sessao = Sessao.objects.create(
            campanha=self.campanha_a, numero=1, titulo="A Fuga", data=timezone.now()
        )

        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, sessao, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # --- Mesma campanha / bloqueio cross-campanha ---

    def test_conexao_bloqueada_entre_campanhas_diferentes(self):
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_b1, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Conexao.objects.exists())

    def test_conexao_nao_pode_ligar_entidade_a_si_mesma(self):
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a1, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Tipos de conexão / relações inversas ---

    def test_tipo_conexao_pode_ter_inverso(self):
        self.assertEqual(self.tipo_filho.inverso, self.tipo_mae)
        self.assertEqual(self.tipo_mae.inverso, self.tipo_filho)

    def test_conexao_nao_e_automaticamente_bidirecional(self):
        """
        Criar "João -> Filho de -> Maria" não deve criar automaticamente
        "Maria -> Mãe de -> João" como um segundo registro — só o
        `inverso` do tipo é usado para EXIBIÇÃO (ver conexoes_de_entidade),
        não para persistir uma segunda linha.
        """
        self.autentica_como(self.mestre_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_filho
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Conexao.objects.count(), 1)

    def test_conexoes_de_entidade_mostra_tipo_inverso_do_outro_lado(self):
        self.autentica_como(self.mestre_a)

        self._cria_conexao(self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_filho)

        resposta_origem = self.client.get(f"/campanha/npcs/{self.npc_a1.id}/conexoes/")
        resposta_destino = self.client.get(f"/campanha/npcs/{self.npc_a2.id}/conexoes/")

        self.assertEqual(resposta_origem.data[0]["tipo_nome"], "Filho de")
        self.assertEqual(resposta_destino.data[0]["tipo_nome"], "Mãe de")

    # --- Permissões ---

    def test_jogador_nao_pode_criar_conexao(self):
        self.autentica_como(self.jogador_a)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_jogador_nao_pode_editar_conexao(self):
        self.autentica_como(self.mestre_a)
        criada = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )
        conexao_id = criada.data["id"]

        self.autentica_como(self.jogador_a)

        response = self.client.patch(
            f"/campanha/conexoes/{conexao_id}/",
            {"descricao": "Editado por jogador"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_jogador_nao_pode_excluir_conexao(self):
        self.autentica_como(self.mestre_a)
        criada = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )
        conexao_id = criada.data["id"]

        self.autentica_como(self.jogador_a)

        response = self.client.delete(f"/campanha/conexoes/{conexao_id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Conexao.objects.filter(pk=conexao_id).exists())

    def test_mestre_de_outra_campanha_nao_cria_conexao_em_a(self):
        """IDOR/BOLA: mestre_b não é mestre da Campanha A."""
        self.autentica_como(self.mestre_b)

        response = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_jogador_de_outra_campanha_nao_ve_conexao_de_a(self):
        """IDOR/BOLA: jogador_b não participa da Campanha A."""
        self.autentica_como(self.mestre_a)
        criada = self._cria_conexao(
            self.client, self.campanha_a, self.npc_a1, self.npc_a2, self.tipo_amigo
        )
        conexao_id = criada.data["id"]

        self.autentica_como(self.jogador_b)

        response = self.client.get(f"/campanha/conexoes/{conexao_id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_conexao_com_tipo_de_entidade_nao_permitido_e_rejeitada(self):
        """
        Allowlist de `modelos_conectaveis()`: não é possível criar uma
        Conexao envolvendo, por exemplo, um Usuario diretamente.
        """
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/conexoes/",
            {
                "entidade1_tipo": "usuario",
                "entidade1_id": self.mestre_a.id,
                "entidade2_tipo": "npc",
                "entidade2_id": self.npc_a1.id,
                "tipo": self.tipo_amigo.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Busca global na campanha
# ---------------------------------------------------------------------------

class BuscaCampanhaTests(DuasCampanhasTestCase):

    def test_acha_por_nome_e_por_conteudo(self):
        self.npc_a1.conteudo = "## Aparencia\n\nUm homem que carrega um amuleto de jade."
        self.npc_a1.save()
        Local.objects.create(campanha=self.campanha_a, nome="Vila do Jade")

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=jade")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        achados = {(r["tipo"], r["nome"]) for r in response.data}
        self.assertIn(("local", "Vila do Jade"), achados)
        self.assertIn(("npc", "Arkan"), achados)

    def test_jogador_nao_acha_entidade_invisivel(self):
        NPC.objects.create(
            campanha=self.campanha_a, nome="Segredo Absoluto", visivel_para_jogadores=False
        )

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=segredo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

        self.autentica_como(self.mestre_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=segredo")
        self.assertEqual(len(response.data), 1)

    def test_termo_curto_devolve_lista_vazia(self):
        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=a")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_nao_participante_recebe_403(self):
        self.autentica_como(self.jogador_b)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=arkan")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Entidades de mundo novas — Documento, Imagem, Canva, Criatura, Divindade,
# Raca. Todas passam pela MESMA fábrica de views (`_crud_mundo`), então os
# testes abaixo rodam parametrizados por tipo: um bug na fábrica aparece nos
# seis de uma vez, e um tipo que esquecer de ser registrado some da lista.
# ---------------------------------------------------------------------------

ENTIDADES_NOVAS = [
    ("documento", "documentos", {"nome": "Carta do Rei", "tipo": "Carta", "autor": "Aldric"}),
    ("imagem", "imagens", {"nome": "Brasão Real", "legenda": "Brasão da casa real"}),
    ("canva", "canvas", {"nome": "Mural do Caso"}),
    ("criatura", "criaturas", {"nome": "Lobo Sombrio", "tipo": "Besta", "nivel": 3, "tamanho": "medio"}),
    ("divindade", "divindades", {"nome": "Khalmyr", "dominio": "Justiça", "categoria": "Maior"}),
    ("raca", "racas", {"nome": "Anão", "tipo": "Humanoide", "tamanho": "pequeno"}),
]


class EntidadesMundoNovasTests(DuasCampanhasTestCase):

    def _cria(self, plural, payload, campanha=None):
        campanha = campanha or self.campanha_a
        return self.client.post(f"/campanha/{campanha.id}/{plural}/", payload, format="json")

    def test_mestre_cria_e_lista_cada_tipo(self):
        self.autentica_como(self.mestre_a)

        for tipo, plural, payload in ENTIDADES_NOVAS:
            with self.subTest(tipo=tipo):
                response = self._cria(plural, payload)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(response.data["nome"], payload["nome"])
                self.assertEqual(response.data["campanha"], self.campanha_a.id)

                listagem = self.client.get(f"/campanha/{self.campanha_a.id}/{plural}/")
                self.assertEqual(listagem.status_code, status.HTTP_200_OK)
                self.assertEqual(len(listagem.data), 1)

    def test_crud_completo_de_cada_tipo(self):
        self.autentica_como(self.mestre_a)

        for tipo, plural, payload in ENTIDADES_NOVAS:
            with self.subTest(tipo=tipo):
                criado = self._cria(plural, payload).data
                detalhe_url = f"/campanha/{plural}/{criado['id']}/"

                self.assertEqual(self.client.get(detalhe_url).status_code, status.HTTP_200_OK)

                patch = self.client.patch(detalhe_url, {"conteudo": "## Anotações"}, format="json")
                self.assertEqual(patch.status_code, status.HTTP_200_OK, patch.data)
                self.assertEqual(patch.data["conteudo"], "## Anotações")

                self.assertEqual(
                    self.client.delete(detalhe_url).status_code, status.HTTP_204_NO_CONTENT
                )
                self.assertEqual(self.client.get(detalhe_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_campos_comuns_de_mundo_existem_em_todos(self):
        """Pasta, ícone, cor, ordem, visibilidade e datas — o contrato que a
        árvore da campanha e o menu de contexto do frontend assumem."""
        self.autentica_como(self.mestre_a)
        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Mundo")

        for tipo, plural, payload in ENTIDADES_NOVAS:
            with self.subTest(tipo=tipo):
                response = self._cria(
                    plural,
                    {**payload, "pasta": pasta.id, "icone": "star", "cor": "#ff0066", "ordem": 3},
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(response.data["pasta"], pasta.id)
                self.assertEqual(response.data["icone"], "star")
                self.assertEqual(response.data["cor"], "#ff0066")
                self.assertEqual(response.data["ordem"], 3)
                self.assertTrue(response.data["visivel_para_jogadores"])
                self.assertFalse(response.data["editavel_para_jogadores"])
                self.assertIn("criado_em", response.data)
                self.assertIn("atualizado_em", response.data)
                self.assertIn("conteudo", response.data)

    def test_pasta_de_outra_campanha_e_rejeitada(self):
        self.autentica_como(self.mestre_a)
        pasta_b = Pasta.objects.create(campanha=self.campanha_b, nome="Mundo de B")

        for tipo, plural, payload in ENTIDADES_NOVAS:
            with self.subTest(tipo=tipo):
                response = self._cria(plural, {**payload, "pasta": pasta_b.id})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ordenacao_respeita_o_campo_ordem(self):
        self.autentica_como(self.mestre_a)
        self._cria("criaturas", {"nome": "Zumbi", "ordem": 0})
        self._cria("criaturas", {"nome": "Ancião", "ordem": 5})
        self._cria("criaturas", {"nome": "Basilisco", "ordem": 1})

        nomes = [c["nome"] for c in self.client.get(f"/campanha/{self.campanha_a.id}/criaturas/").data]
        self.assertEqual(nomes, ["Zumbi", "Basilisco", "Ancião"])

    def test_jogador_le_mas_nao_cria_nem_exclui(self):
        self.autentica_como(self.mestre_a)
        criado = self._cria("divindades", {"nome": "Khalmyr"}).data

        self.autentica_como(self.jogador_a)
        self.assertEqual(
            self.client.get(f"/campanha/divindades/{criado['id']}/").status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self._cria("divindades", {"nome": "Não pode"}).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.delete(f"/campanha/divindades/{criado['id']}/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_jogador_so_edita_quando_editavel_para_jogadores(self):
        self.autentica_como(self.mestre_a)
        criado = self._cria("documentos", {"nome": "Contrato"}).data
        url = f"/campanha/documentos/{criado['id']}/"

        self.autentica_como(self.jogador_a)
        self.assertEqual(
            self.client.patch(url, {"conteudo": "x"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.autentica_como(self.mestre_a)
        self.client.patch(url, {"editavel_para_jogadores": True}, format="json")

        self.autentica_como(self.jogador_a)
        self.assertEqual(
            self.client.patch(url, {"conteudo": "ok"}, format="json").status_code, status.HTTP_200_OK
        )

    def test_jogador_editor_nao_altera_as_flags_de_visibilidade(self):
        """Mesma regra de `RestringeCamposDeMestreMixin` já aplicada aos
        tipos antigos: poder editar o conteúdo não é poder se esconder."""
        self.autentica_como(self.mestre_a)
        criado = self._cria("documentos", {"nome": "Contrato", "editavel_para_jogadores": True}).data
        url = f"/campanha/documentos/{criado['id']}/"

        self.autentica_como(self.jogador_a)
        response = self.client.patch(url, {"visivel_para_jogadores": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["visivel_para_jogadores"])

    def test_jogador_nao_ve_entidade_invisivel_na_listagem(self):
        self.autentica_como(self.mestre_a)
        self._cria("racas", {"nome": "Secreta", "visivel_para_jogadores": False})
        self._cria("racas", {"nome": "Pública"})

        self.autentica_como(self.jogador_a)
        nomes = [r["nome"] for r in self.client.get(f"/campanha/{self.campanha_a.id}/racas/").data]

        self.assertEqual(nomes, ["Pública"])

    def test_jogador_de_outra_campanha_nao_acessa(self):
        self.autentica_como(self.mestre_a)
        criado = self._cria("criaturas", {"nome": "Lobo"}).data

        self.autentica_como(self.jogador_b)
        self.assertEqual(
            self.client.get(f"/campanha/{self.campanha_a.id}/criaturas/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get(f"/campanha/criaturas/{criado['id']}/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_local_precisa_ser_da_mesma_campanha(self):
        self.autentica_como(self.mestre_a)
        local_b = Local.objects.create(campanha=self.campanha_b, nome="Fora")

        for plural in ("documentos", "criaturas"):
            with self.subTest(plural=plural):
                response = self._cria(plural, {"nome": "Intrusa", "local": local_b.id})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_entram_na_busca_global(self):
        self.autentica_como(self.mestre_a)
        self._cria("divindades", {"nome": "Khalmyr"})
        self._cria("racas", {"nome": "Elfo", "conteudo": "Vivem nas florestas de Lenórienn."})

        por_nome = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=Khalmyr").data
        self.assertTrue(any(r["tipo"] == "divindade" for r in por_nome))

        por_conteudo = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=Lenórienn").data
        self.assertTrue(any(r["tipo"] == "raca" for r in por_conteudo))

    def test_podem_ser_duplicadas(self):
        self.autentica_como(self.mestre_a)

        for tipo, plural, payload in ENTIDADES_NOVAS:
            with self.subTest(tipo=tipo):
                criado = self._cria(plural, payload).data
                response = self.client.post(
                    f"/campanha/{self.campanha_a.id}/entidades/duplicar/",
                    {"tipo": tipo, "id": criado["id"]},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(response.data["nome"], f"{payload['nome']} (cópia)")

    def test_aceitam_notas_e_conexoes(self):
        self.autentica_como(self.mestre_a)
        divindade = self._cria("divindades", {"nome": "Khalmyr"}).data
        raca = self._cria("racas", {"nome": "Anão"}).data

        nota = self.client.post(
            "/campanha/notas/",
            {"content_type": "divindade", "object_id": divindade["id"], "conteudo": "Padroeira dos anões."},
            format="json",
        )
        self.assertEqual(nota.status_code, status.HTTP_201_CREATED, nota.data)

        tipo_conexao = TipoConexao.objects.create(nome="Cultuada por")
        conexao = self.client.post(
            f"/campanha/{self.campanha_a.id}/conexoes/",
            {
                "entidade1_tipo": "divindade",
                "entidade1_id": divindade["id"],
                "entidade2_tipo": "raca",
                "entidade2_id": raca["id"],
                "tipo": tipo_conexao.id,
            },
            format="json",
        )
        self.assertEqual(conexao.status_code, status.HTTP_201_CREATED, conexao.data)

        conexoes = self.client.get(f"/campanha/divindades/{divindade['id']}/conexoes/")
        self.assertEqual(conexoes.status_code, status.HTTP_200_OK)
        self.assertEqual(len(conexoes.data), 1)
        self.assertEqual(conexoes.data[0]["entidade"]["tipo"], "raca")


class CanvaTests(DuasCampanhasTestCase):

    def test_persiste_o_estado_completo_do_quadro(self):
        self.autentica_como(self.mestre_a)
        dados = {
            "versao": 1,
            "fundo": {"cor": "#101014", "padrao": "grade"},
            "viewport": {"x": -120, "y": 40, "zoom": 1.5},
            "objetos": [
                {
                    "id": "o1", "tipo": "postit", "x": 10, "y": 20, "w": 180, "h": 180,
                    "rotacao": -4, "z": 1, "estilo": {"fundo": "#ffd866"}, "conteudo": "Pista",
                },
                {
                    "id": "o2", "tipo": "entidade", "x": 300, "y": 20, "w": 220, "h": 90,
                    "rotacao": 0, "z": 2, "entidade": {"tipo": "npc", "id": self.npc_a1.id},
                },
                {"id": "o3", "tipo": "seta", "z": 3, "de": "o1", "para": "o2"},
            ],
        }

        criado = self.client.post(
            f"/campanha/{self.campanha_a.id}/canvas/", {"nome": "Mural", "dados": dados}, format="json"
        )
        self.assertEqual(criado.status_code, status.HTTP_201_CREATED, criado.data)

        lido = self.client.get(f"/campanha/canvas/{criado.data['id']}/").data
        self.assertEqual(lido["dados"], dados)

    def test_referencia_a_entidade_nao_duplica_os_dados_dela(self):
        """O objeto guarda `{tipo, id}` — renomear o NPC reflete no quadro,
        porque o nome nunca foi copiado para dentro do JSON."""
        self.autentica_como(self.mestre_a)
        criado = self.client.post(
            f"/campanha/{self.campanha_a.id}/canvas/",
            {
                "nome": "Mural",
                "dados": {"objetos": [{"id": "o1", "tipo": "entidade", "entidade": {"tipo": "npc", "id": self.npc_a1.id}}]},
            },
            format="json",
        ).data

        self.npc_a1.nome = "Arkan, o Renegado"
        self.npc_a1.save()

        objeto = self.client.get(f"/campanha/canvas/{criado['id']}/").data["dados"]["objetos"][0]
        self.assertNotIn("nome", objeto)
        self.assertEqual(objeto["entidade"], {"tipo": "npc", "id": self.npc_a1.id})

    def test_dados_invalidos_sao_rejeitados(self):
        self.autentica_como(self.mestre_a)

        for dados in ([1, 2, 3], "texto", {"objetos": "não é lista"}):
            with self.subTest(dados=dados):
                response = self.client.post(
                    f"/campanha/{self.campanha_a.id}/canvas/", {"nome": "X", "dados": dados}, format="json"
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dados_nasce_como_objeto_vazio(self):
        self.autentica_como(self.mestre_a)
        response = self.client.post(f"/campanha/{self.campanha_a.id}/canvas/", {"nome": "Novo"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["dados"], {})


class ImagemReferenciaTests(DuasCampanhasTestCase):
    """
    `![[Nome da Imagem]]` dentro do `conteudo` de qualquer entidade é
    resolvido pelo frontend contra a listagem de Imagens da campanha (ver
    `src/hooks/useImagensCampanha.ts`). O que precisa valer aqui é o
    contrato do qual essa resolução depende: nome único por campanha e
    visibilidade respeitada na listagem — uma Imagem escondida do jogador
    não pode aparecer nem ter a URL do arquivo enviada a ele.
    """

    def setUp(self):
        super().setUp()
        self.autentica_como(self.mestre_a)
        self.publica = Imagem.objects.create(campanha=self.campanha_a, nome="Brasão Real")
        self.secreta = Imagem.objects.create(
            campanha=self.campanha_a, nome="Mapa do Tesouro", visivel_para_jogadores=False
        )

    def test_listagem_traz_o_necessario_para_resolver_a_referencia(self):
        response = self.client.get(f"/campanha/{self.campanha_a.id}/imagens/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        for campo in ("id", "nome", "imagem", "legenda", "creditos"):
            self.assertIn(campo, response.data[0])

    def test_imagem_invisivel_nao_chega_ao_jogador(self):
        self.autentica_como(self.jogador_a)
        nomes = [i["nome"] for i in self.client.get(f"/campanha/{self.campanha_a.id}/imagens/").data]

        self.assertEqual(nomes, ["Brasão Real"])

    def test_nao_participante_nao_acessa_as_imagens(self):
        self.autentica_como(self.jogador_b)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/imagens/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_nome_e_unico_por_campanha(self):
        """Sem isso, `![[Brasão Real]]` seria ambíguo."""
        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/imagens/", {"nome": "Brasão Real"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nome", response.data)

    def test_mesmo_nome_em_outra_campanha_e_permitido(self):
        self.autentica_como(self.mestre_b)
        response = self.client.post(
            f"/campanha/{self.campanha_b.id}/imagens/", {"nome": "Brasão Real"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class MultiplasBibliotecasTests(DuasCampanhasTestCase):
    """
    `sistema` (FK, principal) e `sistemas` (M2M) precisam continuar
    coerentes — é o que mantém campanhas/fichas antigas funcionando depois
    da mudança para várias bibliotecas de regras (seção 1).
    """

    def setUp(self):
        super().setUp()
        self.s1 = Sistema.objects.create(nome="Tormenta 20")
        self.s2 = Sistema.objects.create(nome="Homebrew da Casa")
        self.autentica_como(self.mestre_a)

    def test_campanha_aceita_varias_bibliotecas(self):
        response = self.client.patch(
            f"/campanha/{self.campanha_a.id}/", {"sistemas": [self.s1.id, self.s2.id]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertCountEqual(response.data["sistemas"], [self.s1.id, self.s2.id])

    def test_primeiro_da_lista_vira_o_sistema_principal(self):
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistemas": [self.s1.id, self.s2.id]}, format="json")
        self.campanha_a.refresh_from_db()

        self.assertEqual(self.campanha_a.sistema_id, self.s1.id)

    def test_patch_antigo_com_sistema_unico_continua_funcionando(self):
        """Fluxo do seletor de sistema anterior a esta mudança."""
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistema": self.s1.id}, format="json")
        self.campanha_a.refresh_from_db()

        self.assertEqual(self.campanha_a.sistema_id, self.s1.id)
        self.assertEqual(list(self.campanha_a.sistemas.values_list("id", flat=True)), [self.s1.id])

    def test_remover_o_principal_promove_o_que_sobrou(self):
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistemas": [self.s1.id, self.s2.id]}, format="json")
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistemas": [self.s2.id]}, format="json")
        self.campanha_a.refresh_from_db()

        self.assertEqual(self.campanha_a.sistema_id, self.s2.id)

    def test_lista_vazia_zera_o_principal(self):
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistemas": [self.s1.id]}, format="json")
        self.client.patch(f"/campanha/{self.campanha_a.id}/", {"sistemas": []}, format="json")
        self.campanha_a.refresh_from_db()

        self.assertIsNone(self.campanha_a.sistema_id)

    def test_personagem_tambem_aceita_varias_bibliotecas(self):
        personagem = Personagem.objects.create(usuario=self.jogador_a, nome="Arkan", sistema=self.s1)
        self.autentica_como(self.jogador_a)

        response = self.client.patch(
            f"/personagem/{personagem.id}/", {"sistemas": [self.s1.id, self.s2.id]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertCountEqual(response.data["sistemas"], [self.s1.id, self.s2.id])


# ---------------------------------------------------------------------------
# Equipamentos exclusivos da campanha
# ---------------------------------------------------------------------------

class EquipamentosCampanhaTests(DuasCampanhasTestCase):
    """
    O que importa aqui é o ISOLAMENTO (um equipamento pertence a UMA
    campanha e não vaza para outra) e a divisão mestre/jogador. O CRUD em si
    é o mesmo `_crud_mundo` já coberto por `EntidadesMundoNovasTests` — o que
    se testa é que estes três tipos entraram nele de verdade, incluindo
    busca, duplicação e conexões.
    """

    def setUp(self):
        super().setUp()
        self.item_a = ItemCampanha.objects.create(
            campanha=self.campanha_a, nome="Poção do Arauto", descricao="Cura 2d4.", valor=50
        )
        self.arma_a = ArmaCampanha.objects.create(campanha=self.campanha_a, nome="Lâmina de Vidro", dano="1d8")
        self.armadura_a = ArmaduraCampanha.objects.create(campanha=self.campanha_a, nome="Casaco Rúnico", defesa=3)

    # -- criação e edição ---------------------------------------------------

    def test_mestre_cria_item_exclusivo(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/itens-campanha/",
            {"nome": "Amuleto de Wynna", "descricao": "Concede +2 em testes de magia.", "valor": "120.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["nome"], "Amuleto de Wynna")
        self.assertEqual(response.data["campanha"], self.campanha_a.id)

    def test_jogador_nao_cria_nem_edita_nem_exclui(self):
        self.autentica_como(self.jogador_a)

        criar = self.client.post(
            f"/campanha/{self.campanha_a.id}/itens-campanha/", {"nome": "Item pirata"}, format="json"
        )
        editar = self.client.patch(
            f"/campanha/itens-campanha/{self.item_a.id}/", {"valor": "1.00"}, format="json"
        )
        excluir = self.client.delete(f"/campanha/itens-campanha/{self.item_a.id}/")

        self.assertEqual(criar.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(editar.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(excluir.status_code, status.HTTP_403_FORBIDDEN)

    # -- visibilidade -------------------------------------------------------

    def test_jogador_da_campanha_ve_os_tres_tipos(self):
        self.autentica_como(self.jogador_a)

        itens = self.client.get(f"/campanha/{self.campanha_a.id}/itens-campanha/")
        armas = self.client.get(f"/campanha/{self.campanha_a.id}/armas-campanha/")
        armaduras = self.client.get(f"/campanha/{self.campanha_a.id}/armaduras-campanha/")

        self.assertEqual([i["nome"] for i in itens.data], ["Poção do Arauto"])
        self.assertEqual([a["nome"] for a in armas.data], ["Lâmina de Vidro"])
        self.assertEqual([a["nome"] for a in armaduras.data], ["Casaco Rúnico"])

    def test_jogador_de_outra_campanha_nao_acessa(self):
        self.autentica_como(self.jogador_b)

        lista = self.client.get(f"/campanha/{self.campanha_a.id}/itens-campanha/")
        detalhe = self.client.get(f"/campanha/itens-campanha/{self.item_a.id}/")

        self.assertEqual(lista.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detalhe.status_code, status.HTTP_403_FORBIDDEN)

    def test_item_escondido_nao_aparece_para_jogador_mas_aparece_para_mestre(self):
        ItemCampanha.objects.create(
            campanha=self.campanha_a, nome="Segredo do mestre", visivel_para_jogadores=False
        )

        self.autentica_como(self.jogador_a)
        do_jogador = self.client.get(f"/campanha/{self.campanha_a.id}/itens-campanha/")
        self.autentica_como(self.mestre_a)
        do_mestre = self.client.get(f"/campanha/{self.campanha_a.id}/itens-campanha/")

        self.assertNotIn("Segredo do mestre", [i["nome"] for i in do_jogador.data])
        self.assertIn("Segredo do mestre", [i["nome"] for i in do_mestre.data])

    # -- integração com o resto da aba Mundo --------------------------------

    def test_entram_na_busca_global_da_campanha(self):
        self.autentica_como(self.jogador_a)

        response = self.client.get(f"/campanha/{self.campanha_a.id}/busca/?q=Lâmina")

        tipos = {(r["tipo"], r["nome"]) for r in response.data}
        self.assertIn(("armacampanha", "Lâmina de Vidro"), tipos)

    def test_podem_ser_organizados_em_pasta_da_propria_campanha(self):
        pasta = Pasta.objects.create(campanha=self.campanha_a, nome="Tesouro")
        pasta_outra = Pasta.objects.create(campanha=self.campanha_b, nome="Alheia")
        self.autentica_como(self.mestre_a)

        ok = self.client.patch(
            f"/campanha/itens-campanha/{self.item_a.id}/", {"pasta": pasta.id}, format="json"
        )
        recusado = self.client.patch(
            f"/campanha/itens-campanha/{self.item_a.id}/", {"pasta": pasta_outra.id}, format="json"
        )

        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        self.assertEqual(ok.data["pasta"], pasta.id)
        self.assertEqual(recusado.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mestre_duplica_um_equipamento(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/entidades/duplicar/",
            {"tipo": "armacampanha", "id": self.arma_a.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["nome"], "Lâmina de Vidro (cópia)")
        self.assertEqual(response.data["dano"], "1d8")

    def test_podem_participar_de_uma_conexao(self):
        tipo = TipoConexao.objects.create(nome="Forjado por")
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/conexoes/",
            {
                "entidade1_tipo": "armacampanha",
                "entidade1_id": self.arma_a.id,
                "entidade2_tipo": "npc",
                "entidade2_id": self.npc_a1.id,
                "tipo": tipo.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class CopiaEquipamentoParaFichaTests(DuasCampanhasTestCase):
    """
    Copiar leva uma linha NOVA para a ficha e nunca altera o original — é o
    requisito de "sem alterar os itens originais".
    """

    def setUp(self):
        super().setUp()
        self.item_a = ItemCampanha.objects.create(
            campanha=self.campanha_a, nome="Poção do Arauto", descricao="Cura 2d4.", peso=1, valor=50
        )
        self.arma_a = ArmaCampanha.objects.create(
            campanha=self.campanha_a, nome="Lâmina de Vidro", dano="1d8", ataque=2, tipo_dano="Perfurante"
        )
        self.armadura_a = ArmaduraCampanha.objects.create(
            campanha=self.campanha_a, nome="Casaco Rúnico", defesa=3
        )

        self.personagem_a = Personagem.objects.create(usuario=self.jogador_a, nome="Arkan")
        self.campanha_a.personagens.add(self.personagem_a)

        self.personagem_b = Personagem.objects.create(usuario=self.jogador_b, nome="Estranha")
        self.campanha_b.personagens.add(self.personagem_b)

    def test_jogador_copia_item_da_campanha_para_a_ficha(self):
        self.autentica_como(self.jogador_a)

        response = self.client.post(
            f"/campanha/personagens/{self.personagem_a.id}/itens-campanha/{self.item_a.id}/copiar/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        item = Item.objects.get(pk=response.data["id"])
        self.assertEqual(item.nome, "Poção do Arauto")
        self.assertEqual(item.descricao, "Cura 2d4.")
        self.assertEqual(item.personagem_id, self.personagem_a.id)
        # O original continua intacto e é outro registro.
        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.nome, "Poção do Arauto")
        self.assertEqual(ItemCampanha.objects.count(), 1)

    def test_arma_e_armadura_levam_os_campos_de_jogo(self):
        self.autentica_como(self.jogador_a)
        base = f"/campanha/personagens/{self.personagem_a.id}"

        self.client.post(f"{base}/armas-campanha/{self.arma_a.id}/copiar/", {}, format="json")
        self.client.post(f"{base}/armaduras-campanha/{self.armadura_a.id}/copiar/", {}, format="json")

        arma = Arma.objects.get()
        self.assertEqual((arma.dano, arma.ataque, arma.tipo_dano), ("1d8", 2, "Perfurante"))
        self.assertEqual(Armadura.objects.get().defesa, 3)

    def test_personagem_de_outra_campanha_nao_copia(self):
        self.autentica_como(self.jogador_b)

        response = self.client.post(
            f"/campanha/personagens/{self.personagem_b.id}/itens-campanha/{self.item_a.id}/copiar/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Item.objects.exists())

    def test_item_escondido_nao_pode_ser_copiado_pelo_jogador(self):
        escondido = ItemCampanha.objects.create(
            campanha=self.campanha_a, nome="Segredo", visivel_para_jogadores=False
        )
        self.autentica_como(self.jogador_a)

        response = self.client.post(
            f"/campanha/personagens/{self.personagem_a.id}/itens-campanha/{escondido.id}/copiar/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_ficha_expoe_as_campanhas_do_personagem(self):
        """É o que permite à Biblioteca saber onde procurar os exclusivos."""
        self.autentica_como(self.jogador_a)

        response = self.client.get(f"/personagem/{self.personagem_a.id}/")

        self.assertEqual(response.data["campanhas"], [self.campanha_a.id])


# ---------------------------------------------------------------------------
# Loja da campanha
# ---------------------------------------------------------------------------

class LojaBaseTestCase(DuasCampanhasTestCase):
    """Campanha A com um sistema em uso e alguns equipamentos vendáveis."""

    def setUp(self):
        super().setUp()
        self.sistema = Sistema.objects.create(nome="Tormenta")
        self.campanha_a.sistemas.add(self.sistema)
        self.campanha_a.sistema = self.sistema
        self.campanha_a.save(update_fields=["sistema"])

        self.item_sistema = ItemSistema.objects.create(sistema=self.sistema, nome="Corda", valor=5)
        self.arma_sistema = ArmaSistema.objects.create(sistema=self.sistema, nome="Espada", valor=100, dano="1d8")
        self.armadura_sistema = ArmaduraSistema.objects.create(
            sistema=self.sistema, nome="Couro", valor=60, defesa=2
        )
        self.item_exclusivo = ItemCampanha.objects.create(
            campanha=self.campanha_a, nome="Poção do Arauto", valor=80
        )

        # Sistema que a campanha A NÃO usa.
        self.sistema_alheio = Sistema.objects.create(nome="Outro")
        self.item_alheio = ItemSistema.objects.create(sistema=self.sistema_alheio, nome="Proibido")

    def cria_produto(self, origem, preco="10.00", **extra):
        return ProdutoLoja.objects.create(
            campanha=self.campanha_a,
            content_type=ContentType.objects.get_for_model(type(origem)),
            object_id=origem.pk,
            preco=preco,
            **extra,
        )


class CategoriaLojaTests(LojaBaseTestCase):

    def test_mestre_cria_categoria(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/categorias/",
            {"nome": "Consumíveis", "icone": "flask-conical"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["nome"], "Consumíveis")
        self.assertFalse(response.data["rotacao_ativa"])

    def test_jogador_nao_cria_nem_edita_categoria(self):
        categoria = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Armas")
        self.autentica_como(self.jogador_a)

        criar = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/categorias/", {"nome": "Pirata"}, format="json"
        )
        editar = self.client.patch(
            f"/campanha/loja/categorias/{categoria.id}/", {"nome": "Mudado"}, format="json"
        )

        self.assertEqual(criar.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(editar.status_code, status.HTTP_403_FORBIDDEN)

    def test_nome_repetido_na_mesma_campanha_e_recusado(self):
        CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Armas")
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/categorias/", {"nome": "Armas"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rotacao_com_parametros_invalidos_e_recusada(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/categorias/",
            {"nome": "Raros", "rotacao_ativa": True, "rotacao_quantidade": 0, "rotacao_intervalo_minutos": 0},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rotacao_quantidade", response.data)
        self.assertIn("rotacao_intervalo_minutos", response.data)

    def test_excluir_categoria_nao_exclui_os_produtos(self):
        categoria = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Armas")
        produto = self.cria_produto(self.arma_sistema)
        produto.categorias.add(categoria)
        self.autentica_como(self.mestre_a)

        self.client.delete(f"/campanha/loja/categorias/{categoria.id}/")

        produto.refresh_from_db()
        self.assertEqual(ProdutoLoja.objects.count(), 1)
        self.assertEqual(produto.categorias.count(), 0)


class ProdutoLojaTests(LojaBaseTestCase):

    def test_mestre_poe_equipamento_do_sistema_a_venda(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "armasistema", "origem_id": self.arma_sistema.id, "preco": "150.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["origem"]["nome"], "Espada")
        self.assertEqual(response.data["origem"]["classe"], "arma")
        self.assertEqual(response.data["origem"]["dano"], "1d8")

    def test_mestre_poe_exclusivo_da_campanha_a_venda(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "itemcampanha", "origem_id": self.item_exclusivo.id, "preco": "80.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["origem"]["nome"], "Poção do Arauto")

    def test_equipamento_de_sistema_fora_da_campanha_e_recusado(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "itemsistema", "origem_id": self.item_alheio.id, "preco": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("origem_id", response.data)

    def test_exclusivo_de_outra_campanha_e_recusado(self):
        alheio = ItemCampanha.objects.create(campanha=self.campanha_b, nome="De outra mesa")
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "itemcampanha", "origem_id": alheio.id, "preco": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tipo_fora_da_allowlist_e_recusado(self):
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "npc", "origem_id": self.npc_a1.id, "preco": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("origem_tipo", response.data)

    def test_mesmo_equipamento_duas_vezes_e_recusado(self):
        self.cria_produto(self.arma_sistema)
        self.autentica_como(self.mestre_a)

        response = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "armasistema", "origem_id": self.arma_sistema.id, "preco": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_jogador_nao_lista_nem_cria_produtos(self):
        self.autentica_como(self.jogador_a)

        listar = self.client.get(f"/campanha/{self.campanha_a.id}/loja/produtos/")
        criar = self.client.post(
            f"/campanha/{self.campanha_a.id}/loja/produtos/",
            {"origem_tipo": "armasistema", "origem_id": self.arma_sistema.id},
            format="json",
        )

        self.assertEqual(listar.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(criar.status_code, status.HTTP_403_FORBIDDEN)

    def test_disponiveis_lista_as_seis_origens_no_escopo(self):
        self.cria_produto(self.arma_sistema)
        self.autentica_como(self.mestre_a)

        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/disponiveis/")

        nomes = {r["nome"] for r in response.data}
        self.assertEqual(nomes, {"Corda", "Espada", "Couro", "Poção do Arauto"})
        self.assertNotIn("Proibido", nomes)
        ja = {r["nome"]: r["ja_na_loja"] for r in response.data}
        self.assertTrue(ja["Espada"])
        self.assertFalse(ja["Corda"])


class VitrineTests(LojaBaseTestCase):

    def test_jogador_ve_a_vitrine_e_nao_ve_o_que_nao_esta_a_venda(self):
        categoria = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Geral")
        a_venda = self.cria_produto(self.arma_sistema, preco="150.00")
        fora = self.cria_produto(self.item_sistema, disponivel=False)
        esgotado = self.cria_produto(self.armadura_sistema, quantidade_disponivel=0)
        for produto in (a_venda, fora, esgotado):
            produto.categorias.add(categoria)

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nomes = [p["origem"]["nome"] for p in response.data["categorias"][0]["produtos"]]
        self.assertEqual(nomes, ["Espada"])

    def test_mestre_ve_inclusive_o_que_esta_fora_de_venda(self):
        categoria = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Geral")
        for origem in (self.arma_sistema, self.item_sistema):
            self.cria_produto(origem, disponivel=False).categorias.add(categoria)

        self.autentica_como(self.mestre_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertEqual(len(response.data["categorias"][0]["produtos"]), 2)

    def test_categoria_escondida_some_para_o_jogador(self):
        escondida = CategoriaLoja.objects.create(
            campanha=self.campanha_a, nome="Segredos", visivel_para_jogadores=False
        )
        self.cria_produto(self.arma_sistema).categorias.add(escondida)

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertEqual(response.data["categorias"], [])
        # E também não vaza pelo balaio de "sem categoria".
        self.assertEqual(response.data["sem_categoria"], [])

    def test_produto_sem_categoria_aparece_no_balaio(self):
        self.cria_produto(self.item_sistema)

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertEqual([p["origem"]["nome"] for p in response.data["sem_categoria"]], ["Corda"])

    def test_um_produto_pode_estar_em_duas_categorias(self):
        armas = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Armas", ordem=1)
        raros = CategoriaLoja.objects.create(campanha=self.campanha_a, nome="Raros", ordem=2)
        self.cria_produto(self.arma_sistema).categorias.add(armas, raros)

        self.autentica_como(self.jogador_a)
        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        por_nome = {c["nome"]: c for c in response.data["categorias"]}
        self.assertEqual(len(por_nome["Armas"]["produtos"]), 1)
        self.assertEqual(len(por_nome["Raros"]["produtos"]), 1)

    def test_nao_participante_nao_acessa_a_vitrine(self):
        self.autentica_como(self.jogador_b)

        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RotacaoTests(LojaBaseTestCase):
    """
    A rotação é uma função pura do relógio — estes testes existem para travar
    justamente isso: mesma janela, mesma seleção, em qualquer processo; e a
    seleção muda sozinha quando a janela vira.
    """

    def setUp(self):
        super().setUp()
        self.inicio = timezone.now() - timedelta(days=1)
        self.categoria = CategoriaLoja.objects.create(
            campanha=self.campanha_a,
            nome="Rotativos",
            rotacao_ativa=True,
            rotacao_quantidade=2,
            rotacao_intervalo_minutos=60,
            rotacao_inicio=self.inicio,
            rotacao_semente=12345,
        )
        self.produtos = []
        for i in range(6):
            origem = ItemCampanha.objects.create(campanha=self.campanha_a, nome=f"Item {i}", valor=10)
            produto = self.cria_produto(origem, ordem=i)
            produto.categorias.add(self.categoria)
            self.produtos.append(produto)

    def _selecao(self, agora, metodo=None):
        if metodo:
            self.categoria.rotacao_metodo = metodo
        return [p.id for p in loja.selecionar(self.categoria, self.produtos, agora)]

    def test_mesma_janela_produz_sempre_a_mesma_selecao(self):
        agora = self.inicio + timedelta(minutes=90)

        primeira = self._selecao(agora)
        # Mesmo instante, outra chamada — é o que dois jogadores diferentes
        # pedindo a vitrine ao mesmo tempo produzem.
        segunda = self._selecao(agora + timedelta(seconds=30))

        self.assertEqual(primeira, segunda)
        self.assertEqual(len(primeira), 2)

    def test_a_selecao_muda_quando_a_janela_vira(self):
        antes = self._selecao(self.inicio + timedelta(minutes=30))
        depois = self._selecao(self.inicio + timedelta(minutes=90))

        self.assertNotEqual(antes, depois)

    def test_metodo_por_ordem_anda_em_fatias_ciclicas(self):
        ids = [p.id for p in self.produtos]

        janela0 = self._selecao(self.inicio + timedelta(minutes=1), metodo="ordem")
        janela1 = self._selecao(self.inicio + timedelta(minutes=61), metodo="ordem")
        janela2 = self._selecao(self.inicio + timedelta(minutes=121), metodo="ordem")
        # Três janelas de 2 em 6 produtos: a quarta volta ao começo.
        janela3 = self._selecao(self.inicio + timedelta(minutes=181), metodo="ordem")

        self.assertEqual(janela0, ids[0:2])
        self.assertEqual(janela1, ids[2:4])
        self.assertEqual(janela2, ids[4:6])
        self.assertEqual(janela3, ids[0:2])

    def test_sem_rotacao_mostra_tudo(self):
        self.categoria.rotacao_ativa = False

        self.assertEqual(len(self._selecao(timezone.now())), 6)

    def test_vitrine_menor_que_o_estoque_mostra_tudo(self):
        self.categoria.rotacao_quantidade = 10

        self.assertEqual(len(self._selecao(timezone.now())), 6)

    def test_vitrine_informa_quando_a_proxima_rotacao_acontece(self):
        self.autentica_como(self.jogador_a)

        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        categoria = response.data["categorias"][0]
        self.assertEqual(len(categoria["produtos"]), 2)
        self.assertEqual(categoria["total_produtos"], 6)
        self.assertIsNotNone(response.data["proxima_rotacao_em"])
        # A virada é sempre no futuro e dentro de um intervalo.
        self.assertGreater(response.data["proxima_rotacao_em"], timezone.now())
        self.assertLessEqual(
            response.data["proxima_rotacao_em"], timezone.now() + timedelta(minutes=60)
        )

    def test_sem_rotacao_efetiva_a_vitrine_nao_agenda_despertador(self):
        """Rotação ligada mas com vitrine maior que o estoque: nada muda, e
        acordar o cliente seria uma requisição à toa."""
        self.categoria.rotacao_quantidade = 10
        self.categoria.save(update_fields=["rotacao_quantidade"])
        self.autentica_como(self.jogador_a)

        response = self.client.get(f"/campanha/{self.campanha_a.id}/loja/")

        self.assertIsNone(response.data["proxima_rotacao_em"])

    def test_produto_escondido_pela_rotacao_nao_esta_a_venda(self):
        agora = timezone.now()
        visiveis = {p.id for p in loja.selecionar(self.categoria, self.produtos, agora)}
        escondido = next(p for p in self.produtos if p.id not in visiveis)

        self.assertFalse(loja.produto_a_venda(escondido, self.jogador_a, self.campanha_a, agora))
        a_mostra = next(p for p in self.produtos if p.id in visiveis)
        self.assertTrue(loja.produto_a_venda(a_mostra, self.jogador_a, self.campanha_a, agora))
