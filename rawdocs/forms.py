# rawdocs/forms.py

from django import forms
from django.contrib.auth.forms  import UserCreationForm
from django.contrib.auth.models import User, Group

ROLE_CHOICES = [
    ("Metadonneur", "Métadonneur"),
    ("Annotateur",  "Annotateur"),
    ("Expert",      "Expert"),
]

class URLForm(forms.Form):
    pdf_url = forms.URLField(
        label="URL du PDF",
        widget=forms.URLInput(attrs={
            "class":       "upload-cell__input",
            "placeholder": "Entrez l’URL du PDF et appuyez sur Entrée…",
            "id":          "id_pdf_url",
        })
    )

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role  = forms.ChoiceField(choices=ROLE_CHOICES, label="Profil")

    class Meta:
        model  = User
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit)
        group = Group.objects.get(name=self.cleaned_data["role"])
        user.groups.add(group)
        return user


class MetadataEditForm(forms.Form):
    title = forms.CharField(required=False)
    type = forms.CharField(required=False)
    publication_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    version = forms.CharField(required=False)
    source = forms.CharField(required=False)
    context = forms.CharField(required=False)
    country = forms.CharField(required=False)
    language = forms.CharField(required=False)
    url_source = forms.URLField(required=False)