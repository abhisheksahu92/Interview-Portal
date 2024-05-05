from django.shortcuts import render
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from employee.models import Employee
from .forms import AdminLoginForm,AdminUpdateForm,AdminEmployeeUpdateForm
from candidate.models import Candidate,CandidateResult
from django.http import JsonResponse
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
    elif command == 'Pass':
        candidate.assessment_result = True
        candidate.status = 'Pending'
    candidate.save()
    return HttpResponseRedirect(reverse('admin:admin-feedback',args=[id]))

@login_required(login_url="/admin/login/") 
def adminUpdateView(request,id):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    qs = Candidate.objects.filter(id=id).first()
    form = AdminUpdateForm(request.POST or None,initial={'phone':qs.phone,'email':qs.email})
    
    if form.is_valid():
        user = User.objects.get(username=request.user)
        qs.phone = form.cleaned_data['phone']
        qs.email = form.cleaned_data['email']
        user.email = form.cleaned_data['email']
        qs.save()
        user.save()
        messages.success(request, 'Candidate Updated.')
        return HttpResponseRedirect(reverse('admin:admin-feedback',args=[id]))
    else:
        return render(request, 'admin/update_candidate.html', {'form': form,'qs':qs})
    
@login_required(login_url="/admin/login/") 
def adminDeleteView(request,id):
    try:
        if not request.user.is_superuser:
            logout(request)
            messages.warning(request, 'Access Denied.')
            return HttpResponseRedirect(reverse('index'))
        
        if request.method == 'POST':
            qs = Candidate.objects.filter(id=id)
            CandidateResult.objects.filter(candidate_id=id).delete()
            User.objects.filter(id=qs.first().username_id).delete()
            Candidate.objects.filter(id=id).delete()
            return JsonResponse({'status': 'Success'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required(login_url="/admin/login/") 
def adminEmployeeUpdateView(request,id):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    qs = Employee.objects.filter(id=id).first()
    form = AdminEmployeeUpdateForm(request.POST or None,initial={
        'employee_name': qs.employee_name,
        'employee_email': qs.employee_email,
        'employee_skill':qs.employee_skill,
        'employee_level' : qs.employee_level
    },instance=qs)
    
    if form.is_valid():
        user = User.objects.get(username=qs.employee_username)
        qs.employee_name = form.cleaned_data['employee_name']
        qs.employee_email = form.cleaned_data['employee_email']
        qs.employee_skill = form.cleaned_data['employee_skill']
        qs.employee_level = form.cleaned_data['employee_level']
        user.email = form.cleaned_data['employee_email']
        qs.save()
        user.save()
        messages.success(request, 'Employee Updated.')
        return HttpResponseRedirect(reverse('admin:admin-employee-list'))
    else:
        return render(request, 'admin/update_employee.html', {'form': form,'qs':qs})
    
@login_required(login_url="/admin/login/") 
def adminEmployeeDeleteView(request,id):
    try:
        if not request.user.is_superuser:
            logout(request)
            messages.warning(request, 'Access Denied.')
            return HttpResponseRedirect(reverse('index'))
        
        if request.method == 'POST':    
            qs = Employee.objects.filter(id=id)

            User.objects.filter(id=qs.first().employee_username_id).delete()
            Employee.objects.filter(id=id).delete()
            return JsonResponse({'status': 'Success'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required(login_url="/admin/login/") 
def adminEmployeeStatusView(request,status,id):
    try:
        if not request.user.is_superuser:
            logout(request)
            messages.warning(request, 'Access Denied.')
            return HttpResponseRedirect(reverse('index'))
        
        if request.method == 'POST':
            qs = Employee.objects.filter(id=id).first()
            qs.employee_status = status
            qs.save()
            return JsonResponse({'status': 'Success'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)