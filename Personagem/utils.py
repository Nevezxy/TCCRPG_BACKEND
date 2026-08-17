from .models import Atributo, Status, Defesa, Pericia

def criar_dados_iniciais_personagem(personagem, modelo):
    
    if modelo == "dnd":
        #ATRIBUTOS
        forca = Atributo.objects.create(
            personagem=personagem,
            nome="For",
            valor=1,
            cor="#EE0000",
            icone="Swords"
        )
        
        destreza = Atributo.objects.create(
            personagem=personagem,
            nome="Des",
            valor=1,
            cor="#00FFFF",
            icone="Zap"
        )
        
        constituicao = Atributo.objects.create(
            personagem=personagem,
            nome="Con",
            valor=1,
            cor="#00FF99",
            icone="Heart"
        )
        
        inteligencia = Atributo.objects.create(
            personagem=personagem,
            nome="Int",
            valor=1,
            cor="#FFC000",
            icone="Brain"
        )
        
        sabedoria = Atributo.objects.create(
            personagem=personagem,
            nome="Sab",
            valor=1,
            cor="#CC00FF",
            icone="Eye"
        )
        
        carisma = Atributo.objects.create(
            personagem=personagem,
            nome="Car",
            valor=1,
            cor="#FF0066",
            icone="Flame"
        )
        
        #STATUS
        Status.objects.create(
            personagem=personagem,
            nome="Pontos de Vida",
            barra=True,
            cor="#00FF99",
            valor_max=10,
            valor_atual=10,
            atributo=constituicao,
            atributo_nivel=True
        )
        
        Status.objects.create(
            personagem=personagem,
            nome="Espaços de Magia (Nível 1)",
            barra=True,
            cor="#FF0066",
            valor_max=2,
            valor_atual=2,
            sub_status=True,
        )
        
        Status.objects.create(
            personagem=personagem,
            nome="Movimento",
            barra=False,
            cor="#FFFFFF",
            valor_max=10,
            valor_atual=10,
        )
        
        #DEFESAS
        Defesa.objects.create(
            personagem=personagem,
            nome="Classe de Armadura",
            atributo=destreza,
            valor=10,
            icone="Shield"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save For",
            atributo=forca,
            valor=0,
            icone="Swords"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save Des",
            atributo=destreza,
            valor=0,
            icone="Zap"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save Con",
            atributo=constituicao,
            valor=0,
            icone="Heart"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save Int",
            atributo=inteligencia,
            valor=0,
            icone="Book"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save Sab",
            atributo=sabedoria,
            valor=0,
            icone="Brain"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="Save Car",
            atributo=carisma,
            valor=0,
            icone="Eye"
        )
        
        Defesa.objects.create(
            personagem=personagem,
            nome="DT",
            valor=8,
            icone="Flame"
        )
        
        #PERÍCIAS
        Pericia.objects.create(
            personagem=personagem,
            nome="Atletismo",
            atributo=forca,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Acrobacia",
            atributo=destreza,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Furtividade",
            atributo=destreza,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Prestidigitação",
            atributo=destreza,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Arcanismo",
            atributo=inteligencia,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="História",
            atributo=inteligencia,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Investigação",
            atributo=inteligencia,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Natureza",
            atributo=inteligencia,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Religião",
            atributo=inteligencia,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Lidar com Animais",
            atributo=sabedoria,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Intuição",
            atributo=sabedoria,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Medicina",
            atributo=sabedoria,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Percepção",
            atributo=sabedoria,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Sobrevivência",
            atributo=sabedoria,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Atuação",
            atributo=carisma,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Enganação",
            atributo=carisma,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Intimidação",
            atributo=carisma,
            somar_atributo=True
        )
        
        Pericia.objects.create(
            personagem=personagem,
            nome="Persuasão",
            atributo=carisma,
            somar_atributo=True
        )
        
        return "Modelo D&D criado com sucesso!"
    
    #ATRIBUTOS
    agilidade = Atributo.objects.create(
        personagem=personagem,
        nome="Agi",
        valor=1,
        cor="#00FFFF",
        icone = "Zap"
    )
    
    forca = Atributo.objects.create(
        personagem=personagem,
        nome="For",
        valor=1,
        cor="#EE0000",
        icone = "Swords"
    )
    
    intelecto = Atributo.objects.create(
        personagem=personagem,
        nome="Int",
        valor=1,
        cor="#FFC000",
        icone = "Brain"
    )
    
    presenca = Atributo.objects.create(
        personagem=personagem,
        nome="Pre",
        valor=1,
        cor="#FF0066",
        icone = "Flame"
    )
        
    vigor = Atributo.objects.create(
        personagem=personagem,
        nome="Vig",
        valor=1,
        cor="#00FF99",
        icone = "Heart"
    )
    
    #STATUS
    Status.objects.create(
        personagem=personagem,
        nome="Pontos de Vida",
        barra=True,
        cor="#00FF99",
        valor_max=10,
        valor_atual=10,
        atributo=vigor,
        atributo_nivel=True
    )
    
    Status.objects.create(
        personagem=personagem,
        nome="Pontos de Energia",
        barra=True,
        cor="#FF0066",
        valor_max=10,
        valor_atual=10,
        atributo=presenca,
        atributo_nivel=True
    )
    
    Status.objects.create(
        personagem=personagem,
        nome="Movimento",
        barra=False,
        cor="#FFFFFF",
        valor_max=10,
        valor_atual=10,
        atributo=agilidade,
        atributo_nivel=False
    )

    #DEFESA
    Defesa.objects.create(
        personagem=personagem,
        nome="Classe de Armadura",
        atributo=agilidade,
        valor=10
    )
    
    Defesa.objects.create(
        personagem=personagem,
        nome="Redução de Dano",
        valor=0
    )

    Defesa.objects.create(
        personagem=personagem,
        nome="Bloqueio",
        valor=0
    )
    
    Defesa.objects.create(
        personagem=personagem,
        nome="Contra Ataque",
        valor=0
    )
    
    Defesa.objects.create(
        personagem=personagem,
        nome="Esquiva",
        valor=0
    )
    
    
    Defesa.objects.create(
        personagem=personagem,
        nome="Fortitude",
        valor=0,
        icone="Heart",
    )
    
    Defesa.objects.create(
        personagem=personagem,
        nome="Reflexos",
        valor=0,
        icone="Zap",
    )

    Defesa.objects.create(
        personagem=personagem,
        nome="Vontade",
        valor=0,
        icone="Brain"
    )
    
    Defesa.objects.create(
        personagem=personagem,
        nome="DT",
        atributo=presenca,
        valor=10,
        icone="Flame"
    )

    #PERÍCIAS
    Pericia.objects.create(
        personagem=personagem,
        nome="Acrobacia",
        atributo=agilidade
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Adestramento",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Atletismo",
        atributo=forca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Diplomacia",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Enganação",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Furtividade",
        atributo=agilidade
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Iniciativa",
        atributo=agilidade
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Intimidação",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Intuição",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Investigação",
        atributo=intelecto
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Lutar",
        atributo=forca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Medicina",
        atributo=intelecto
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Mirar",
        atributo=agilidade
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Percepção",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Pilotar",
        atributo=agilidade
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Profissão",
        atributo=None
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Saber Geral",
        atributo=intelecto
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Sobrevivência",
        atributo=intelecto
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Tática",
        atributo=intelecto
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Técnica",
        atributo=presenca
    )

    Pericia.objects.create(
        personagem=personagem,
        nome="Sorte",
        atributo=None
    )