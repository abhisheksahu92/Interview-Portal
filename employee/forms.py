from django import forms
from .models import Employee
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class EmployeeProfileForm(forms.ModelForm):
    passcode = forms.CharField(label='Authentication Key', max_length=10, required=False)
    class Meta:
        model = Employee
        fields = ['employee_name', 'employee_skill', 'employee_level','passcode']

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('employee_level') == 'L1':
            if cleaned_data.get('passcode') != 'l1234':
                raise ValidationError('Authentication Key is not correct')
        if cleaned_data.get('employee_level') == 'L2':
            if cleaned_data.get('passcode') != 'l2345':
                raise ValidationError('Authentication Key is not correct')
        if cleaned_data.get('employee_level') == 'HR':
            if cleaned_data.get('passcode') != 'hr1234':
                raise ValidationError('Authentication Key is not correct')

class EmployeeSignupForm(forms.ModelForm):
    password = forms.CharField(label='Password', max_length=120, required=True,
                                       widget=forms.PasswordInput())
    password_confirm = forms.CharField(label='Confirm Password', max_length=120,
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


class EmployeeLoginForm(forms.Form):
    username = forms.CharField(label = 'Username', max_length=120, required=True)
    password = forms.CharField(label = 'Password', max_length=120, required=True,widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        if not User.objects.filter(username = username).exists():
            raise forms.ValidationError('Username not exists')

class EmployeeFeedbackForm(forms.Form):
    status   = forms.ChoiceField(label = 'Status', 
                                 choices=(('Selected','Selected'),('Rejected','Rejected')), 
                                 required=True)
    feedback = forms.CharField(label = 'Feedback', max_length= 1000, required=True,widget=forms.Textarea)
    


