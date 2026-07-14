from .models import Experimento


def experimento_ativo(request):
    """
    Injeta o experimento ativo (armazenado na sessão) em todos os templates.
    Disponibiliza também a lista completa de experimentos para o seletor da sidebar.
    """
    exp_id = request.session.get('experimento_ativo_id')
    experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None
    return {
        'experimento_ativo':    experimento,
        'todos_experimentos':   Experimento.objects.order_by('-criado_em'),
    }
