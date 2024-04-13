from django.shortcuts import render
from candidate.models import Candidate

# Create your views here.
def dashboardIndexView(request):
    return render(request, 'dashboard/index.html')

def dashboardSelectedView(request):
    candidate_list = Candidate.objects.filter(status='Selected')
    return render(request, 'dashboard/selected.html',{'candidate_list': candidate_list})

def dashboardRejectedView(request):
    candidate_list = Candidate.objects.filter(status='Rejected')
    return render(request, 'dashboard/rejected.html',{'candidate_list': candidate_list})

def dashboardCandidatesView(request):
    candidate_list = Candidate.objects.all()
    return render(request, 'dashboard/candidates.html',{'candidate_list': candidate_list})