from django.shortcuts import render
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
import datetime
from .forms import EmployeeLoginForm,EmployeeSignupForm,EmployeeProfileForm,EmployeeFeedbackForm
from .models import Employee
from candidate.models import Candidate,CandidateResult
from candidate.views import send_mail_candidate

def isEmployee(employee):
    emp_qs = Employee.objects.filter(employee_username=employee)
    return emp_qs.exists()

def employeeIndexView(request):
    if not request.user.is_staff and request.user.is_authenticated:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))

    registered = False
    if request.user.is_staff and Employee.objects.filter(employee_username=request.user,employee_status='Approved').exists():
        registered = True
    return render(request, 'employee/index.html', {'registered': registered})

@login_required(login_url="/employee/login/")
def employeeListView(request):
    if not request.user.is_staff or not isEmployee(request.user):
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))

    registered = False
    qs_employee = Employee.objects.filter(employee_username=request.user).first()

    if qs_employee.employee_status == 'Pending':
        messages.warning(request, 'Pending Approval.')
        return HttpResponseRedirect(reverse('employee:employee-index'))
    elif qs_employee.employee_status == 'Rejected':
        messages.warning(request, 'Approval Rejected.')
        return HttpResponseRedirect(reverse('employee:employee-index'))
    
    if qs_employee.employee_status == 'Approved':
        registered = True

    skill = qs_employee.employee_skill
    level = qs_employee.employee_level
    if level == 'L1':
        candidate_list = CandidateResult.objects.filter(status_l1='Pending',candidate_id__skill=skill,candidate_id__assessment_result=True,candidate_id__status='Pending')
    elif level == 'L2':
        candidate_list = CandidateResult.objects.filter(status_l1='Selected',status_l2='Pending',candidate_id__skill=skill)
    elif level == 'HR':
        candidate_list = CandidateResult.objects.filter(status_l1='Selected',status_l2='Selected',status_hr='Pending')
    return render(request, 'employee/list.html', {'candidate_list': candidate_list,'registered':registered})

@login_required(login_url="/employee/login/") 
def employeeProfileView(request):
    if not request.user.is_staff:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    registered = False
    candidate_selected,candidate_rejected = 0,0
    form = EmployeeProfileForm(request.POST or None)
    qs = Employee.objects.filter(employee_username=request.user)

    registered = False
    if qs.exists():
        level = qs.first().employee_level
        status = qs.first().employee_status
        filters_selected = {f'status_{level.lower()}':'Selected',f'{level.lower()}_by': qs.first()}
        filters_rejected = {f'status_{level.lower()}':'Rejected',f'{level.lower()}_by': qs.first()}
        candidate_selected = CandidateResult.objects.filter(**filters_selected).count()
        candidate_rejected = CandidateResult.objects.filter(**filters_rejected).count()
        if status == 'Approved':
            registered = True

    if form.is_valid():
        employee_username = User.objects.get(username=request.user)
        employee_name = form.cleaned_data['employee_name']
        employee_skill = form.cleaned_data['employee_skill']
        employee_level = form.cleaned_data['employee_level']
        Employee.objects.create(employee_username=employee_username,
                                 employee_name=employee_name,
                                 employee_skill=employee_skill,
                                 employee_email=request.user.email,
                                 employee_level=employee_level)
        messages.success(request, 'Profile is completed.')
        return HttpResponseRedirect(reverse('employee:employee-list'))
    else:
        return render(request, 'employee/profile.html', {'form': form,'done':qs.exists(),'qs':qs.first(),'registered':registered,'candidate_selected':candidate_selected,'candidate_rejected':candidate_rejected})

def employeeSignupView(request):     
    form = EmployeeSignupForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        email = form.cleaned_data.get('email')
        User.objects.create_user(
            username = username,
            password=password,
            is_staff = True,
            email=email
        )
        messages.success(request,'Signup is Done.')
        return HttpResponseRedirect(reverse('employee:employee-login'))
    else:
        return render(request,'employee/signup.html',{'form':form})

def employeeLoginView(request):  
    form = EmployeeLoginForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        django_user = User.objects.get(username=username)
        if django_user.is_staff:
            user = authenticate(username = username,password = password)
            if user:
                login(request,user)
                return HttpResponseRedirect(reverse('employee:employee-index'))
            else:
                messages.error(request,'Invalid Credentials')
                return HttpResponseRedirect(reverse('employee:employee-login'))
        else:
            messages.error(request, 'Please Register as Employee.')
            return HttpResponseRedirect(reverse('employee:employee-login'))
    return render(request,'employee/login.html',{'form':form})

@login_required(login_url="/employee/login/") 
def employeeStatusList(request,status):
    if not request.user.is_staff or not isEmployee(request.user):
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    qs_employee = Employee.objects.filter(employee_username=request.user).first()

    if qs_employee.employee_status == 'Pending':
        messages.warning(request, 'Pending Approval.')
        return HttpResponseRedirect(reverse('employee:employee-index'))
    elif qs_employee.employee_status == 'Rejected':
        messages.warning(request, 'Approval Rejected.')
        return HttpResponseRedirect(reverse('employee:employee-index'))

    registered = False
    if isEmployee(request.user) and qs_employee.employee_status == 'Approved':
        registered = True
    
    level = qs_employee.employee_level
    filters_status = {f'status_{level.lower()}':status,f'{level.lower()}_by': qs_employee}
    candidate_list = CandidateResult.objects.filter(**filters_status)
    return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered,'level':level.lower()})

@login_required(login_url="/employee/login/") 
def employeeFeedback(request,id=None):
    if not request.user.is_staff or not isEmployee(request.user):
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    form = EmployeeFeedbackForm(request.POST or None)
    candidate = Candidate.objects.filter(id=id).first()
    qs_candidate_result = CandidateResult.objects.filter(candidate_id=candidate)
    qs_employee = Employee.objects.filter(employee_username=request.user).first()

    if qs_employee.employee_status == 'Pending':
        messages.warning(request, 'Pending Approval.')
        return HttpResponseRedirect(reverse('employee:employee-index'))
    elif qs_employee.employee_status == 'Rejected':
        messages.warning(request, 'Approval Rejected.')
        return HttpResponseRedirect(reverse('employee:employee-index'))
    
    registered = False
    if isEmployee(request.user) and qs_employee.employee_status == 'Approval':
        registered = True
    level = qs_employee.employee_level
    if form.is_valid():
        status = form.cleaned_data.get('status')
        feedback = form.cleaned_data.get('feedback')
        data = {f'feedback_{level.lower()}':feedback,
                f'status_{level.lower()}':status,
                f'{level.lower()}_by': qs_employee,
                f'{level.lower()}_at': datetime.datetime.now()}
        qs_candidate_result.update(**data)
        if level == 'HR' and status == 'Selected':
            Candidate.objects.filter(id=id).update(status='Selected')
        elif status == 'Rejected':
            Candidate.objects.filter(id=id).update(status='Rejected')
        send_mail_candidate(f'{status.lower()}_mail',{'first_name':candidate.first_name,'last_name':candidate.last_name,'level':level.upper()},candidate.email)
        return HttpResponseRedirect(reverse('employee:employee-list'))
    return render(request, 'employee/feedback.html',{'form': form, 'registered': registered,'candidate':candidate,'candidate_result':qs_candidate_result.first()})

@login_required(login_url="/employee/login/") 
def employeeLogoutView(request):
    logout(request)
    messages.success(request, 'Logout Done.')
    return HttpResponseRedirect(reverse('employee:employee-login'))

