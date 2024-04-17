from django.shortcuts import render
from django.views.generic import CreateView,ListView,TemplateView
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.http import HttpResponseRedirect,Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .forms import CandidateCreateForm,CandidateSignupForm,CandidateLoginForm
from .models import Candidate
import os

def is_user_group_correct(user):
    query_set = Group.objects.filter(user = user)
    return query_set.values()[0].get('name') == 'Candidate'

def candidateIndexView(request):
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    if request.user.is_anonymous:
        status = 'NOTLOGGED'
    else:
        qs = Candidate.objects.filter(username=request.user)
        if qs.exists():
            status = qs.first().status
        else:
            status = 'No Status'
    return render(request, 'Candidate/index.html', {'status':status})

@login_required(login_url="/candidate/login/") 
def candidateProfileView(request):
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    file = None
    form = CandidateCreateForm(request.POST or None,request.FILES)
    qs = Candidate.objects.filter(username=request.user)
    if qs.exists():
        file = str(qs.first().resume).split('/')[-1]

    if form.is_valid():
        user = User.objects.get(username=request.user)
        first_name = form.cleaned_data['first_name']
        last_name = form.cleaned_data['last_name']
        email = form.cleaned_data['email']
        phone = form.cleaned_data['phone']
        dateofbirth = form.cleaned_data['dateofbirth']
        experience = form.cleaned_data['experience']
        noticeperiod = form.cleaned_data['noticeperiod']
        source = form.cleaned_data['source']
        skill = form.cleaned_data['skill']
        Candidate.objects.create(username=user,
                                 first_name=first_name,
                                 last_name=last_name,
                                 email=email,
                                 phone=phone,
                                 dateofbirth=dateofbirth,
                                 experience=experience,
                                 noticeperiod=noticeperiod,
                                 source=source,
                                 skill=skill,
                                 resume = request.FILES['resume'])
        messages.success(request, 'Profile is completed.')
        return HttpResponseRedirect(reverse('candidate:candidate-profile'))
    else:
        return render(request, 'Candidate/profile.html', {'form': form,'done':qs.exists(),'qs':qs.first(),'file':file})

def candidateSignupView(request):
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    form = CandidateSignupForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        User.objects.create_user(
            username = username,
            password=password
        )
        group = Group.objects.get(name='Candidate')
        group.user_set.add(User.objects.get(username=username))
        messages.success(request,'Signup is Done.')
        return HttpResponseRedirect(reverse('candidate:candidate-login'))
    else:
        return render(request,'Candidate/signup.html',{'form':form})

def candidateLoginView(request):
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    form = CandidateLoginForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        django_user = User.objects.get(username=username)
        group = django_user.groups.filter(name='Candidate').exists()
        if group:
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                return HttpResponseRedirect(reverse('candidate:candidate-index'))
            else:
                messages.error(request, 'Invalid Credentials')
                return HttpResponseRedirect(reverse('candidate:candidate-login'))
        else:
            messages.error(request, 'Please register as Candidate and login again.')
            return HttpResponseRedirect(reverse('candidate:candidate-login'))
    return render(request,'candidate/login.html',{'form':form})

@login_required(login_url="/candidate/login/") 
def candidateLogoutView(request):
    logout(request)
    messages.success(request, 'Logout Done.')
    return HttpResponseRedirect(reverse('candidate:candidate-index'))


