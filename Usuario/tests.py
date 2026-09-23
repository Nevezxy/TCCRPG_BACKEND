"""
Perfil do usuário (`/usuario/me/...`), poderes da conta (`PoderUsuario`) e o
mural de notas no perfil.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from Campanha.models import Campanha, Nota
from Personagem.models import Personagem, Poder, PoderUsuario

from .models import Usuario


class BasePerfil(APITestCase):

    def setUp(self):
        self.ana = Usuario.objects.create_user(username="ana", email="ana@exemplo.com", password="SenhaForte123!")
        self.bia = Usuario.objects.create_user(username="bia", email="bia@exemplo.com", password="SenhaForte123!")
        self.estranho = Usuario.objects.create_user(username="zeca", password="SenhaForte123!")
        # Ana mestra, Bia joga: as duas se conhecem; Zeca não conhece ninguém.
        self.campanha = Campanha.objects.create(mestre=self.ana, nome="Cinzas")
        self.campanha.jogadores.add(self.ana, self.bia)
        self.client.force_authenticate(self.ana)


class MeTests(BasePerfil):

    def test_get_traz_campos_de_perfil_e_totais(self):
        Personagem.objects.create(usuario=self.ana, nome="Kael")
        PoderUsuario.objects.create(usuario=self.ana, nome="Passo Sombrio")

        resposta = self.client.get("/usuario/me/")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        for campo in ("foto", "banner", "descricao", "cor_perfil", "links_sociais", "data_atualizacao", "email"):
            self.assertIn(campo, resposta.data)
        self.assertEqual(resposta.data["totais"], {"personagens": 1, "campanhas": 1, "poderes": 1})

    def test_patch_atualiza_o_perfil(self):
        resposta = self.client.patch(
            "/usuario/me/",
            {
                "descricao": "  Mestra nas sextas.  ",
                "cor_perfil": "#FF0066",
                "links_sociais": [{"rotulo": "Site", "url": "https://analume.art"}],
                "first_name": "Ana",
            },
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_200_OK, resposta.data)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.descricao, "Mestra nas sextas.")
        self.assertEqual(self.ana.cor_perfil, "#ff0066")
        self.assertEqual(self.ana.links_sociais, [{"rotulo": "Site", "url": "https://analume.art"}])
        self.assertIsNotNone(self.ana.data_atualizacao)

    def test_patch_multipart_aceita_links_em_string_json(self):
        resposta = self.client.patch(
            "/usuario/me/",
            {"links_sociais": '[{"rotulo": "Discord", "url": "https://discord.gg/x"}]'},
            format="multipart",
        )

        self.assertEqual(resposta.status_code, status.HTTP_200_OK, resposta.data)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.links_sociais[0]["rotulo"], "Discord")

    def test_link_que_nao_e_http_e_recusado(self):
        resposta = self.client.patch(
            "/usuario/me/",
            {"links_sociais": [{"rotulo": "x", "url": "javascript:alert(1)"}]},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.links_sociais, [])

    def test_cor_invalida_e_recusada(self):
        resposta = self.client.patch("/usuario/me/", {"cor_perfil": "vermelho"}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_username_nao_muda_por_patch(self):
        self.client.patch("/usuario/me/", {"username": "outra"}, format="json")
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.username, "ana")


class ListasDoPerfilTests(BasePerfil):

    def test_personagens_sao_so_os_meus(self):
        Personagem.objects.create(usuario=self.ana, nome="Kael")
        Personagem.objects.create(usuario=self.bia, nome="Irisa")

        resposta = self.client.get("/usuario/me/personagens/")

        self.assertEqual([p["nome"] for p in resposta.data], ["Kael"])

    def test_campanhas_trazem_o_papel(self):
        outra = Campanha.objects.create(mestre=self.bia, nome="Protocolo")
        outra.jogadores.add(self.bia, self.ana)
        moderada = Campanha.objects.create(mestre=self.bia, nome="Marés")
        moderada.jogadores.add(self.bia, self.ana)
        moderada.moderadores.add(self.ana)
        Campanha.objects.create(mestre=self.bia, nome="Não sou dessa")

        resposta = self.client.get("/usuario/me/campanhas/")

        papeis = {c["nome"]: c["papel"] for c in resposta.data}
        self.assertEqual(papeis, {"Cinzas": "mestre", "Protocolo": "jogador", "Marés": "moderador"})


class PoderUsuarioTests(BasePerfil):

    def test_crud_do_proprio_poder(self):
        criado = self.client.post("/usuario/me/poderes/", {"nome": "Rajada", "custo": 2, "tag": "Ataque"}, format="json")
        self.assertEqual(criado.status_code, status.HTTP_201_CREATED, criado.data)
        pk = criado.data["id"]
        self.assertEqual(criado.data["usuario"], self.ana.pk)

        editado = self.client.patch(f"/usuario/me/poderes/{pk}/", {"custo": 3}, format="json")
        self.assertEqual(editado.data["custo"], 3)

        self.assertEqual(len(self.client.get("/usuario/me/poderes/").data), 1)

        apagado = self.client.delete(f"/usuario/me/poderes/{pk}/")
        self.assertEqual(apagado.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PoderUsuario.objects.exists())

    def test_poder_de_outra_conta_nao_e_acessivel(self):
        alheio = PoderUsuario.objects.create(usuario=self.bia, nome="Alheio")

        self.assertEqual(self.client.get(f"/usuario/me/poderes/{alheio.pk}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f"/usuario/me/poderes/{alheio.pk}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/usuario/me/poderes/").data, [])

    def test_biblioteca_da_ficha_lista_os_poderes_da_conta_do_dono(self):
        kael = Personagem.objects.create(usuario=self.ana, nome="Kael")
        PoderUsuario.objects.create(usuario=self.ana, nome="Passo Sombrio")
        PoderUsuario.objects.create(usuario=self.bia, nome="De outra conta")

        resposta = self.client.get(f"/personagem/{kael.pk}/poderes-usuario/")

        self.assertEqual([p["nome"] for p in resposta.data], ["Passo Sombrio"])

    def test_adicionar_da_biblioteca_copia_para_a_ficha(self):
        kael = Personagem.objects.create(usuario=self.ana, nome="Kael")
        origem = PoderUsuario.objects.create(usuario=self.ana, nome="Rajada", tag="Ataque", custo=2, descricao="<p>2d6</p>")

        resposta = self.client.post(f"/personagem/{kael.pk}/poderes-usuario/{origem.pk}/copiar/")

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        copia = Poder.objects.get(pk=resposta.data["id"])
        self.assertEqual((copia.personagem, copia.nome, copia.tag, copia.custo), (kael, "Rajada", "Ataque", 2))
        # É cópia: editar o poder da conta não muda a ficha.
        origem.nome = "Rajada Maior"
        origem.save()
        copia.refresh_from_db()
        self.assertEqual(copia.nome, "Rajada")

    def test_nao_copia_poder_de_outra_conta(self):
        kael = Personagem.objects.create(usuario=self.ana, nome="Kael")
        alheio = PoderUsuario.objects.create(usuario=self.bia, nome="Alheio")

        resposta = self.client.post(f"/personagem/{kael.pk}/poderes-usuario/{alheio.pk}/copiar/")

        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(kael.poderes.exists())

    def test_mestre_adiciona_poder_da_conta_do_jogador_a_ficha_dele(self):
        irisa = Personagem.objects.create(usuario=self.bia, nome="Irisa")
        self.campanha.personagens.add(irisa)
        do_jogador = PoderUsuario.objects.create(usuario=self.bia, nome="Do jogador")

        self.assertEqual([p["nome"] for p in self.client.get(f"/personagem/{irisa.pk}/poderes-usuario/").data], ["Do jogador"])
        resposta = self.client.post(f"/personagem/{irisa.pk}/poderes-usuario/{do_jogador.pk}/copiar/")
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)

    def test_jogador_que_so_le_a_ficha_nao_ve_a_conta_do_dono(self):
        kael = Personagem.objects.create(usuario=self.ana, nome="Kael")
        self.campanha.personagens.add(kael)
        PoderUsuario.objects.create(usuario=self.ana, nome="Passo Sombrio")
        self.client.force_authenticate(self.bia)

        self.assertEqual(self.client.get(f"/personagem/{kael.pk}/poderes-usuario/").status_code, status.HTTP_403_FORBIDDEN)


class PerfilPublicoTests(BasePerfil):

    def test_quem_divide_campanha_ve_o_perfil_sem_email(self):
        resposta = self.client.get(f"/usuario/{self.bia.pk}/")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["username"], "bia")
        self.assertNotIn("email", resposta.data)

    def test_estranho_recebe_404(self):
        self.client.force_authenticate(self.estranho)
        self.assertEqual(self.client.get(f"/usuario/{self.ana.pk}/").status_code, status.HTTP_404_NOT_FOUND)


class NotasNoPerfilTests(BasePerfil):

    def _nota(self, alvo, texto="Boa sessão!"):
        return self.client.post(
            "/campanha/notas/",
            {"content_type": "usuario", "object_id": alvo.pk, "conteudo": texto},
            format="json",
        )

    def test_quem_joga_junto_escreve_e_le_o_mural(self):
        self.client.force_authenticate(self.bia)
        criada = self._nota(self.ana)
        self.assertEqual(criada.status_code, status.HTTP_201_CREATED, criada.data)
        self.assertEqual(criada.data["autor"]["tipo"], "usuario")

        self.client.force_authenticate(self.ana)
        lidas = self.client.get(f"/campanha/notas/?content_type=usuario&object_id={self.ana.pk}")
        self.assertEqual(len(lidas.data), 1)

    def test_estranho_nao_escreve_nem_le(self):
        self.client.force_authenticate(self.estranho)
        self.assertEqual(self._nota(self.ana).status_code, status.HTTP_403_FORBIDDEN)
        lidas = self.client.get(f"/campanha/notas/?content_type=usuario&object_id={self.ana.pk}")
        self.assertEqual(lidas.status_code, status.HTTP_403_FORBIDDEN)

    def test_dono_do_perfil_remove_nota_alheia(self):
        self.client.force_authenticate(self.bia)
        pk = self._nota(self.ana).data["id"]

        self.client.force_authenticate(self.ana)
        self.assertEqual(self.client.delete(f"/campanha/notas/{pk}/").status_code, status.HTTP_204_NO_CONTENT)

    def test_mestre_de_outra_mesa_nao_modera_o_mural(self):
        # Bia é mestra de uma mesa onde Ana joga — isso NÃO dá a Bia poder
        # sobre o mural da Ana (ver `campanhas_do_objeto_notavel`).
        mesa_da_bia = Campanha.objects.create(mestre=self.bia, nome="Mesa da Bia")
        mesa_da_bia.jogadores.add(self.ana, self.estranho)
        self.client.force_authenticate(self.estranho)
        pk = self._nota(self.ana).data["id"]

        self.client.force_authenticate(self.bia)
        self.assertEqual(self.client.delete(f"/campanha/notas/{pk}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Nota.objects.filter(pk=pk).exists())

    def test_nota_de_perfil_nao_aceita_personagem(self):
        self.client.force_authenticate(self.bia)
        irisa = Personagem.objects.create(usuario=self.bia, nome="Irisa")
        self.campanha.personagens.add(irisa)

        resposta = self.client.post(
            "/campanha/notas/",
            {"content_type": "usuario", "object_id": self.ana.pk, "conteudo": "oi", "personagem": irisa.pk},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)


class OutrosUsuariosTests(BasePerfil):

    def setUp(self):
        super().setUp()
        self.admin = Usuario.objects.create_superuser(username="admin", password="SenhaForte123!")
        Personagem.objects.create(usuario=self.admin, nome="Do Admin")
        Personagem.objects.create(usuario=self.bia, nome="Irisa")
        Campanha.objects.create(mestre=self.admin, nome="Mesa do Admin").jogadores.add(self.admin)

    def test_superusuario_ve_so_o_que_e_dos_outros_com_o_dono(self):
        self.client.force_authenticate(self.admin)

        personagens = self.client.get("/usuario/outros/personagens/").data
        self.assertEqual([p["nome"] for p in personagens], ["Irisa"])
        self.assertEqual(personagens[0]["dono"]["username"], "bia")

        campanhas = self.client.get("/usuario/outros/campanhas/").data
        self.assertEqual([c["nome"] for c in campanhas], ["Cinzas"])

    def test_abas_pessoais_do_superusuario_sao_so_dele(self):
        self.client.force_authenticate(self.admin)

        self.assertEqual([p["nome"] for p in self.client.get("/usuario/me/personagens/").data], ["Do Admin"])
        self.assertEqual([c["nome"] for c in self.client.get("/usuario/me/campanhas/").data], ["Mesa do Admin"])
        self.assertTrue(self.client.get("/usuario/me/").data["is_superuser"])

    def test_usuario_comum_recebe_403(self):
        self.assertEqual(self.client.get("/usuario/outros/personagens/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/usuario/outros/campanhas/").status_code, status.HTTP_403_FORBIDDEN)
