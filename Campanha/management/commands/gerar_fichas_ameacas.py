"""
Gera fichas de ameaça genéricas (NPC/Criatura) e salva como FichaPreset.

    python manage.py gerar_fichas_ameacas [--usuario-id 1] [--apply]

SEM `--apply` nada é gravado: só lista quantas fichas seriam criadas (dry-run).

Cobre as 4 Classes (Assassino, Guerreiro, Suporte, Tank) x 3 Papéis de
Combate (Chefe, Rival, Servo) x 22 Níveis (1/4, 1/2, 1 a 20) = 264
predefinições. Todos os números vêm do Capítulo 9 - "Criação de Ameaças" do
manual do sistema (Tabelas de Balanceamento CHEFE/RIVAL/SERVO e a seção
Classes), aplicados via `get_or_create` — rodar de novo não duplica nem
sobrescreve fichas já criadas com o mesmo nome.

Decisões de projeto que não estavam explícitas no manual (confirmadas com o
usuário ao longo da conversa que gerou este comando):
  - O cap de atributo dos níveis 1/4 e 1/2 ("Buxa") usa o mesmo valor de
    Iniciante (3), já que o manual não define esse tier separadamente.
  - `tcc-level` é `<input type="number">` no editor legado (não aceita
    frações) — os níveis 1/4 e 1/2 são gravados como "0.25"/"0.5" no JSON,
    com a fração explícita no nome da predefinição.
  - Dentro de cada classe, a alocação de pontos de atributo segue a ordem de
    prioridade da identidade pedida (ex.: Guerreiro enche Força até o cap,
    depois Agilidade, depois Vigor, depois Presença/Intelecto), conforme o
    texto do manual: "Distribua focando nos atributos mais fortes para a
    Classe da criatura."
  - Dano Médio é expresso em dados (pedido do usuário): 2 a 6 dados fixos
    por golpe + modificador plano cobrindo o resto da escala — evita pools
    de dado absurdos (tipo 50+d6) em níveis altos, do jeito que bosses de
    outros sistemas também fazem.
"""

import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from Campanha.models import FichaPreset

NIVEIS = ["1/4", "1/2", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
          "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"]


def categoria(ord_nivel):
    if ord_nivel <= 1:
        return "Buxa"
    if ord_nivel <= 6:
        return "Iniciante"
    if ord_nivel <= 11:
        return "Mediano"
    if ord_nivel <= 16:
        return "Avançado"
    return "Supremo"


CAP_ATRIBUTO = {"Buxa": 3, "Iniciante": 3, "Mediano": 4, "Avançado": 5, "Supremo": 6}

