from django.contrib import admin

from .models import GeracaoCorpusSurrogate, VersaoCorpusSurrogate


class VersaoCorpusSurrogateInline(admin.TabularInline):
    """
    As versões aparecem dentro da geração porque é assim que elas são lidas na prática:
    ninguém procura a versão v07 solta, procura a rodada e compara as versões dela entre
    si. Somente leitura de propósito, já que editar um número aqui desfaria a
    correspondência com o arquivo em disco.
    """

    model = VersaoCorpusSurrogate
    extra = 0
    can_delete = False
    fields = ('rotulo', 'modo', 'seed', 'sentencas', 'entidades_distintas',
              'colisoes_nao_resolvidas', 'placeholders_restantes',
              'problemas_alinhamento', 'arquivo')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(GeracaoCorpusSurrogate)
class GeracaoCorpusSurrogateAdmin(admin.ModelAdmin):
    list_display = ('id', 'criado_em', 'sessao', 'total_versoes', 'com_contraprova',
                    'commit_curto', 'reproduzivel')
    list_filter = ('com_contraprova', 'repositorio_sujo', 'sessao')
    date_hierarchy = 'criado_em'
    inlines = [VersaoCorpusSurrogateInline]
    readonly_fields = ('criado_em', 'commit_git', 'repositorio_sujo', 'hash_mapa_phi',
                       'relatorio_leitura_json', 'anotador_base_id', 'total_versoes',
                       'com_contraprova', 'caminho_saida')

    @admin.display(description='Commit')
    def commit_curto(self, obj):
        if not obj.commit_git:
            return 'não identificado'
        return obj.commit_git[:12] + (' (sujo)' if obj.repositorio_sujo else '')

    @admin.display(boolean=True, description='Reproduzível')
    def reproduzivel(self, obj):
        return obj.reproduzivel


@admin.register(VersaoCorpusSurrogate)
class VersaoCorpusSurrogateAdmin(admin.ModelAdmin):
    """
    Existe além do inline para permitir comparar versões de gerações diferentes, que é o
    que se faz quando uma rodada é refeita e se quer saber o que mudou.
    """

    list_display = ('id', 'geracao', 'rotulo', 'modo', 'seed', 'sentencas',
                    'entidades_distintas', 'limpa')
    list_filter = ('modo', 'geracao')
    search_fields = ('rotulo', 'arquivo', 'hash_arquivo')

    @admin.display(boolean=True, description='Sem pendência')
    def limpa(self, obj):
        return obj.limpa
