from django import forms
from .models import Candidate
from django.contrib.auth.models import User

class DateInput(forms.DateInput):
    input_type = 'date'

class CandidateCreateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['first_name', 'last_name', 'phone', 'dateofbirth','experience',
                    'noticeperiod','source','skill','resume']
        NOTICEPERIOD_CHOICES = (
                ('', 'Select Notice Period'),
                (1,1), #First one is the value of select option and second is the displayed value in option
                (2,2),
                (3,3),
                )
        widgets = {
            'dateofbirth': DateInput(),
            'noticeperiod': forms.Select(choices=NOTICEPERIOD_CHOICES,attrs={'class': 'form-control'}),
        }

class CandidateUpdateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['first_name', 'last_name', 'dateofbirth','experience',
                    'noticeperiod','source','skill','resume']
        NOTICEPERIOD_CHOICES = (
                ('', 'Select Notice Period'),
                (1,1), #First one is the value of select option and second is the displayed value in option
                (2,2),
                (3,3),
                )
        widgets = {
            'dateofbirth': DateInput(),
            'noticeperiod': forms.Select(choices=NOTICEPERIOD_CHOICES,attrs={'class': 'form-control'}),
        }

class CandidateSignupForm(forms.ModelForm):
    password = forms.CharField(label='Password', max_length=120, required=True,
                                       widget=forms.PasswordInput())
    password_confirm = forms.CharField(label='Confirm_Password', max_length=120,
                                       required=True, widget=forms.PasswordInput())
    class Meta:
        model = User
        fields = ['username','email','password','password_confirm']

    def clean(self):
        cleaned_data = super().clean()
        pass_0 = cleaned_data.get('password')
        pass_1 = cleaned_data.get('password_confirm')
        if pass_0 != pass_1:
            raise forms.ValidationError('Both password should be matched')


class CandidateLoginForm(forms.Form):
    username = forms.CharField(label = 'Username', max_length=120, required=True)
    password = forms.CharField(label = 'Password', max_length=120, required=True,widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        if not User.objects.filter(username = username).exists():
            raise forms.ValidationError('Username not exists')