# cada linha: (vida_base, vida_mult, atributos_pool, atk, dano_medio, defesa_base,
#              resist_forte, resist_media, resist_fraca, dt)
TABELAS = {
    "Chefe": [
        (10, 5, 4, 4, 10, 17, 2, 0, -2, 17),
        (30, 5, 5, 5, 12, 18, 3, 1, -1, 18),
        (50, 10, 6, 6, 23, 23, 4, 2, 0, 19),
        (80, 10, 7, 8, 29, 24, 5, 3, 1, 20),
        (110, 10, 8, 9, 34, 25, 6, 4, 2, 21),
        (140, 10, 9, 10, 45, 26, 7, 5, 3, 22),
        (170, 10, 10, 11, 55, 27, 8, 6, 4, 23),
        (220, 25, 11, 16, 79, 27, 9, 7, 5, 24),
        (280, 25, 12, 17, 86, 28, 11, 9, 7, 25),
        (320, 25, 13, 18, 93, 29, 12, 10, 8, 26),
        (360, 25, 14, 19, 100, 30, 13, 11, 9, 27),
        (400, 25, 15, 20, 107, 31, 14, 12, 10, 28),
        (350, 50, 16, 25, 129, 31, 15, 13, 11, 29),
        (400, 50, 17, 26, 131, 32, 17, 15, 13, 30),
        (450, 50, 18, 27, 138, 33, 18, 16, 14, 31),
        (500, 50, 19, 28, 145, 34, 19, 17, 15, 32),
        (550, 50, 20, 29, 152, 35, 20, 18, 16, 33),
        (360, 100, 21, 30, 177, 35, 21, 19, 18, 34),
        (420, 100, 22, 31, 184, 36, 23, 21, 19, 35),
        (480, 100, 23, 32, 191, 37, 25, 23, 21, 36),
        (540, 100, 24, 33, 198, 38, 26, 24, 22, 37),
        (600, 100, 25, 34, 205, 39, 27, 25, 23, 38),
    ],
    "Rival": [
        (3, 1, 3, 4, 5, 11, 0, -2, -4, 13),
        (8, 1, 3, 5, 6, 12, 1, -1, -3, 14),
        (14, 2, 4, 6, 11, 17, 2, 0, -2, 15),
        (21, 2, 4, 7, 14, 18, 3, 1, -1, 16),
        (29, 2, 5, 8, 17, 19, 4, 2, 0, 17),
        (36, 2, 5, 9, 22, 20, 5, 3, 1, 18),
        (44, 2, 6, 10, 27, 21, 6, 4, 2, 19),
        (65, 5, 6, 11, 39, 22, 7, 5, 3, 20),
        (75, 5, 7, 12, 43, 23, 9, 7, 5, 21),
        (85, 5, 7, 13, 46, 24, 10, 8, 6, 22),
        (95, 5, 8, 14, 50, 25, 11, 9, 7, 23),
        (105, 5, 8, 15, 53, 26, 12, 10, 8, 24),
        (100, 10, 9, 16, 64, 27, 13, 11, 9, 25),
        (110, 10, 9, 17, 65, 28, 15, 13, 11, 26),
        (125, 10, 10, 18, 69, 29, 16, 14, 12, 27),
        (135, 10, 10, 19, 72, 30, 17, 15, 13, 28),
        (150, 10, 11, 20, 76, 31, 18, 16, 14, 29),
        (150, 15, 11, 21, 88, 32, 20, 18, 16, 30),
        (165, 15, 12, 22, 92, 33, 21, 19, 17, 31),
        (180, 15, 12, 23, 95, 34, 23, 21, 19, 32),
        (195, 15, 13, 24, 96, 35, 24, 22, 20, 33),
        (210, 15, 14, 25, 102, 36, 25, 23, 21, 34),
    ],
    "Servo": [
        (1, 0, 0, 0, 5, 10, -2, -4, -6, 10),
        (2, 0, 0, 1, 6, 10, -1, -3, -5, 11),
        (2, 1, 1, 2, 11, 11, 0, -2, -4, 12),
        (4, 1, 1, 3, 14, 12, 1, -1, -3, 13),
        (6, 1, 2, 4, 17, 17, 2, 0, -2, 14),
        (8, 1, 2, 5, 22, 18, 3, 1, -1, 15),
        (10, 1, 3, 6, 27, 19, 4, 2, 0, 16),
        (13, 2, 3, 7, 39, 20, 5, 3, 1, 17),
        (16, 2, 4, 8, 43, 21, 6, 4, 2, 18),
        (18, 2, 4, 9, 46, 22, 7, 5, 3, 19),
        (21, 2, 5, 10, 50, 23, 9, 7, 5, 20),
        (23, 2, 5, 11, 53, 24, 10, 8, 6, 21),
        (22, 3, 6, 12, 64, 25, 11, 9, 7, 22),
        (25, 3, 6, 13, 65, 26, 12, 10, 8, 23),
        (29, 3, 7, 14, 69, 27, 13, 11, 9, 24),
        (31, 3, 7, 15, 72, 28, 15, 13, 11, 25),
        (35, 3, 8, 16, 76, 29, 16, 14, 12, 26),
        (36, 4, 8, 17, 88, 30, 17, 15, 13, 27),
        (40, 4, 9, 18, 92, 31, 18, 16, 14, 28),
        (44, 4, 9, 19, 95, 32, 20, 18, 16, 29),
        (47, 4, 10, 20, 96, 33, 22, 19, 17, 30),
        (51, 4, 10, 21, 102, 34, 23, 21, 19, 31),
    ],
}

CAMPOS = ["vida_base", "vida_mult", "atributos_pool", "atk", "dano_medio",
          "defesa_base", "resist_forte", "resist_media", "resist_fraca", "dt"]

