#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geração de surrogates verossímeis, Fase 4 da extensão de corpus.

Substitui cada entidade sensível por um valor fictício que **parece real**, de modo que
o corpus resultante preserve as características linguísticas do original e continue útil
para treinar modelos de NER.

Especificação completa: `01_ESPEC_Corpus_Surrogates.md` (Google Drive).

Três níveis de consistência, que não podem ser confundidos
==========================================================
1. Dentro de um corpus, a mesma entidade real recebe sempre o mesmo surrogate.
2. Entre homônimos, pessoas diferentes com o mesmo nome real recebem surrogates
                          diferentes. A chave é a IDENTIDADE (hash do paciente), não a
                          cadeia de caracteres.
3. Entre corpora, a mesma entidade real recebe surrogates diferentes em cada
                          versão gerada. É o que dificulta a reidentificação e o que
                          permite gerar N versões da mesma base.

Restrição inegociável
---------------------
Os surrogates vêm de **fonte externa** (catálogos deste módulo). Nunca do próprio corpus.
Sortear o nome de um paciente real para substituir outro não anonimiza nada. Apenas
embaralha, e mantém dado real em circulação.

Sobre a semente
---------------
A geração é determinística dado (seed, entidade). Isso é necessário para refazer o
experimento. Como os surrogates vêm de catálogo público, inverter a função com a semente
devolve apenas a posição de um nome numa lista pública, informação inútil. Se algum dia
os catálogos passarem a ser derivados do corpus, esta propriedade se perde e a semente
não pode mais ser publicada.
"""

import hashlib
import random
import re
import unicodedata

# ---------------------------------------------------------------------------
# Catálogos de valores fictícios. Vêm de fonte externa e nunca do corpus.
#
# Listas curtas de partida. Para o experimento final devem ser ampliadas com dados
# públicos (IBGE para nomes, Correios para logradouros), mantendo a distribuição
# realista: sobrenomes brasileiros seguem uma cauda longa dominada por poucos nomes
# muito frequentes, e replicar isso importa para a verossimilhança.
# ---------------------------------------------------------------------------

PRENOMES_M = [
    'Antônio', 'Carlos', 'Eduardo', 'Fernando', 'Gustavo', 'Henrique', 'Joaquim',
    'Leonardo', 'Marcelo', 'Nelson', 'Otávio', 'Paulo', 'Ricardo', 'Rodrigo',
    'Sérgio', 'Thiago', 'Vinícius', 'Wagner', 'Alberto', 'Bruno', 'Cláudio',
    'Diego', 'Emerson', 'Fábio', 'Gilberto', 'Hélio', 'Ivan', 'Jorge', 'Luciano',
    'Maurício', 'Nilton', 'Osvaldo', 'Rafael', 'Sebastião', 'Valdir',
    'José', 'João', 'Pedro', 'Luiz', 'Francisco', 'Manoel', 'Raimundo',
]

PRENOMES_F = [
    'Adriana', 'Beatriz', 'Cristina', 'Daniela', 'Eliane', 'Fernanda', 'Gabriela',
    'Helena', 'Isabel', 'Juliana', 'Karina', 'Luciana', 'Mariana', 'Natália',
    'Patrícia', 'Renata', 'Simone', 'Tatiana', 'Vanessa', 'Amanda', 'Bianca',
    'Camila', 'Débora', 'Elaine', 'Flávia', 'Giovana', 'Ingrid', 'Joana',
    'Larissa', 'Márcia', 'Nádia', 'Priscila', 'Rosana', 'Silvana', 'Vera',
    'Maria', 'Ana', 'Francisca', 'Antônia', 'Terezinha', 'Lúcia', 'Rosa',
]

SOBRENOMES = [
    'Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves',
    'Pereira', 'Lima', 'Gomes', 'Ribeiro', 'Carvalho', 'Almeida', 'Lopes',
    'Soares', 'Fernandes', 'Vieira', 'Barbosa', 'Rocha', 'Dias', 'Nascimento',
    'Andrade', 'Moreira', 'Nunes', 'Marques', 'Machado', 'Mendes', 'Freitas',
    'Cardoso', 'Ramos', 'Gonçalves', 'Santana', 'Teixeira', 'Araújo', 'Cunha',
]

# Partícula correta para cada sobrenome. Em português a partícula concorda com o
# SOBRENOME, não com o prenome: diz-se "Adriana do Nascimento", nunca "Adriana da
# Nascimento". Errar isso produz nome que soa falso para falante nativo, e num
# experimento cuja hipótese é justamente que os surrogates são verossímeis, um nome
# obviamente sintético contamina o resultado.
# Sobrenome ausente deste mapa não recebe partícula.
PARTICULA_POR_SOBRENOME = {
    'Silva': 'da', 'Rocha': 'da', 'Cunha': 'da', 'Costa': 'da', 'Luz': 'da',
    'Santos': 'dos', 'Reis': 'dos', 'Anjos': 'dos',
    'Nascimento': 'do', 'Carmo': 'do', 'Amaral': 'do', 'Prado': 'do', 'Vale': 'do',
    'Souza': 'de', 'Oliveira': 'de', 'Almeida': 'de', 'Andrade': 'de',
    'Freitas': 'de', 'Araújo': 'de', 'Carvalho': 'de', 'Lima': 'de',
    'Moraes': 'de', 'Paula': 'de', 'Assis': 'de',
}

TIPOS_LOGRADOURO = ['Rua', 'Avenida', 'Travessa', 'Alameda', 'Praça', 'Rodovia']

NOMES_LOGRADOURO = [
    'das Acácias', 'dos Ipês', 'Antônio Pereira', 'Boa Vista', 'do Cedro',
    'Espírito Santo', 'Flor do Campo', 'Guanabara', 'Independência', 'Jacarandá',
    'Laranjeiras', 'Monte Belo', 'Nova Esperança', 'Ouro Preto', 'Paraíso',
    'Quatro Rodas', 'Rio Branco', 'Santa Luzia', 'Três Irmãos', 'Vale Verde',
]

# Municípios do ES, manter a distribuição geográfica do corpus original.
# Trocar por cidade de outro estado alteraria a distribuição e a verossimilhança.
MUNICIPIOS_ES = [
    'Vitória', 'Vila Velha', 'Serra', 'Cariacica', 'Viana', 'Guarapari',
    'Linhares', 'Colatina', 'São Mateus', 'Cachoeiro de Itapemirim',
    'Aracruz', 'Nova Venécia', 'Barra de São Francisco', 'Santa Teresa',
]

# Morfologia das instituições de saúde, para que o surrogate tenha a mesma "cara".
#
# Derivado do detector de INSTITUIÇÃO em selecionar_estratificado_por_phi(), que foi
# construído a partir do que aparece de fato no corpus MV. Manter os dois alinhados: um
# tipo que o detector reconhece mas o gerador não sabe produzir vira substituição com a
# forma errada.
PREFIXOS_INSTITUICAO = [
    'Hospital', 'Hospital Estadual', 'Hospital Municipal', 'UPA', 'UPINHA', 'UBS',
    'Pronto Atendimento', 'Pronto-Socorro', 'Clínica', 'Centro de Saúde',
    'Maternidade', 'CAPS', 'Hemocentro', 'Santa Casa', 'CACON',
]

# Siglas de unidades. No texto clínico a instituição aparece com frequência abreviada
# (HINSG, HESVV, HUCAM, HMRP, HMS, HRAS no detector do pipeline). Substituir uma sigla
# por nome por extenso muda a forma da menção e entrega a substituição.
SIGLAS_INSTITUICAO = [
    # 3 letras
    'HAB', 'HCM', 'HJP', 'HLN', 'HMV', 'HNC', 'HPR', 'HSB', 'HAC', 'HBV',
    'HCT', 'HLP', 'HSA', 'HTV', 'HVN', 'HSC',
    # 4 letras
    'HEAB', 'HECM', 'HEJP', 'HELN', 'HEMV', 'HENC', 'HEPR', 'HESB',
    'HMAC', 'HMBV', 'HMCT', 'HMLP', 'HRSA', 'HRTV', 'HGVN', 'HUSC',
    'HECT', 'HELP', 'HEVN', 'HESC', 'HMNC', 'HMPR', 'HMSB', 'HRAB',
    # 5 letras
    'HEABC', 'HECMV', 'HEJPN', 'HELNC', 'HMACT', 'HMBVN', 'HRSAB', 'HRTVN',
    'HUSCM', 'HGVNC', 'HEPRB', 'HESBC', 'HMCTV', 'HMLPN', 'HRABC', 'HEVNC',
    # 6 letras
    'HEABCD', 'HECMVN', 'HMACTV', 'HRSABC', 'HUSCMV', 'HGVNCT',
]

NOMES_INSTITUICAO = [
    'São Camilo', 'Santa Mônica', 'Bom Pastor', 'Nossa Senhora da Penha',
    'São Vicente', 'Santa Helena', 'Dom Bosco', 'São Judas', 'Santa Rita',
    'São Lucas', 'Bom Jesus', 'Santo Antônio', 'São Jorge', 'Santa Clara',
]

# DDDs do Espírito Santo
DDD_ES = ['27', '28']

DOMINIOS_EMAIL = [
    'exemplo.com.br', 'correio.com.br', 'mensagem.com', 'webmail.com.br',
]


# ---------------------------------------------------------------------------
# Utilidades de forma
# ---------------------------------------------------------------------------

def _sem_acento(texto):
    nfkd = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def espelhar_caixa(original, surrogate):
    """
    Aplica ao surrogate a mesma caixa do original.

    Texto clínico do MV é cheio de nome em CAIXA ALTA. Um surrogate em Título dentro de
    um texto onde todos os nomes estão em maiúsculas seria trivial de detectar, e o
    experimento perderia o sentido, porque o modelo estaria aprendendo a caixa, não a
    estrutura.
    """
    if original.isupper():
        return surrogate.upper()
    if original.islower():
        return surrogate.lower()
    return surrogate


def inferir_genero(prenome):
    """
    Infere o gênero do prenome para que o surrogate o preserve.

    O i2b2 2014 tratou isso explicitamente ("we paid attention to maintain gender
    information ... by selecting from lists generated from census data"). Trocar
    'ANA' por 'ANTÔNIO' quebra a concordância com o resto da sentença ("a paciente
    ANTÔNIO foi avaliada") e entrega ao modelo um sinal que o texto real não tem.

    Primeiro consulta os catálogos; se o nome não estiver neles, cai na terminação,
    que em português acerta a maioria dos casos. Devolve 'M', 'F' ou None.
    """
    if not prenome:
        return None
    base = _sem_acento(prenome).strip().lower()
    for nome in PRENOMES_F:
        if _sem_acento(nome).lower() == base:
            return 'F'
    for nome in PRENOMES_M:
        if _sem_acento(nome).lower() == base:
            return 'M'
    if len(base) < 3:
        return None
    # Terminações fortes primeiro; 'a' final é o indicador mais comum de feminino,
    # com exceções conhecidas (Luca, Josué...) que a heurística aceita errar.
    if base.endswith(('a', 'ia', 'na', 'ana', 'ela', 'ice')):
        return 'F'
    if base.endswith(('o', 'os', 'or', 'son', 'ton', 'ldo', 'rto')):
        return 'M'
    return None


def detectar_formato_nome(original):
    """
    Descreve a forma da menção para que o surrogate a reproduza.

    'J. SILVA' e 'JOÃO DA SILVA' são a mesma pessoa escrita de dois jeitos; o surrogate
    precisa manter a diferença, senão a variação de forma some do corpus.

    Retorna: {'n_partes', 'abreviado', 'com_particula', 'caixa_alta'}
    """
    partes = original.split()
    return {
        'n_partes':      len(partes),
        'abreviado':     any(re.fullmatch(r'[A-Za-zÀ-ÿ]\.?', p) for p in partes),
        'com_particula': any(_sem_acento(p).lower() in ('da', 'de', 'do', 'dos', 'das')
                             for p in partes),
        'caixa_alta':    original.isupper(),
    }


# ---------------------------------------------------------------------------
# Gerador
# ---------------------------------------------------------------------------

class GeradorSurrogates:
    """
    Gera surrogates verossímeis com consistência por identidade.

    Uso:
        g = GeradorSurrogates(seed=1)
        g.nome_pessoa('JOAO DA SILVA', chave='hash_do_paciente_A')
        g.nome_pessoa('JOAO DA SILVA', chave='hash_do_paciente_B')  # outro nome
        g.data('2025-05-12', chave='hash_do_paciente_A')            # shift consistente

    `chave` é a identidade da entidade. Para o paciente é o hash de `cd_paciente`
    (ver Fase 2). Para menções sem identificador estruturado, profissionais,
    acompanhantes, use a forma normalizada do texto dentro do escopo do documento,
    e declare essa limitação no trabalho.
    """

    MODO_VEROSSIMIL = 'verossimil'
    MODO_PLACEHOLDER = 'placeholder'   # braço C: PESSOA_1, PESSOA_2...
    MODO_CELEBRIDADE = 'celebridade'   # braço C: nomes muito conhecidos

    # Nomes deliberadamente reconhecíveis, para a contraprova. A hipótese do orientador
    # é que o modelo os detecte com facilidade e o F1 suba artificialmente.
    CELEBRIDADES = [
        'Machado de Assis', 'Carlos Drummond', 'Cecília Meireles', 'Jorge Amado',
        'Clarice Lispector', 'Graciliano Ramos', 'Rachel de Queiroz', 'Mário de Andrade',
    ]

    def __init__(self, seed, modo=MODO_VEROSSIMIL, catalogos=None):
        self.seed = seed
        self.modo = modo
        self._cache = {}          # (tipo, chave) -> surrogate, garante consistência
        self._contadores = {}     # para o modo placeholder
        self._shift_datas = {}    # chave -> deslocamento em dias
        self._nao_suportados = set()
        self._genero_indefinido = 0   # nomes em que o gênero não pôde ser inferido
        self._colisoes_evitadas = 0   # sorteios refeitos por sair igual ao original
        self._colisoes_nao_resolvidas = []  # casos em que nem assim deu para diferir
        self._sufixo_tentativa = ''   # varia o RNG entre as tentativas

        cat = catalogos or {}
        self.prenomes_m   = cat.get('prenomes_m', PRENOMES_M)
        self.prenomes_f   = cat.get('prenomes_f', PRENOMES_F)
        self.sobrenomes   = cat.get('sobrenomes', SOBRENOMES)
        self.logradouros  = cat.get('nomes_logradouro', NOMES_LOGRADOURO)
        self.municipios   = cat.get('municipios', MUNICIPIOS_ES)
        self.instituicoes = cat.get('nomes_instituicao', NOMES_INSTITUICAO)

    # -- infraestrutura -----------------------------------------------------

    def _rng(self, tipo, chave, discriminador=''):
        """
        RNG determinístico por (seed, tipo, chave).

        Deriva de um hash em vez de usar um Random global: assim a ordem em que as
        entidades aparecem no corpus não altera o resultado. Sem isso, inserir uma
        sentença no meio do corpus mudaria todos os surrogates seguintes, e as versões
        deixariam de ser reproduzíveis.
        """
        material = (f'{self.seed}|{tipo}|{chave}|{discriminador}'
                    f'{self._sufixo_tentativa}').encode('utf-8')
        semente = int(hashlib.sha256(material).hexdigest()[:16], 16)
        return random.Random(semente)

    # Tipos em que a chave de consistência é APENAS a identidade, ignorando a forma
    # escrita. 'JOÃO DA SILVA' e 'J. SILVA' são a mesma pessoa e precisam receber o
    # mesmo surrogate, incluir o texto na chave os separaria e quebraria a
    # consistência que o orientador pediu.
    _CHAVE_SO_IDENTIDADE = {'PESSOA'}

    # Quantas vezes tentar de novo quando o surrogate sai igual ao valor original.
    # Cinco tentativas bastam com qualquer catálogo de tamanho razoável: a chance de
    # cinco sorteios seguidos caírem no mesmo valor é desprezível.
    MAX_TENTATIVAS_DIFERENTE = 5

    def _memoizar(self, tipo, chave, gerar, original=None):
        """
        Memoiza o surrogate para garantir consistência.

        Para PESSOA, a chave é só a identidade. Para os demais tipos ela inclui o valor
        original, porque um mesmo paciente pode ter DOIS telefones, DOIS documentos ou
        DOIS endereços distintos, e cada um precisa do seu próprio surrogate. Sem isso,
        o segundo valor herdaria o surrogate do primeiro e o corpus passaria a afirmar
        que os dois eram o mesmo número.

        Há também uma verificação de segurança: se o sorteio devolver exatamente o valor
        original, ele é refeito. Um surrogate igual ao original não anonimiza nada, é PHI
        real permanecendo no corpus publicado, e com catálogo pequeno a coincidência
        acontece com frequência incômoda. A comparação ignora caixa e acento, porque
        "ANA" e "Ana" são o mesmo nome para quem lê.
        """
        if tipo in self._CHAVE_SO_IDENTIDADE or original is None:
            cache_key = (tipo, chave)
        else:
            cache_key = (tipo, chave, original)

        if cache_key in self._cache:
            return self._cache[cache_key]

        alvo = _sem_acento((original or '').strip()).lower()
        valor = gerar()
        tentativa = 0
        while (alvo and _sem_acento(str(valor).strip()).lower() == alvo
               and tentativa < self.MAX_TENTATIVAS_DIFERENTE):
            tentativa += 1
            self._colisoes_evitadas += 1
            # Muda a chave do sorteio para cair em outro ponto do catálogo
            self._sufixo_tentativa = f'#{tentativa}'
            valor = gerar()
            self._sufixo_tentativa = ''

        if alvo and _sem_acento(str(valor).strip()).lower() == alvo:
            # Catálogo pequeno demais para escapar. Não deixa passar em silêncio.
            self._colisoes_nao_resolvidas.append((tipo, original))

        self._cache[cache_key] = valor
        return valor

    def _proximo_placeholder(self, tipo, chave):
        def gerar():
            self._contadores[tipo] = self._contadores.get(tipo, 0) + 1
            return f'{tipo}_{self._contadores[tipo]}'
        return self._memoizar(tipo, chave, gerar)

    # -- PESSOA -------------------------------------------------------------

    def nome_pessoa(self, original, chave):
        """Nome fictício preservando forma (nº de partes, abreviação, partícula, caixa)."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('PESSOA', chave)

        def gerar():
            rng = self._rng('PESSOA', chave)
            if self.modo == self.MODO_CELEBRIDADE:
                return espelhar_caixa(original, rng.choice(self.CELEBRIDADES))

            forma = detectar_formato_nome(original)

            # Preserva o gênero do prenome original; se não for possível inferir,
            # sorteia, mas registra para que a taxa de indefinição seja auditável.
            genero = inferir_genero(original.split()[0] if original.split() else '')
            if genero == 'F':
                prenomes = self.prenomes_f
            elif genero == 'M':
                prenomes = self.prenomes_m
            else:
                self._genero_indefinido += 1
                prenomes = self.prenomes_m if rng.random() < 0.5 else self.prenomes_f

            partes = [rng.choice(prenomes)]

            # Nome de uma parte só continua com uma parte só. 'ANA' não pode virar
            # 'ANTÔNIO ALVES': o número de partes é traço da menção e o corpus perde
            # variação de forma se todos os nomes forem normalizados para dois termos.
            n_sobrenomes = max(0, forma['n_partes'] - 1)
            usa_particula = forma['com_particula'] and n_sobrenomes >= 2
            if usa_particula:
                n_sobrenomes -= 1  # a partícula ocupa uma das posições

            # Quando o nome pede partícula, sorteia o PRIMEIRO sobrenome apenas entre os
            # que têm partícula conhecida. Sem esta restrição, cair num sobrenome fora do
            # mapa (Moreira, Marques, Ribeiro...) fazia a partícula não ser inserida e o
            # nome sair com uma parte a menos que o original, ocorria em ~15% dos casos.
            candidatos = list(self.sobrenomes)
            escolhidos = []
            if n_sobrenomes:
                if usa_particula:
                    com_particula = [s for s in candidatos if s in PARTICULA_POR_SOBRENOME]
                    if com_particula:
                        primeiro = rng.choice(com_particula)
                        escolhidos.append(primeiro)
                        candidatos.remove(primeiro)
                        n_restantes = n_sobrenomes - 1
                    else:
                        usa_particula = False
                        n_restantes = n_sobrenomes
                else:
                    n_restantes = n_sobrenomes
                if n_restantes > 0:
                    escolhidos.extend(
                        rng.sample(candidatos, min(n_restantes, len(candidatos)))
                    )

            # A partícula concorda com o PRIMEIRO sobrenome escolhido, não com o prenome
            if usa_particula and escolhidos:
                partes.append(PARTICULA_POR_SOBRENOME[escolhidos[0]])
            partes.extend(escolhidos)

            nome = ' '.join(partes)
            if forma['abreviado'] and len(partes) > 1:
                # 'J. SILVA' → inicial + último sobrenome
                nome = f'{partes[0][0]}. {partes[-1]}'
            return espelhar_caixa(original, nome)

        # O original vai junto apenas para a checagem de colisão. A chave de cache
        # continua sendo só a identidade, porque PESSOA está em _CHAVE_SO_IDENTIDADE.
        return self._memoizar('PESSOA', chave, gerar, original)

    # -- ENDEREÇO -----------------------------------------------------------

    def endereco(self, original, chave):
        """Logradouro fictício com o mesmo tipo (rua→rua, avenida→avenida)."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('ENDERECO', chave)

        def gerar():
            rng = self._rng('ENDERECO', chave, original)
            tipo_original = None
            sem_acento_upper = _sem_acento(original).upper()
            for tipo in TIPOS_LOGRADOURO:
                if _sem_acento(tipo).upper() in sem_acento_upper:
                    tipo_original = tipo
                    break
            tipo_final = tipo_original or rng.choice(TIPOS_LOGRADOURO)
            endereco = f'{tipo_final} {rng.choice(self.logradouros)}'

            # O número segue o original: se havia número, o surrogate tem número; se não
            # havia, não inventa. Sortear por conta própria fazia 'RUA DAS PALMEIRAS'
            # ganhar um número inexistente e 'ALAMEDA DOS PINHEIROS, 45' perder o seu,             # em ambos os casos alterando a informação que o modelo vê.
            numero_original = re.search(r',\s*(\d+)', original or '')
            if numero_original:
                # Mantém a ordem de grandeza do número original (dezena, centena, milhar)
                casas = len(numero_original.group(1))
                minimo = 10 ** (casas - 1) if casas > 1 else 1
                maximo = (10 ** casas) - 1
                endereco += f', {rng.randint(minimo, maximo)}'

            return espelhar_caixa(original, endereco)

        return self._memoizar('ENDERECO', chave, gerar, original)

    def municipio(self, original, chave):
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('MUNICIPIO', chave)
        return self._memoizar('MUNICIPIO', chave, lambda: espelhar_caixa(
            original, self._rng('MUNICIPIO', chave).choice(self.municipios)), original)

    # -- INSTITUIÇÃO --------------------------------------------------------

    def instituicao(self, original, chave):
        """Instituição fictícia preservando a morfologia (Hospital X, UPA Y, UBS Z)."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('INSTITUICAO', chave)

        def gerar():
            rng = self._rng('INSTITUICAO', chave, original)
            texto = (original or '').strip()

            # Sigla continua sigla. 'HEUE' virando 'HOSPITAL SÃO LUCAS' muda a forma da
            # menção, o modelo veria um token onde antes havia quatro, e a substituição
            # ficaria evidente para quem lesse o corpus.
            if re.fullmatch(r'[A-ZÀ-Ý]{3,6}', texto):
                sigla = rng.choice(SIGLAS_INSTITUICAO)
                # Preserva o comprimento da sigla original quando possível
                candidatas = [s for s in SIGLAS_INSTITUICAO if len(s) == len(texto)]
                if candidatas:
                    sigla = rng.choice(candidatas)
                return sigla

            sem_acento_upper = _sem_acento(texto).upper()
            # Prefixo mais longo primeiro: 'Hospital Estadual' antes de 'Hospital',
            # senão o mais curto casa primeiro e a especificidade se perde.
            prefixo = None
            for candidato in sorted(PREFIXOS_INSTITUICAO, key=len, reverse=True):
                if _sem_acento(candidato).upper() in sem_acento_upper:
                    prefixo = candidato
                    break
            prefixo = prefixo or rng.choice(PREFIXOS_INSTITUICAO)
            return espelhar_caixa(original, f'{prefixo} {rng.choice(self.instituicoes)}')

        return self._memoizar('INSTITUICAO', chave, gerar, original)

    # -- DATA / HORA --------------------------------------------------------

    def deslocamento_dias(self, chave):
        """
        Deslocamento fixo por paciente, entre -365 e +365 dias.

        Sorteado uma vez e aplicado a TODAS as datas daquele paciente. É isso que
        preserva os intervalos: se o original tem alta 7 dias após a internação, o
        surrogate também tem. Sortear cada data isoladamente destruiria a coerência
        clínica ("retorno em 30 dias" deixaria de fazer sentido) e mataria o vínculo
        longitudinal que o hash do paciente existe para preservar.
        """
        if chave not in self._shift_datas:
            self._shift_datas[chave] = self._rng('SHIFT', chave).randint(-365, 365)
        return self._shift_datas[chave]

    def data(self, original_iso, chave):
        """
        Desloca uma data ISO (YYYY-MM-DD) pelo shift do paciente.

        Devolve o original se não for uma data ISO válida, datas incompletas são
        exceção documentada do pipeline e não devem ser inventadas.
        """
        from datetime import date, timedelta

        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('DATA', chave)

        m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', (original_iso or '').strip())
        if not m:
            return original_iso
        try:
            base = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return original_iso
        return (base + timedelta(days=self.deslocamento_dias(chave))).isoformat()

    def hora(self, original, chave):
        """
        Hora é preservada por padrão.

        Horário de atendimento raramente identifica alguém sozinho e carrega informação
        clínica real (turno, plantão, intervalo entre medicações). Deslocá-lo degradaria
        a utilidade sem ganho de privacidade proporcional. Decisão a revisar com o
        orientador, está registrada como pendência 7 na especificação.
        """
        return original

    # -- Identificadores estruturados ---------------------------------------

    def telefone(self, original, chave):
        """Telefone fictício com DDD do ES, preservando o formato do original."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('TELEFONE', chave)

        def gerar():
            rng = self._rng('TELEFONE', chave, original)
            texto = original or ''
            digitos = re.sub(r'\D', '', texto)
            n = len(digitos)

            # Reproduz a estrutura do original: celular (9 dígitos, começa com 9) ou
            # fixo (8 dígitos, começa com 3 no ES), com ou sem DDD. Trocar um fixo de
            # 8 dígitos por um número de 10 mudaria o formato que o modelo aprende a
            # reconhecer, e a comparação com o corpus real deixaria de ser justa.
            tem_ddd = n >= 10
            celular = (n in (9, 11)) or texto.strip().startswith(('9', '(')) and n != 8
            if celular:
                numero = f'9{rng.randint(1000, 9999)}{rng.randint(1000, 9999)}'
            else:
                numero = f'3{rng.randint(100, 999)}{rng.randint(1000, 9999)}'

            ddd = rng.choice(DDD_ES) if tem_ddd or '(' in texto else ''
            corpo_esq = numero[:-4]
            corpo_dir = numero[-4:]

            if '(' in texto:
                return f'({ddd}) {corpo_esq}-{corpo_dir}'
            if '-' in texto:
                return f'{ddd} {corpo_esq}-{corpo_dir}'.strip()
            return f'{ddd}{numero}'

        return self._memoizar('TELEFONE', chave, gerar, original)

    def cpf(self, original, chave):
        """CPF fictício com dígito verificador válido e o formato do original."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('CPF', chave)

        def gerar():
            rng = self._rng('CPF', chave, original)
            base = [rng.randint(0, 9) for _ in range(9)]
            for _ in range(2):
                peso = len(base) + 1
                soma = sum(d * (peso - i) for i, d in enumerate(base))
                digito = (soma * 10) % 11
                base.append(0 if digito == 10 else digito)
            numeros = ''.join(map(str, base))
            if '.' in (original or '') or '-' in (original or ''):
                return f'{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}'
            return numeros

        return self._memoizar('CPF', chave, gerar, original)

    def cep(self, original, chave):
        """CEP fictício na faixa do ES (29000-000 a 29999-999)."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('CEP', chave)

        def gerar():
            rng = self._rng('CEP', chave, original)
            prefixo = f'29{rng.randint(0, 999):03d}'
            sufixo = f'{rng.randint(0, 999):03d}'
            return f'{prefixo}-{sufixo}' if '-' in (original or '') else f'{prefixo}{sufixo}'

        return self._memoizar('CEP', chave, gerar, original)

    def email(self, original, chave):
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('EMAIL', chave)

        def gerar():
            rng = self._rng('EMAIL', chave, original)
            prenome = rng.choice(self.prenomes_m + self.prenomes_f)
            sobrenome = rng.choice(self.sobrenomes)
            usuario = _sem_acento(f'{prenome}.{sobrenome}').lower()
            return f'{usuario}@{rng.choice(DOMINIOS_EMAIL)}'

        return self._memoizar('EMAIL', chave, gerar, original)

    def documento(self, original, chave):
        """Documento genérico (RG, CNS, CNH) com o mesmo comprimento e formato."""
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('DOCUMENTO', chave)

        def gerar():
            rng = self._rng('DOCUMENTO', chave, original)
            digitos = re.sub(r'\D', '', original or '')
            n = len(digitos) or 9
            novos = ''.join(str(rng.randint(0, 9)) for _ in range(n))
            # Reconstrói preservando a pontuação do original
            resultado, i = [], 0
            for c in (original or ''):
                if c.isdigit():
                    resultado.append(novos[i] if i < len(novos) else '0')
                    i += 1
                else:
                    resultado.append(c)
            return ''.join(resultado) if resultado else novos

        return self._memoizar('DOCUMENTO', chave, gerar, original)

    # -- Despacho -----------------------------------------------------------

    _DESPACHO = {
        'PESSOA':      'nome_pessoa',
        'ENDERECO':    'endereco',
        'ENDEREÇO':    'endereco',
        'MUNICIPIO':   'municipio',
        'INSTITUICAO': 'instituicao',
        'INSTITUIÇÃO': 'instituicao',
        'DATA':        'data',
        'HORA':        'hora',
        'TELEFONE':    'telefone',
        'CONTATO':     'telefone',
        'CPF':         'cpf',
        'CEP':         'cep',
        'EMAIL':       'email',
        'DOCUMENTO':   'documento',
    }

    def gerar(self, tipo, original, chave):
        """
        Ponto de entrada único: devolve o surrogate para (tipo, valor original, chave).

        Tipo desconhecido devolve o valor original inalterado e NÃO falha em silêncio de
        forma perigosa, mas o chamador deve verificar `tipos_nao_suportados()` depois de
        processar o corpus, porque um tipo não tratado é PHI que permaneceu no texto.
        """
        metodo = self._DESPACHO.get((tipo or '').upper())
        if metodo is None:
            self._nao_suportados.add(tipo)
            return original
        return getattr(self, metodo)(original, chave)

    def tipos_nao_suportados(self):
        """Tipos que passaram por gerar() sem tratamento. Deve estar vazio."""
        return sorted(self._nao_suportados)

    def estatisticas(self):
        """Números para auditar a qualidade da geração depois de processar o corpus."""
        return {
            'entidades_distintas':  len(self._cache),
            'pacientes_com_shift':  len(self._shift_datas),
            'genero_indefinido':    self._genero_indefinido,
            'tipos_nao_suportados': self.tipos_nao_suportados(),
            'colisoes_evitadas':    self._colisoes_evitadas,
            'colisoes_nao_resolvidas': len(self._colisoes_nao_resolvidas),
        }
