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
    'Adriano', 'Alexandre', 'Alex', 'Anderson', 'André', 'Arthur', 'Augusto',
    'Benedito', 'Bernardo', 'Caio', 'Celso', 'César', 'Cristiano', 'Daniel', 'Danilo',
    'Davi', 'Denis', 'Douglas', 'Edson', 'Elias', 'Enzo', 'Evandro', 'Everton',
    'Felipe', 'Flávio', 'Gabriel', 'Geraldo', 'Germano', 'Gilson', 'Guilherme',
    'Heitor', 'Hugo', 'Igor', 'Isaac', 'Jair', 'Jefferson', 'Jonas', 'Josué', 'Juliano',
    'Júlio', 'Kleber', 'Lauro', 'Leandro', 'Lucas', 'Marcos', 'Mário', 'Mateus',
    'Matheus', 'Miguel', 'Moisés', 'Murilo', 'Natanael', 'Nicolas', 'Orlando',
    'Patrick', 'Renan', 'Renato', 'Roberto', 'Robson', 'Rogério', 'Ronaldo', 'Rubens',
    'Samuel', 'Sandro', 'Saulo', 'Silvio', 'Tiago', 'Ulisses', 'Valter', 'Vicente',
    'Victor', 'Vitor', 'Wallace', 'Wellington', 'Wesley', 'William', 'Yuri',
    'Adalberto', 'Ademir', 'Agnaldo', 'Altair', 'Amauri', 'Aparecido', 'Armando',
    'Arnaldo', 'Benjamim', 'Clóvis', 'Dário', 'Domingos', 'Edgar', 'Edmilson', 'Elton',
    'Ernesto', 'Eugênio', 'Ezequiel', 'Genivaldo', 'Getúlio', 'Horácio', 'Ismael',
    'Jaime', 'Jeremias', 'Lázaro', 'Lourival', 'Manuel', 'Messias', 'Napoleão', 'Olavo',
    'Pascoal', 'Reginaldo', 'Romildo', 'Severino', 'Tadeu', 'Tarcísio', 'Waldemar',
    'Zacarias',
]

PRENOMES_F = [
    'Adriana', 'Beatriz', 'Cristina', 'Daniela', 'Eliane', 'Fernanda', 'Gabriela',
    'Helena', 'Isabel', 'Juliana', 'Karina', 'Luciana', 'Mariana', 'Natália',
    'Patrícia', 'Renata', 'Simone', 'Tatiana', 'Vanessa', 'Amanda', 'Bianca',
    'Camila', 'Débora', 'Elaine', 'Flávia', 'Giovana', 'Ingrid', 'Joana',
    'Larissa', 'Márcia', 'Nádia', 'Priscila', 'Rosana', 'Silvana', 'Vera',
    'Maria', 'Ana', 'Francisca', 'Antônia', 'Terezinha', 'Lúcia', 'Rosa',
    'Alessandra', 'Alice', 'Aline', 'Andréa', 'Andressa', 'Ângela', 'Aparecida',
    'Bárbara', 'Bruna', 'Carla', 'Carolina', 'Cássia', 'Cecília', 'Célia', 'Clara',
    'Cláudia', 'Conceição', 'Daiane', 'Denise', 'Diana', 'Edna', 'Eduarda', 'Elisa',
    'Elisângela', 'Elizabete', 'Érica', 'Ester', 'Eva', 'Fabiana', 'Fátima', 'Glória',
    'Graça', 'Heloísa', 'Iara', 'Ivone', 'Jaqueline', 'Jéssica', 'Joice', 'Josefa',
    'Júlia', 'Jussara', 'Kátia', 'Laís', 'Laura', 'Letícia', 'Lídia', 'Lívia', 'Lorena',
    'Luana', 'Luíza', 'Madalena', 'Marcela', 'Margarida', 'Marina', 'Marta', 'Michele',
    'Miriam', 'Mônica', 'Neusa', 'Olga', 'Paula', 'Raquel', 'Rebeca', 'Regina', 'Rita',
    'Roberta', 'Rosângela', 'Rute', 'Sabrina', 'Sandra', 'Sara', 'Sílvia', 'Sônia',
    'Sueli', 'Tânia', 'Teresa', 'Thaís', 'Valéria', 'Vitória', 'Viviane', 'Yasmin',
    'Zélia', 'Adelaide', 'Alzira', 'Anita', 'Aurora', 'Benedita', 'Carmem', 'Celina',
    'Dalva', 'Dirce', 'Dulce', 'Edite', 'Elza', 'Eunice', 'Geralda', 'Hilda', 'Iolanda',
    'Irene', 'Jandira', 'Judite', 'Leonor', 'Lourdes', 'Luzia', 'Marlene', 'Nair',
    'Odete', 'Olinda', 'Ruth', 'Sebastiana', 'Zilda',
]

