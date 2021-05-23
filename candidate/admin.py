from django.contrib import admin
from .models import Candidate,CandidateResult

# Register your models here.
@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['username', 'first_name', 'last_name', 'email', 'phone', 'dateofbirth','experience',
                    'noticeperiod','source','skill']

@admin.register(CandidateResult)
class CandidateResultAdmin(admin.ModelAdmin):
    list_display = ['candidate_id',]