CLASSES = {
    "Guerreiro": {
        "passos": {"atk": 1, "defesa_base": 1, ("resist_forte", "resist_media", "resist_fraca"): -1, "dt": -1},
        "prioridade": [["for"], ["agi"], ["vig"], ["pre", "int"]],
        "ataque_attr": "for",
        "arma": ("Golpe de Espada", "Espada longa", "Arma", 10, "Corpo a corpo"),
        "passiva_extra": None,
        "resist_map": {"forte": "fort", "media": "ref", "fraca": "von"},
        "sentido_media": "iniciativa",
    },
    "Tank": {
        "passos": {"vida_base": 1, "defesa_base": 1, "dt": -1},
        "atributo_pool_delta": -2,
        "prioridade": [["for"], ["vig"], ["agi"], ["pre", "int"]],
        "ataque_attr": "for",
        "arma": ("Golpe de Maça", "Maça e escudo", "Arma", 8, "Corpo a corpo"),
        "passiva_extra": "reducao_danos",
        "resist_map": {"forte": "fort", "media": "von", "fraca": "ref"},
        "sentido_media": "percepcao",
    },
    "Assassino": {
        "passos": {"dano_medio": 1, "atk": 1, "vida_base": -1, "defesa_base": -1},
        "prioridade": [["agi"], ["pre", "int"], ["vig"], ["for"]],
        "ataque_attr": "agi",
        "arma": ("Lâmina Arremessada", "Adagas de arremesso", "Arma", 6, "À distância (arremesso)"),
        "passiva_extra": "ataque_furtivo",
        "resist_map": {"forte": "ref", "media": "fort", "fraca": "von"},
        "sentido_media": "iniciativa",
    },
    "Suporte": {
        "passos": {"dt": 2, "vida_base": -1, "defesa_base": -1},
        "prioridade": [["pre"], ["int"], ["vig"], ["agi", "for"]],
        "ataque_attr": "pre",
        "arma": ("Investida Mística", "Cajado", "Arma", 6, "À distância (mística)"),
        "passiva_extra": "cura_acelerada",
        "resist_map": {"forte": "von", "media": "fort", "fraca": "ref"},
        "sentido_media": "percepcao",
    },
}

RD_POR_CATEGORIA = {"Buxa": 2, "Iniciante": 5, "Mediano": 10, "Avançado": 20, "Supremo": 40}
FURTIVO_POR_CATEGORIA = {"Buxa": (1, 6), "Iniciante": (2, 6), "Mediano": (4, 6), "Avançado": (6, 6), "Supremo": (8, 6)}
CURA_POR_CATEGORIA = {"Buxa": 2, "Iniciante": 5, "Mediano": 10, "Avançado": 20, "Supremo": 50}
PERICIA_POR_ATRIBUTO = {"for": "Lutar", "agi": "Mirar", "pre": "Técnica"}


def linha(papel, ord_nivel):
    return dict(zip(CAMPOS, TABELAS[papel][ord_nivel]))


def clamp(i):
    return max(0, min(21, i))


def dado_para_media(alvo, tamanho_dado):
    """Acha (N, tamanho_dado, flat) tal que N*tamanho_dado.avg + flat == alvo.

    N fica travado entre 2 e 6 dados — quem carrega a escala em tiers altos
    é o modificador fixo, não o número de dados (senão viram pools tipo
    50d6 em níveis 16-20).
    """
    media_dado = (tamanho_dado + 1) / 2
    n = round(alvo / media_dado / 2) * 2
    n = max(2, min(6, n))
    base = n * media_dado
    flat = alvo - base
    if flat == int(flat):
        flat = int(flat)
    return n, tamanho_dado, flat


def formatar_dano(n, s, flat, alvo):
    sinal = f"+{flat}" if flat > 0 else (f"{flat}" if flat < 0 else "")
    return f"{n}d{s}{sinal} ({alvo})"


def distribuir_atributos(pool, prioridade, cap):
    """Enche os atributos até o cap, na ordem de prioridade da identidade da
    classe — grupos com mais de um atributo dividem os pontos em rodízio."""
    attrs = {"agi": 1, "for": 1, "int": 1, "pre": 1, "vig": 1}
    restante = pool
    for grupo in prioridade:
        progresso = True
        while restante > 0 and progresso:
            progresso = False
            for a in grupo:
                if restante <= 0:
                    break
                if attrs[a] < cap:
                    attrs[a] += 1
                    restante -= 1
                    progresso = True
    return attrs


