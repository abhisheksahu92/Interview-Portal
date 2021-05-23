from django.shortcuts import render
from django.views.generic import CreateView,ListView,TemplateView
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .forms import EmployeeLoginForm,EmployeeSignupForm,EmployeeProfileForm,EmployeeFeedbackForm
from .models import Employee
from candidate.models import Candidate,CandidateResult

def isEmployee(employee):
    emp_qs = Employee.objects.filter(employee_username=employee)
    return emp_qs.exists()

def employeeIndexView(request):
    registered = False
    if request.user.is_authenticated:
        registered = True

    return render(request, 'employee/index.html', {'registered': registered})

def employeeListView(request):
    registered = False
    qs_employee = Employee.objects.filter(employee_username=request.user).first()
    if qs_employee:
        registered = True
    skill = qs_employee.employee_skill
    level = qs_employee.employee_level
    if level == 'L1':
        candidate_list = CandidateResult.objects.filter(status_l1='Pending',candidate_id__skill=skill)
    elif level == 'L2':
        candidate_list = CandidateResult.objects.filter(status_l1='Selected',status_l2='Pending',candidate_id__skill=skill)
    elif level == 'HR':
        candidate_list = CandidateResult.objects.filter(status_l1='Selected',status_l2='Selected',status_hr='Pending')
    return render(request, 'employee/list.html', {'candidate_list': candidate_list,'registered':registered})
    
def employeeProfileView(request):
    registered = False
    form = EmployeeProfileForm(request.POST or None)
    qs = Employee.objects.filter(employee_username=request.user)
    if qs.exists():
        registered = True

    if form.is_valid():
        employee_username = User.objects.get(username=request.user)
        employee_name = form.cleaned_data['employee_name']
        employee_email = form.cleaned_data['employee_email']
        employee_skill = form.cleaned_data['employee_skill']
        employee_level = form.cleaned_data['employee_level']
        Employee.objects.create(employee_username=employee_username,
                                 employee_name=employee_name,
                                 employee_email=employee_email,
                                 employee_skill=employee_skill,
                                 employee_level=employee_level)
        messages.success(request, 'Profile is completed.')
        return HttpResponseRedirect(reverse('employee:employee-list'))
    else:
        return render(request, 'employee/profile.html', {'form': form,'done':qs.exists(),'qs':qs.first(),'registered':registered})

def employeeSignupView(request):
    form = EmployeeSignupForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        User.objects.create_user(
            username = username,
            password=password
        )
        group = Group.objects.get(name='Employee')
        group.user_set.add(User.objects.get(username=username))
        messages.success(request,'Signup is Done.')
        return HttpResponseRedirect(reverse('employee:employee-login'))
    else:
        return render(request,'Employee/signup.html',{'form':form})

def employeeLoginView(request):
    form = EmployeeLoginForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        django_user = User.objects.get(username=username)
        group = django_user.groups.filter(name='Employee').exists()
        if group:
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

def employeeSelected(request):
    registered = False
    if isEmployee(request.user):
        registered = True
        qs_employee = Employee.objects.filter(employee_username=request.user).first()
        level = qs_employee.employee_level
        if level == 'L1':
            candidate_list = CandidateResult.objects.filter(status_l1='Selected',l1_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})
        elif level == 'L2':
            candidate_list = CandidateResult.objects.filter(status_l2='Selected',l2_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})
        elif level == 'HR':
            candidate_list = CandidateResult.objects.filter(status_hr='Selected',hr_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})

def employeeRejected(request):
    registered = False
    if isEmployee(request.user):
        registered = True
        qs_employee = Employee.objects.filter(employee_username=request.user).first()
        level = qs_employee.employee_level
        if level == 'L1':
            candidate_list = CandidateResult.objects.filter(status_l1='Rejected',l1_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})
        elif level == 'L2':
            candidate_list = CandidateResult.objects.filter(status_l2='Rejected',l2_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})
        elif level == 'HR':
            candidate_list = CandidateResult.objects.filter(status_hr='Rejected',hr_by=qs_employee)
            return render(request, 'employee/selected_list.html', {'candidate_list': candidate_list, 'registered': registered})

def employeeFeedback(request,id=None):
    form = EmployeeFeedbackForm(request.POST or None)
    candidate = Candidate.objects.filter(id=id).first()
    qs_candidate_result = CandidateResult.objects.filter(candidate_id=candidate)
    qs_employee = Employee.objects.filter(employee_username=request.user).first()
    registered = False
    if isEmployee(request.user):
        registered = True
        level = qs_employee.employee_level
        if form.is_valid():
            if level == 'L1':
                qs_candidate_result.update(
                                   feedback_l1=form.cleaned_data.get('feedback'),
                                   status_l1=form.cleaned_data.get('status'),
                                   l1_by=qs_employee)
            elif level == 'L2':
                qs_candidate_result.update(
                    feedback_l2=form.cleaned_data.get('feedback'),
                    status_l2=form.cleaned_data.get('status'),
                    l2_by=qs_employee)
            elif level == 'HR':
                qs_candidate_result.update(
                    feedback_hr=form.cleaned_data.get('feedback'),
                    status_hr=form.cleaned_data.get('status'),
                    hr_by=qs_employee)
                if form.cleaned_data.get('status') == 'Selected':
                    Candidate.objects.filter(id=id).update(status='Selected')
                elif form.cleaned_data.get('status') == 'Rejected':
                    Candidate.objects.filter(id=id).update(status='Rejected')
            return HttpResponseRedirect(reverse('employee:employee-list'))
    return render(request, 'employee/feedback.html',{'form': form, 'registered': registered,'candidate':candidate,'candidate_result':qs_candidate_result.first()})

@login_required
def employeeLogoutView(request):
    logout(request)
    messages.success(request, 'Logout Done.')
    return HttpResponseRedirect(reverse('employee:employee-login'))

