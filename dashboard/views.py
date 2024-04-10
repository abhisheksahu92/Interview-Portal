from django.shortcuts import render
from candidate.models import Candidate

# Create your views here.
def dashboardIndexView(request):
    candidate_list = Candidate.objects.all()
    return render(request, 'dashboard/index.html',{'candidate_list': candidate_list})