def build_ficha(papel, classe_nome, ord_nivel, timestamp_base):
    cfg = CLASSES[classe_nome]
    cat = categoria(ord_nivel)
    cap = CAP_ATRIBUTO[cat]
    valores = linha(papel, ord_nivel)

    for campo, passo in cfg.get("passos", {}).items():
        alvo = clamp(ord_nivel + passo)
        linha_alvo = linha(papel, alvo)
        campos = campo if isinstance(campo, tuple) else (campo,)
        for c in campos:
            valores[c] = linha_alvo[c]

    pool = max(0, valores["atributos_pool"] + cfg.get("atributo_pool_delta", 0))
    attrs = distribuir_atributos(pool, cfg["prioridade"], cap)

    vida = valores["vida_base"] + valores["vida_mult"] * attrs["vig"]
    defesa = valores["defesa_base"] + attrs["agi"]

    resist_valores = {"forte": valores["resist_forte"], "media": valores["resist_media"], "fraca": valores["resist_fraca"]}
    defense = {"ca": str(defesa)}
    for chave_texto, campo_defesa in cfg["resist_map"].items():
        defense[campo_defesa] = str(resist_valores[chave_texto])

    sentido_media_campo = cfg["sentido_media"]
    sentido_fraco_campo = "percepcao" if sentido_media_campo == "iniciativa" else "iniciativa"
    sentidos_valor = {sentido_media_campo: resist_valores["media"], sentido_fraco_campo: resist_valores["fraca"]}

    atk = valores["atk"]
    ataque_attr_valor = attrs[cfg["ataque_attr"]]
    nome_arma, item_nome, item_tipo, dado_tam, tipo_ataque = cfg["arma"]
    n, s, flat = dado_para_media(valores["dano_medio"], dado_tam)
    dano_str = formatar_dano(n, s, flat, valores["dano_medio"])
    teste_str = f"{ataque_attr_valor}d+{atk}" if atk >= 0 else f"{ataque_attr_valor}d{atk}"

    nivel_label = NIVEIS[ord_nivel]
    nome_completo = f"{classe_nome} {papel} Nv. {nivel_label} ({cat})"
    # tcc-level é <input type="number"> no editor legado — não aceita frações literais
    nivel_json = {"1/4": "0.25", "1/2": "0.5"}.get(nivel_label, nivel_label)

    abilities_active = [{
        "name": nome_arma,
        "action": "2 Ações",
        "custom": "",
        "desc": f"{tipo_ataque} | TESTE: {teste_str} | DANO: {dano_str}",
    }]
    abilities_passive = []

    if cfg["passiva_extra"] == "ataque_furtivo":
        qtd, tam = FURTIVO_POR_CATEGORIA[cat]
        media_furtivo = round(qtd * (tam + 1) / 2)
        abilities_passive.append({
            "name": "Ataque Furtivo",
            "desc": f"Uma vez por rodada, causa {qtd}d{tam} ({media_furtivo}) de dano adicional contra um alvo Desprevenido ou Flanqueado.",
        })
    elif cfg["passiva_extra"] == "reducao_danos":
        abilities_passive.append({
            "name": "Redução de Danos",
            "desc": f"Recebe RD {RD_POR_CATEGORIA[cat]} contra um tipo de dano à escolha do mestre.",
        })
    elif cfg["passiva_extra"] == "cura_acelerada":
        abilities_passive.append({
            "name": "Cura Acelerada (Apoio)",
            "desc": f"No início do turno, recupera {CURA_POR_CATEGORIA[cat]} PV — em si mesma ou em um aliado a até 6m, à escolha do mestre.",
        })
    else:
        abilities_passive.append({
            "name": "Ataque de Oportunidade",
            "desc": "Uma vez por rodada, se um ser adjacente se mover para fora do seu alcance voluntariamente, pode fazer uma reação e atacá-lo.",
        })

    if papel == "Chefe":
        # Chefes têm 2 habilidades por categoria (regra do manual)
        dano3_avg = round(valores["dano_medio"] * 1.5)
        n3, s3, flat3 = dado_para_media(dano3_avg, dado_tam)
        abilities_active.append({
            "name": f"{nome_arma} (Investida)",
            "action": "3 Ações",
            "custom": "",
            "desc": (f"{tipo_ataque} | TESTE: {teste_str} | DANO: {formatar_dano(n3, s3, flat3, dano3_avg)} "
                     "— golpe mais pesado (ajuste de +50% do dano por ação extra)"),
        })
        abilities_passive.append({
            "name": "Maior que a Morte",
            "desc": "Enquanto tiver pelo menos metade dos PV, é imune a efeitos de morte instantânea.",
        })

    skill_secundaria = {
        "Guerreiro": ("Atletismo (For)", atk - 2),
        "Tank": ("Intimidação (Pre)", atk - 2),
        "Assassino": ("Furtividade (Agi)", atk - 2),
        "Suporte": ("Diplomacia (Pre)", atk - 2),
    }[classe_nome]
    nome_pericia_principal = f"{PERICIA_POR_ATRIBUTO[cfg['ataque_attr']]} ({cfg['ataque_attr'].capitalize()})"

    dados = {
        "id": timestamp_base,
        "name": nome_completo,
        "template": "tcc",
        "schema": 3,
        "staticInfo": {"level": nivel_json, "type": papel, "hp": f"{vida} / {vida}"},
        "attributes": {k: str(v) for k, v in attrs.items()},
        "defense": defense,
        # `resistencias` (texto livre) guarda o DT das Habilidades da
        # criatura — não é o teste de acerto do ataque físico (já está em
        # TESTE); é o valor que os ALVOS precisam bater para resistir às
        # habilidades dela.
        "resistance": {"imunidades": "", "resistencias": f"DT das Habilidades: {valores['dt']}", "vulnerabilidades": ""},
        "lists": {
            "sense": [
                {"name": "Percepção", "custom": "", "value": str(sentidos_valor["percepcao"])},
                {"name": "Iniciativa", "custom": "", "value": str(sentidos_valor["iniciativa"])},
            ],
            "movement": [
                {"type": "Terrestre", "value": f"{7.5 + attrs['agi']:g}m".replace(".", ","), "squares": False},
            ],
            "skill": [
                {"name": nome_pericia_principal, "value": f"+{atk}"},
                {"name": skill_secundaria[0], "value": f"+{skill_secundaria[1]}" if skill_secundaria[1] >= 0 else str(skill_secundaria[1])},
            ],
            "equipment": [
                {"name": item_nome, "type": item_tipo, "custom": "", "desc": tipo_ataque},
            ],
            "passiveAbility": abilities_passive,
            "activeAbility": abilities_active,
        },
    }
    return nome_completo, dados


