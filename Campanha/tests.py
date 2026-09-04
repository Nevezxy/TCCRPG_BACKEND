from rest_framework import status
from rest_framework.test import APITestCase

from Usuario.models import Usuario
from Personagem.models import Personagem
from .models import Campanha, NPC, Local, Organizacao, Pasta, TipoConexao, Conexao


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
