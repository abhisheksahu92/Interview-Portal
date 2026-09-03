
from .models import Jobs
from django import forms

class DateInput(forms.DateInput):
    input_type = 'date'

class JobsForm(forms.ModelForm):
    class Meta:
        model = Jobs
        fields = '__all__'
        widgets = {
            'expiration_date': DateInput(),
            'posted_date': DateInput(),
        }