class Command(BaseCommand):
    help = "Gera as 264 fichas de ameaça (4 Classes x 3 Papéis x 22 Níveis) como FichaPreset (dry-run por padrão)."

    def add_arguments(self, parser):
        parser.add_argument("--usuario-id", type=int, default=1, help="ID do usuário dono das predefinições (padrão: 1).")
        parser.add_argument("--apply", action="store_true", help="Grava de fato (sem isto, só lista quantas seriam criadas).")

    def handle(self, *args, **opcoes):
        usuario_id = opcoes["usuario_id"]
        aplicar = opcoes["apply"]

        Usuario = get_user_model()
        if not Usuario.objects.filter(pk=usuario_id).exists():
            raise CommandError(f"Usuário id={usuario_id} não existe.")

        papeis = ["Chefe", "Rival", "Servo"]
        classes = ["Assassino", "Guerreiro", "Suporte", "Tank"]

        planejadas = []
        timestamp_base = int(time.time() * 1000)
        contador = 0
        for papel in papeis:
            for classe in classes:
                for ord_nivel in range(len(NIVEIS)):
                    nome, dados = build_ficha(papel, classe, ord_nivel, timestamp_base + contador)
                    planejadas.append((nome, dados))
                    contador += 1

        self.stdout.write(f"{len(planejadas)} fichas planejadas para usuario_id={usuario_id}.")

        if not aplicar:
            for nome, _ in planejadas[:10]:
                self.stdout.write(f"  {nome}")
            if len(planejadas) > 10:
                self.stdout.write(f"  ... e mais {len(planejadas) - 10}.")
            self.stdout.write(self.style.NOTICE("Dry-run: nada foi gravado. Use --apply para criar de fato."))
            return

        criadas, existentes = 0, 0
        with transaction.atomic():
            for nome, dados in planejadas:
                _, foi_criado = FichaPreset.objects.get_or_create(
                    usuario_id=usuario_id, nome=nome, defaults={"dados": dados}
                )
                criadas += foi_criado
                existentes += not foi_criado

        self.stdout.write(self.style.SUCCESS(f"Criadas: {criadas} · já existentes (mantidas como estavam): {existentes}"))
