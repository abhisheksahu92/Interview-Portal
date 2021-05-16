from django.shortcuts import render
from django.views.generic import CreateView,ListView,TemplateView
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth import authenticate,login,logout
from django.http import HttpResponseRedirect,Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .forms import CandidateCreateForm,CandidateSignupForm,CandidateLoginForm
from .models import Candidate

class CandidateIndexView(TemplateView):
    template_name = 'candidate/index.html'

class CandidateListView(ListView):
    template_name = 'candidate/list.html'
    model = Candidate
    context_object_name = 'candidate-list'
    paginate_by = 10

def candidateProfileView(request):
    form = CandidateCreateForm(request.POST or None)
    qs = Candidate.objects.filter(username=request.user)
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
                                 skill=skill)
        messages.success(request, 'Profile is completed.')
        return HttpResponseRedirect(reverse('candidate:candidate-list'))
    else:
        return render(request, 'Candidate/profile.html', {'form': form,'done':qs.exists(),'qs':qs.first()})


def candidateSignupView(request):
    form = CandidateSignupForm(request.POST or None)
    if form.is_valid():
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        User.objects.create_user(
            username = username,
            password=password
        )
        messages.success(request,'Signup is Done.')
        return HttpResponseRedirect(reverse('candidate:candidate-login'))
    else:
        return render(request,'Candidate/signup.html',{'form':form})

def candidateLoginView(request):
    form = CandidateLoginForm(request.POST or None)
    if form.is_valid():
        user = authenticate(username = form.cleaned_data.get('username'),password = form.cleaned_data.get('password'))
        if user:
            login(request,user)
            return HttpResponseRedirect(reverse('candidate:candidate-index'))
        else:
            messages.error(request,'Invalid Credentials')
            return HttpResponseRedirect(reverse('candidate:candidate-login'))
    return render(request,'candidate/login.html',{'form':form})

@login_required
def candidateLogoutView(request):
    logout(request)
    messages.success(request, 'Logout Done.')
    return HttpResponseRedirect(reverse('candidate:candidate-index'))