SOBRENOMES = [
    'Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves',
    'Pereira', 'Lima', 'Gomes', 'Ribeiro', 'Carvalho', 'Almeida', 'Lopes',
    'Soares', 'Fernandes', 'Vieira', 'Barbosa', 'Rocha', 'Dias', 'Nascimento',
    'Andrade', 'Moreira', 'Nunes', 'Marques', 'Machado', 'Mendes', 'Freitas',
    'Cardoso', 'Ramos', 'Gonçalves', 'Santana', 'Teixeira', 'Araújo', 'Cunha',
    'Costa', 'Reis', 'Anjos', 'Carmo', 'Amaral', 'Prado', 'Vale', 'Moraes', 'Paula',
    'Assis', 'Luz', 'Azevedo', 'Barros', 'Batista', 'Borges', 'Brandão', 'Braga',
    'Brito', 'Campos', 'Castro', 'Cavalcanti', 'Coelho', 'Correia', 'Cruz', 'Duarte',
    'Farias', 'Figueiredo', 'Fonseca', 'Franco', 'Garcia', 'Guimarães', 'Leite',
    'Macedo', 'Magalhães', 'Martins', 'Matos', 'Medeiros', 'Melo', 'Miranda',
    'Monteiro', 'Moura', 'Neves', 'Pacheco', 'Peixoto', 'Pinheiro', 'Pinto', 'Pires',
    'Queiroz', 'Rezende', 'Sales', 'Sampaio', 'Siqueira', 'Tavares', 'Toledo',
    'Vasconcelos', 'Xavier', 'Aguiar', 'Amorim', 'Antunes', 'Bastos', 'Bezerra',
    'Bittencourt', 'Bueno', 'Caldeira', 'Camargo', 'Chaves', 'Cordeiro', 'Couto',
    'Dantas', 'Domingues', 'Esteves', 'Falcão', 'Gouveia', 'Lacerda', 'Leal', 'Lemos',
    'Maciel', 'Maia', 'Mota', 'Muniz', 'Nogueira', 'Paiva', 'Paixão', 'Passos',
    'Quintela', 'Rangel', 'Rosa', 'Seixas', 'Simões', 'Trindade', 'Valente', 'Veloso',
    'Viana', 'Zanetti', 'Bonfim', 'Favero', 'Gasparini', 'Loureiro', 'Pimentel',
    'Scarpati', 'Zanotti', 'Fraga', 'Lyrio', 'Piovesan', 'Dalmaso',
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

# Palavras para compor nomes de lugar: bairros, distritos e municípios capixabas. O
# gerador de endereço troca cada palavra identificadora do original por uma destas,
# mantendo a estrutura da menção.
PALAVRAS_DE_LUGAR = [
    'Camburi', 'Jucutuquara', 'Maruípe', 'Goiabeiras', 'Itararé', 'Bonfim',
    'Consolação', 'Gurigica', 'Itaparica', 'Itapuã', 'Aribiri', 'Cobilândia', 'Glória',
    'Ibes', 'Jaburuna', 'Alvorada', 'Soteco', 'Jabaeté', 'Carapina', 'Laranjeiras',
    'Jacaraípe', 'Manguinhos', 'Barcelona', 'Planalto', 'Serrano', 'Tubarão',
    'Valparaíso', 'Campinho', 'Itacibá', 'Flexal', 'Santana', 'Cruzeiro', 'Tucum',
    'Bandeirantes', 'Itanguá', 'Canaã', 'Universal', 'Areinha', 'Caxias', 'Esperança',
    'Horizonte', 'Brasil', 'América', 'Primavera', 'Aurora', 'Colina', 'Mata', 'Praia',
    'Barra', 'Pontal', 'Ilha', 'Morro', 'Lagoa', 'Cachoeira', 'Pedra', 'Monte', 'Campo',
    'Ribeirão', 'Linhares', 'Colatina', 'Aracruz', 'Guarapari', 'Viana', 'Cariacica',
    'Itapemirim', 'Marataízes', 'Anchieta', 'Piúma', 'Iconha', 'Alegre', 'Castelo',
    'Muqui', 'Mimoso', 'Guaçuí', 'Iúna', 'Ibatiba', 'Venécia', 'Pinheiros', 'Montanha',
    'Mucurici', 'Ecoporanga', 'Pancas', 'Guandu', 'Itaguaçu', 'Itarana', 'Fundão',
    'Ibiraçu', 'Sooretama', 'Marilândia', 'Bananal', 'Leopoldina', 'Apiacá', 'Irupi',
    'Mantenópolis', 'Brejetuba', 'Jardim', 'Vila', 'Parque', 'Morada', 'Bela', 'Vista',
    'Luzia', 'Teresa', 'Inês', 'Bárbara', 'Helena', 'Antônio', 'Pedro', 'José',
    'Francisco', 'Sebastião', 'Mateus', 'Gabriel', 'Roque', 'Domingos', 'Jerônimo',
    'Marechal', 'Floriano', 'Afonso', 'Alfredo', 'Atílio', 'Kennedy', 'Lindenberg',
    'Pavão', 'Valério', 'Neiva', 'Palmeiras', 'Acácias', 'Ipês', 'Cedro', 'Jacarandá',
    'Paraíso', 'Independência', 'Guanabara', 'Tabuazeiro', 'Andorinhas', 'Resistência',
    'Romão', 'Forte', 'Mário', 'Cypreste', 'Redenção', 'Joana', 'Estrelinha',
    'Inhanguetá', 'Universitário', 'Comdusa', 'Jabour', 'Solon', 'Borges', 'Maria',
    'Ortiz', 'Segurança', 'Enseada', 'Suá', 'Bento', 'Ferreira', 'Fradinhos', 'Piedade',
    'Moscoso', 'Fonte', 'Grande', 'Caratoíra', 'Condusa', 'Vitória', 'Itaquari',
    'Jardineiras', 'Boa', 'Sorte', 'Rosa', 'Penha', 'Ataíde', 'Divino', 'Garoto',
    'Paul', 'Zumbi', 'Cocal', 'Vasco', 'Coutinho', 'Aviso', 'Interlagos', 'Movelar',
    'Shell', 'Conceição', 'Bebedouro', 'Canivete', 'Rio', 'Quartel', 'Regência',
    'Povoação', 'Desengano', 'Farias', 'Juparanã',
]

# Palavras que dão a estrutura do endereço e não identificam ninguém. Ficam como estão,
# porque são elas que o modelo usa para reconhecer que ali há um endereço.
ESTRUTURA_ENDERECO = {
    'rua', 'r', 'avenida', 'av', 'travessa', 'trav', 'tv', 'alameda', 'al', 'praca',
    'pc', 'rodovia', 'rod', 'estrada', 'estr', 'beco', 'ladeira', 'largo', 'viela',
    'bairro', 'b', 'distrito', 'municipio', 'cidade', 'comunidade', 'assentamento',
    'loteamento', 'residencial', 'conjunto', 'condominio', 'edificio', 'ed', 'bloco',
    'bl', 'apartamento', 'ap', 'apt', 'apto', 'casa', 'cs', 'fundos', 'lote', 'lt',
    'quadra', 'qd', 'km', 'br', 'es', 'numero', 'n', 'no', 'sn', 'zona', 'rural',
    'urbana', 'interior', 'centro', 'sitio', 'fazenda', 'corrego', 'proximo', 'perto',
    'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'na', 'ao', 'a', 'o',
    # Qualificadores muito comuns em nome de lugar. Sozinhos não identificam: o que
    # identifica 'São Pedro' é o 'Pedro'. Mantê-los faz o surrogate soar como lugar.
    'sao', 'santa', 'santo', 'nova', 'novo', 'vila', 'jardim', 'parque', 'porto',
    'boa', 'bela', 'alto', 'baixo', 'grande', 'morada', 'vista',
}

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


MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
         'setembro', 'outubro', 'novembro', 'dezembro']

