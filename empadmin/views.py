from django.shortcuts import render
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from employee.models import Employee
from .forms import AdminLoginForm
from candidate.models import Candidate,CandidateResult
from candidate.views import send_mail_candidate

def adminIndexView(request):
    return render(request, 'admin/index.html')

@login_required(login_url="/admin/login/")
def adminCandidateListView(request):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))

    candidate_list = Candidate.objects.all()
    return render(request, 'admin/candidate_list.html', {'candidate_list': candidate_list})

@login_required(login_url="/admin/login/")
def adminEmployeeeListView(request):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))

    employee_list = Employee.objects.all()
    return render(request, 'admin/employee_list.html', {'employee_list': employee_list})

def adminLoginView(request):  
    form = AdminLoginForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        django_user = User.objects.get(username=username)
        if django_user.is_superuser:
            user = authenticate(username = username,password = password)
            if user:
                login(request,user)
                return HttpResponseRedirect(reverse('admin:admin-index'))
            else:
                messages.error(request,'Invalid Credentials')
                return HttpResponseRedirect(reverse('admin:admin-login'))
        else:
            messages.error(request, 'Please Register as Admin.')
            return HttpResponseRedirect(reverse('admin:admin-login'))
    return render(request,'admin/login.html',{'form':form})

@login_required(login_url="/admin/login/") 
def adminStatusList(request,status):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))

    candidate_list = Candidate.objects.filter(status=status)
    return render(request, 'admin/selected_list.html', {'candidate_list': candidate_list})

@login_required(login_url="/admin/login/") 
def adminLogoutView(request):
    logout(request)
    messages.success(request, 'Logout Done.')
    return HttpResponseRedirect(reverse('admin:admin-login'))

@login_required(login_url="/admin/login/") 
def adminFeedback(request,id=None):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    qs_candidate_result = CandidateResult.objects.get(candidate_id__id=id)
    return render(request, 'admin/feedback.html',{'candidate':qs_candidate_result})

@login_required(login_url="/admin/login/") 
def adminExamUpdate(request,command,id):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    candidate = Candidate.objects.filter(id=id).first()
    if command == 'Reset':
        candidate.assessment_data = None
        candidate.assessment_result = not candidate.assessment_result
    else:
        candidate.status = 'Pending'
    candidate.save()
    return HttpResponseRedirect(reverse('admin:admin-feedback',args=[id]))

