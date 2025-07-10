# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import User


class CustomUserCreationForm(UserCreationForm):
    """Formulaire de création d'utilisateur personnalisé"""

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'speciality', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True


class CustomUserChangeForm(UserChangeForm):
    """Formulaire de modification d'utilisateur personnalisé"""

    class Meta:
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Administration des utilisateurs"""

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active_user', 'created_at')
    list_filter = ('role', 'is_active_user', 'is_staff', 'created_at')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'speciality')
    ordering = ('-created_at',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Informations personnalisées', {
            'fields': ('role', 'phone', 'speciality', 'is_active_user')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'email',
                'first_name',
                'last_name',
                'role',
                'phone',
                'speciality',
                'password1',
                'password2',
            ),
        }),
    )

    actions = ['activate_users', 'deactivate_users', 'reset_passwords']

    def activate_users(self, request, queryset):
        """Activer les utilisateurs sélectionnés"""
        updated = queryset.update(is_active_user=True)
        self.message_user(request, f'{updated} utilisateur(s) activé(s).')

    activate_users.short_description = "Activer les utilisateurs sélectionnés"

    def deactivate_users(self, request, queryset):
        """Désactiver les utilisateurs sélectionnés"""
        updated = queryset.update(is_active_user=False)
        self.message_user(request, f'{updated} utilisateur(s) désactivé(s).')

    deactivate_users.short_description = "Désactiver les utilisateurs sélectionnés"