_SEPARADOR_DATA = r'(\s*[/\\.\-]\s*)'


def _mes_por_nome(texto):
    """Devolve (numero_do_mes, abreviado) para um nome de mês, ou (None, False)."""
    alvo = _sem_acento(texto).lower().rstrip('.')
    for numero, nome in enumerate(MESES, 1):
        sem_acento = _sem_acento(nome)
        if alvo == sem_acento:
            return numero, False
        if len(alvo) == 3 and alvo == sem_acento[:3]:
            return numero, True
    return None, False


def _numero_no_formato(valor, modelo):
    """Escreve o número com zero à esquerda só se o original tinha dois dígitos."""
    return f'{valor:02d}' if len(modelo) >= 2 else str(valor)


def _ano_no_formato(ano, modelo):
    """Escreve o ano com dois ou quatro dígitos, conforme o original."""
    return f'{ano % 100:02d}' if len(modelo) == 2 else str(ano)


def _ano_completo(texto):
    """Ano de dois dígitos é lido como 20xx. O corpus é de registros recentes."""
    ano = int(texto)
    return 2000 + ano if len(texto) == 2 else ano


def deslocar_data_livre(original, dias):
    """
    Desloca uma data escrita fora do padrão ISO e devolve no mesmo formato.

    Atende aos formatos encontrados nas datas anotadas à mão no corpus:

        dia / mês             '12 / 03'          a maioria absoluta dos casos
        mês / ano             '03 / 2024', '03 / 24'
        dia / mês / ano       '12 / 03 / 2024'
        mês por extenso e ano 'março de 2024', 'mar / 2024', 'março 2024'
        ano sozinho           '2019'

    A data incompleta é completada só para fazer a conta, e o que foi completado não
    aparece no resultado: quem não tinha ano continua sem ano. Sem dia, a conta parte do
    dia 15; sem mês, de 1º de julho; sem ano, de um ano de referência.

    O separador, os espaços e os zeros à esquerda do original são mantidos, para que o
    surrogate tenha a mesma forma que o modelo vê no corpus real.

    Devolve None quando não reconhece o formato. Não tenta adivinhar: uma expressão
    como 'há três dias' é relativa, e deslocá-la seria inventar informação.
    """
    from datetime import date, timedelta

    texto = (original or '').strip()
    delta = timedelta(days=dias)

    def montar(ano, mes, dia):
        try:
            return date(ano, mes, dia) + delta
        except ValueError:
            return None

    # dia / mês / ano
    m = re.fullmatch(r'(\d{1,2})' + _SEPARADOR_DATA + r'(\d{1,2})' + _SEPARADOR_DATA
                     + r'(\d{4}|\d{2})', texto)
    if m:
        dia, sep1, mes, sep2, ano = m.groups()
        nova = montar(_ano_completo(ano), int(mes), int(dia))
        if nova is None:
            return None
        return (_numero_no_formato(nova.day, dia) + sep1
                + _numero_no_formato(nova.month, mes) + sep2
                + _ano_no_formato(nova.year, ano))

    # mês / ano com quatro dígitos
    m = re.fullmatch(r'(\d{1,2})' + _SEPARADOR_DATA + r'(\d{4})', texto)
    if m:
        mes, sep, ano = m.groups()
        nova = montar(int(ano), int(mes), 15)
        if nova is None:
            return None
        return _numero_no_formato(nova.month, mes) + sep + str(nova.year)

    # dois números curtos: dia / mês, ou mês / ano de dois dígitos
    m = re.fullmatch(r'(\d{1,2})' + _SEPARADOR_DATA + r'(\d{1,2})', texto)
    if m:
        primeiro, sep, segundo = m.groups()
        a, b = int(primeiro), int(segundo)
        if 1 <= b <= 12 and 1 <= a <= 31:
            # Ano de referência bissexto, para que 29 / 02 seja uma data válida.
            nova = montar(2024, b, a)
            if nova is None:
                return None
            return (_numero_no_formato(nova.day, primeiro) + sep
                    + _numero_no_formato(nova.month, segundo))
        if 1 <= a <= 12 and b > 12 and len(segundo) == 2:
            nova = montar(2000 + b, a, 15)
            if nova is None:
                return None
            return (_numero_no_formato(nova.month, primeiro) + sep
                    + f'{nova.year % 100:02d}')
        return None

    # mês por extenso seguido de ano
    m = re.fullmatch(r'([^\W\d_]+\.?)(\s+de\s+|\s*/\s*|\s+)(\d{4}|\d{2})', texto,
                     flags=re.IGNORECASE)
    if m:
        nome, sep, ano = m.groups()
        mes, abreviado = _mes_por_nome(nome)
        if mes is None:
            return None
        nova = montar(_ano_completo(ano), mes, 15)
        if nova is None:
            return None
        novo_nome = MESES[nova.month - 1]
        if abreviado:
            novo_nome = novo_nome[:3] + ('.' if nome.endswith('.') else '')
        if nome[:1].isupper() and not nome.isupper():
            novo_nome = novo_nome.capitalize()       # 'Março' continua com inicial maiúscula
        else:
            novo_nome = espelhar_caixa(nome, novo_nome)
        return novo_nome + sep + _ano_no_formato(nova.year, ano)

    # ano sozinho
    m = re.fullmatch(r'(19|20)\d{2}', texto)
    if m:
        nova = montar(int(texto), 7, 1)
        return str(nova.year) if nova else None

    return None


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


