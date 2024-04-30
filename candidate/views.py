from django.shortcuts import render,get_object_or_404
from django.views.generic import CreateView,ListView,TemplateView
from django.contrib.auth.models import User,Group
from django.contrib.auth import authenticate,login,logout
from django.http import HttpResponseRedirect,Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from .forms import CandidateCreateForm,CandidateSignupForm,CandidateLoginForm,CandidateUpdateForm
from .models import Candidate,CandidateResult
import os

def is_user_group_correct(user):
    query_set = Group.objects.filter(user = user)
    return query_set.values()[0].get('name') == 'Candidate'

def send_mail_candidate(mail_template,context,email,subject='Interview Update'):
    subject = subject
    html_message = render_to_string(f'candidate/{mail_template}.html', context)
    plain_message = strip_tags(html_message)
    from_email = settings.EMAIL_HOST_USER
    to = email
    send_mail(subject, plain_message, from_email, [to], html_message=html_message)

def candidateIndexView(request):
    candidate = {}
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    if request.user.is_anonymous:
        status = 'NOTLOGGED'
    else:
        qs = Candidate.objects.filter(username=request.user)
        qs_result = CandidateResult.objects.filter(candidate_id=qs.first())
        candidate = qs_result.first()
        if qs.exists():
            status = qs.first().status
        else:
            status = 'No Status'
    return render(request, 'candidate/index.html', {'status':status,'candidate':candidate})

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
        email = user.email
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
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        messages.success(request, 'Candidate registration is completed.')
        send_mail_candidate('registration',{'first_name':first_name,'last_name':last_name},email)
        return HttpResponseRedirect(reverse('candidate:candidate-profile'))
    else:
        return render(request, 'candidate/profile.html', {'form': form,'done':qs.exists(),'qs':qs.first(),'file':file})

def candidateSignupView(request):
    if not request.user.is_anonymous and not is_user_group_correct(request.user):
        logout(request)
        return HttpResponseRedirect(reverse('index'))
    
    form = CandidateSignupForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        email = form.cleaned_data.get('email')
        User.objects.create_user(
            username = username,
            password=password,
            email=email
        )
        group = Group.objects.get(name='Candidate')
        group.user_set.add(User.objects.get(username=username))
        send_mail_candidate('signup_mail',{'username':username},email)
        messages.success(request,'Candidate signup is done.')
        return HttpResponseRedirect(reverse('candidate:candidate-login'))
    else:
        return render(request,'candidate/signup.html',{'form':form})

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
                send_mail_candidate('login_mail',{'first_name':django_user.first_name,'last_name':django_user.last_name},django_user.email)
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

@login_required(login_url="/candidate/login/") 
def candidateUpdateView(request,pk=None):
    qs_update = get_object_or_404(Candidate,id=pk)
    user = User.objects.get(username=request.user)
    form = CandidateUpdateForm(request.POST or None,request.FILES or None,instance=qs_update)
    if form.is_valid():
        instance = form.save(commit=False)
        instance.save(update_fields=['first_name', 'last_name', 'dateofbirth','experience',
                    'noticeperiod','source','skill','resume'])
        user.first_name = form.cleaned_data.get('first_name')
        user.last_name = form.cleaned_data.get('last_name')
        user.save()
        return HttpResponseRedirect(reverse('candidate:candidate-profile'))
    context = {'form': form}
    return render(request, template_name='candidate/edit.html', context=context)

