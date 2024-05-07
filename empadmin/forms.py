from django import forms
from django.contrib.auth.models import User
from candidate.models import Candidate
from employee.models import Employee

class AdminLoginForm(forms.Form):
    username = forms.CharField(label = 'Username', max_length=120, required=True)
    password = forms.CharField(label = 'Password', max_length=120, required=True,widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        if not User.objects.filter(username = username).exists():
            raise forms.ValidationError('Username not exists')
        
class AdminUpdateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['phone', 'email']

class AdminEmployeeUpdateForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['employee_name', 'employee_email', 'employee_skill', 'employee_level']

        def clean(self):
            cleaned_data = super().clean()
            email = cleaned_data.get('employee_email')
            if email != self.instance.employee_email:
                if Employee.objects.filter(employee_email=email).exists():
                    raise forms.ValidationError('Employee with this Official Email already exists.')