# Tratamentos que aparecem dentro da menção anotada como PESSOA ('SR JOAO', 'DRA ANA').
# Não identificam ninguém e são a pista mais forte de que ali vem um nome.
TITULOS_PESSOA = {
    'sr', 'sra', 'srta', 'dr', 'dra', 'd', 'dona', 'seu', 'prof', 'profa', 'enf', 'enfa',
    'tec', 'doutor', 'doutora', 'senhor', 'senhora',
}


def separar_titulo(original):
    """
    Separa o tratamento do começo da menção. Devolve (titulo, resto).

    'SR . JOAO DA SILVA' vira ('SR .', 'JOAO DA SILVA'). O ponto solto logo depois do
    tratamento acompanha o tratamento, porque a tokenização do corpus o separa.
    """
    partes = (original or '').split()
    corte = 0
    while corte < len(partes):
        palavra = _sem_acento(partes[corte]).lower().rstrip('.')
        eh_titulo = palavra in TITULOS_PESSOA and (corte == 0 or partes[corte - 1] == '.'
                                                   or corte == 1 and False)
        eh_ponto = partes[corte] == '.' and corte > 0
        if corte == 0 and palavra in TITULOS_PESSOA or eh_ponto and corte == 1:
            corte += 1
        else:
            break
    return ' '.join(partes[:corte]), ' '.join(partes[corte:])


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
    MODO_ORIGINAL = 'original'         # braço A: devolve o valor real, sem trocar nada

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
        self._datas_nao_deslocadas = 0  # datas em formato que o gerador não reconhece
        self._palavras_usadas = {}      # por paciente: palavras de nome já sorteadas
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

        # O tratamento fica, e só o nome é trocado. No corpus, 14% das menções de pessoa
        # começam com SR, SRA, DR ou DRA dentro do trecho anotado. Trocar o tratamento
        # por um prenome, como acontecia, apagava do corpus com surrogates todas as
        # menções nesse formato, e o modelo deixava de aprendê-lo.
        titulo, resto = separar_titulo(original)
        if titulo:
            if not resto:
                return original      # só o tratamento: não há nome para trocar
            return f'{titulo} {self.nome_pessoa(resto, chave)}'

        if self.modo == self.MODO_VEROSSIMIL:
            return self._nome_palavra_por_palavra(original, chave)

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

    _PARTICULAS_NOME = ('de', 'da', 'do', 'dos', 'das', 'e')

    def _nome_palavra_por_palavra(self, original, chave):
        """
        Troca o nome palavra por palavra, com um dicionário próprio de cada paciente.

        Dentro dos registros de um paciente, cada palavra de nome real tem sempre a mesma
        palavra fictícia. Disso saem as duas propriedades que o orientador pediu:

          - a mesma pessoa recebe o mesmo surrogate, em qualquer forma de escrita.
            'JOAO DA SILVA', 'JOAO' e 'J. SILVA' viram 'CARLOS DA ROCHA', 'CARLOS' e
            'C. ROCHA';
          - pessoas diferentes recebem surrogates diferentes, inclusive dentro do mesmo
            paciente. O médico, o paciente e o acompanhante não viram a mesma pessoa.

        A versão anterior guardava um único nome por paciente. Com isso, todas as
        pessoas citadas nos registros de um paciente recebiam o mesmo nome, e uma menção
        curta saía com o tamanho da primeira menção vista. Quase metade das menções do
        corpus estava nessa situação.

        O dicionário é por paciente, então o mesmo nome real em outro paciente recebe
        outra palavra: homônimos continuam distintos.

        Partículas, pontuação e iniciais mantêm o lugar. A primeira palavra vira prenome,
        do mesmo gênero quando dá para inferir, e as demais viram sobrenomes.
        """
        usadas = self._palavras_usadas.setdefault(chave, set())
        novas = []
        ja_tem_nome = False
        particula = None

        for palavra in (original or '').split():
            base = _sem_acento(palavra).upper().strip('.,;:()-')
            if not base or not any(c.isalpha() for c in base):
                novas.append(palavra)                      # pontuação ou número
                continue
            if base.lower() in self._PARTICULAS_NOME:
                novas.append(palavra)
                particula = base.lower()
                continue

            cache_key = ('PESSOA', chave, base)
            if cache_key not in self._cache:
                rng = self._rng('PESSOA', chave, base)
                if len(base) == 1:
                    # Inicial: usa a de uma palavra já trocada que comece com ela, para
                    # 'J. SILVA' acompanhar 'JOAO DA SILVA'. Sem isso, sorteia.
                    conhecidas = [v for (t, c, o), v in self._cache.items()
                                  if t == 'PESSOA' and c == chave and len(o) > 1
                                  and o.startswith(base)]
                    escolhida = (conhecidas[0][0] if conhecidas
                                 else rng.choice('ABCDEFGJLMNPRSTV'))
                else:
                    if not ja_tem_nome:
                        genero = inferir_genero(palavra)
                        if genero is None:
                            self._genero_indefinido += 1
                            genero = 'M' if rng.random() < 0.5 else 'F'
                        catalogo = self.prenomes_f if genero == 'F' else self.prenomes_m
                    else:
                        catalogo = self.sobrenomes
                    livres = [n for n in catalogo
                              if _sem_acento(n).upper() != base
                              and _sem_acento(n).upper() not in usadas]
                    # Depois de partícula, prefere sobrenome que combine com ela, para
                    # não sair 'da Nascimento'.
                    combinam = [n for n in livres
                                if PARTICULA_POR_SOBRENOME.get(n) == particula]
                    if particula and combinam:
                        livres = combinam
                    escolhida = rng.choice(livres or list(catalogo))
                    usadas.add(_sem_acento(escolhida).upper())
                self._cache[cache_key] = escolhida

            escolhida = self._cache[cache_key]
            if palavra.isupper():
                escolhida = escolhida.upper()
            elif palavra.islower():
                escolhida = escolhida.lower()
            sufixo = palavra[len(palavra.rstrip('.,;:')):]   # ponto colado na palavra
            novas.append(escolhida + sufixo)
            ja_tem_nome = True
            particula = None

        return ' '.join(novas)

    # -- ENDEREÇO -----------------------------------------------------------

    def endereco(self, original, chave):
        """
        Endereço fictício com a mesma estrutura do original.

        No corpus, endereço raramente é "rua tal, número tal". Aparece como bairro, como
        município, como "morador de tal lugar", muitas vezes numa palavra só. Gerar sempre
        "Rua Fulana" ensinava ao modelo um formato que quase não existe no texto real.

        Por isso a troca é feita palavra por palavra:
          - o que dá estrutura (rua, bairro, de, km, pontuação) fica como está;
          - número vira outro número com a mesma quantidade de dígitos;
          - o resto, que é o que identifica o lugar, vira uma palavra do catálogo.

        A quantidade de palavras, a pontuação e a caixa do original são mantidas.
        """
        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('ENDERECO', chave)

        def gerar():
            rng = self._rng('ENDERECO', chave, original)
            novas = []
            trocou = False
            for palavra in (original or '').split():
                base = _sem_acento(palavra).lower().strip('.,;:()-/')
                if not base or base in ESTRUTURA_ENDERECO or len(base) == 1:
                    novas.append(palavra)
                elif base.isdigit():
                    minimo = 10 ** (len(base) - 1) if len(base) > 1 else 1
                    numero = str(rng.randint(minimo, 10 ** len(base) - 1))
                    novas.append(palavra.replace(palavra.strip('.,;:()-/'), numero))
                    trocou = True
                elif any(c.isalpha() for c in base):
                    candidatas = [p for p in PALAVRAS_DE_LUGAR
                                  if _sem_acento(p).lower() != base
                                  and _sem_acento(p).lower() not in ESTRUTURA_ENDERECO]
                    escolhida = espelhar_caixa(palavra, rng.choice(candidatas))
                    if palavra[:1].isupper() and not palavra.isupper():
                        escolhida = escolhida.capitalize()
                    novas.append(escolhida)
                    trocou = True
                else:
                    novas.append(palavra)

            if not trocou:
                # Menção feita só de palavras estruturais ('centro', 'zona rural'). Não
                # identifica um lugar, mas foi anotada como endereço: recebe um nome de
                # lugar para não repetir o original.
                return espelhar_caixa(original, rng.choice(PALAVRAS_DE_LUGAR))
            return ' '.join(novas)

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
        Deslocamento fixo por paciente, entre -365 e +365 dias, nunca zero.

        Sorteado uma vez e aplicado a TODAS as datas daquele paciente. É isso que
        preserva os intervalos: se o original tem alta 7 dias após a internação, o
        surrogate também tem. Sortear cada data isoladamente destruiria a coerência
        clínica ("retorno em 30 dias" deixaria de fazer sentido) e mataria o vínculo
        longitudinal que o hash do paciente existe para preservar.
        """
        if chave not in self._shift_datas:
            # O zero fica de fora do sorteio. Com ele, cerca de um paciente em cada 731
            # recebia deslocamento nulo e tinha todas as datas reais mantidas no corpus.
            dias = self._rng('SHIFT', chave).randint(-365, 364)
            self._shift_datas[chave] = dias + 1 if dias >= 0 else dias
        return self._shift_datas[chave]

    def data(self, original_iso, chave):
        """
        Desloca uma data pelo shift do paciente.

        O caso principal é a data ISO (YYYY-MM-DD), que é como a normalização entrega as
        datas completas. As datas incompletas, que a expressão regular não captura e que
        só aparecem porque foram anotadas à mão ('12 / 03', 'março de 2024', '2019'),
        passam por `deslocar_data_livre`, que desloca o que dá para deslocar e devolve
        no mesmo formato em que recebeu.

        O que não é reconhecido volta como veio, e é contado em `datas_nao_deslocadas`.
        Esse contador precisa ser conferido depois da geração: cada unidade dele é uma
        data real que continuou no corpus.
        """
        from datetime import date, timedelta

        if self.modo == self.MODO_PLACEHOLDER:
            return self._proximo_placeholder('DATA', chave)

        dias = self.deslocamento_dias(chave)
        m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', (original_iso or '').strip())
        if m:
            try:
                base = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                self._datas_nao_deslocadas += 1
                return original_iso
            return (base + timedelta(days=dias)).isoformat()

        deslocada = deslocar_data_livre(original_iso, dias)
        if deslocada is None:
            self._datas_nao_deslocadas += 1
            return original_iso
        return deslocada

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
        # Braço A. O valor real volta para o lugar do marcador, e o corpus passa pelo
        # mesmo caminho de código dos outros braços: mesma tokenização, mesma
        # reconstrução de labels. Assim a única diferença entre A e B é o valor.
        if self.modo == self.MODO_ORIGINAL:
            return original

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
            'datas_nao_deslocadas': self._datas_nao_deslocadas,
            'tipos_nao_suportados': self.tipos_nao_suportados(),
            'colisoes_evitadas':    self._colisoes_evitadas,
            'colisoes_nao_resolvidas': len(self._colisoes_nao_resolvidas),
        }
