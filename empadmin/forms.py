from django import forms
from django.contrib.auth.models import User

class AdminLoginForm(forms.Form):
    username = forms.CharField(label = 'Username', max_length=120, required=True)
    password = forms.CharField(label = 'Password', max_length=120, required=True,widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        if not User.objects.filter(username = username).exists():
            raise forms.ValidationError('Username not exists')
