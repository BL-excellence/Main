# accounts/views.py
from django.db import models
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect


from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect

# @csrf_protect
# def login_view(request):
#     if request.method == 'POST':
#         username = request.POST.get('email')  # L’email est utilisé comme username dans ce cas
#         password = request.POST.get('password')
#
#         user = authenticate(request, username=username, password=password)
#         if user:
#             login(request, user)
#
#             # Redirection selon le rôle
#             if user.role == 'admin':
#                 return redirect('accounts:admin_dashboard')
#             elif user.role == 'metadonneur':
#                 return redirect('dashboard:metadonneur_home')
#             elif user.role == 'annotateur':
#                 return redirect('dashboard:annotateur_home')
#             elif user.role == 'expert':
#                 return redirect('dashboard:expert_home')
#             else:
#                 return redirect('dashboard:home')
#         else:
#             messages.error(request, 'Email ou mot de passe incorrect.')
#
#     # Comptes de démonstration affichés dans le template
#     demo_accounts = [
#         {'email': 'marie@company.com', 'role': 'Métadonneur', 'password': 'password123'},
#         {'email': 'jean@company.com', 'role': 'Annotateur', 'password': 'password123'},
#         {'email': 'sophie@company.com', 'role': 'Expert métier', 'password': 'password123'},
#     ]
#
#     return render(request, 'accounts/login.html', {'demo_accounts': demo_accounts})

from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib import messages

@csrf_protect
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('email')  # champ "email" utilisé comme username
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard:home')  # Redirection unique, rôle géré dans dashboard_home
        else:
            messages.error(request, 'Email ou mot de passe incorrect.')

    # Comptes de démonstration affichés dans le template
    demo_accounts = [
        {'email': 'marie@company.com', 'role': 'Métadonneur', 'password': 'password123'},
        {'email': 'jean@company.com', 'role': 'Annotateur', 'password': 'password123'},
        {'email': 'sophie@company.com', 'role': 'Expert métier', 'password': 'password123'},
    ]

    return render(request, 'accounts/login.html', {'demo_accounts': demo_accounts})

@login_required
def logout_view(request):
    logout(request)
    return redirect('accounts:login')


# accounts/views.py (ajout des vues admin)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from .models import User
from .forms import UserCreationForm, UserUpdateForm


def is_admin(user):
    return user.is_authenticated and user.role == 'admin'


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    """Tableau de bord administrateur"""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active_user=True).count()
    inactive_users = User.objects.filter(is_active_user=False).count()

    # Statistiques par rôle
    role_stats = {}
    for role, label in User.ROLE_CHOICES:
        role_stats[label] = User.objects.filter(role=role).count()

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'role_stats': role_stats,
    }

    return render(request, 'accounts/admin_dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def manage_users(request):
    """Gestion des utilisateurs"""
    users = User.objects.all().order_by('-created_at')

    # Filtrage
    role_filter = request.GET.get('role')
    status_filter = request.GET.get('status')
    search = request.GET.get('search')

    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == 'active':
        users = users.filter(is_active_user=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active_user=False)
    if search:
        users = users.filter(
            models.Q(username__icontains=search) |
            models.Q(email__icontains=search) |
            models.Q(first_name__icontains=search) |
            models.Q(last_name__icontains=search)
        )

    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'role_choices': User.ROLE_CHOICES,
        'current_filters': {
            'role': role_filter,
            'status': status_filter,
            'search': search,
        }
    }

    return render(request, 'accounts/manage_users.html', context)
@login_required
def profile_view(request):
    """Page de profil utilisateur"""
    return render(request, 'accounts/profile.html', {'user': request.user})
