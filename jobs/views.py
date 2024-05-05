from django.shortcuts import render
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse

from .models import Jobs,JobsExam
from .forms import JobsForm
# Create your views here.

@login_required(login_url="/admin/login/") 
def job_list(request):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    jobs = Jobs.objects.all()
    return render(request, 'jobs/job_list.html', {'jobs': jobs})

@login_required(login_url="/admin/login/") 
def job_detail(request, pk):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    job = Jobs.objects.get(pk=pk)
    exam = JobsExam.objects.filter(job_id=job)
    if exam.exists:
        exam = exam.first()
    else:
        exam = False
    return render(request, 'jobs/job_detail.html', {'job': job,'exam':exam})

@login_required(login_url="/admin/login/") 
def create_job(request):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    if request.method == 'POST':
        form = JobsForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('jobs:job-list'))
    else:
        form = JobsForm()
    return render(request, 'jobs/create_job.html', {'form': form})

@login_required(login_url="/admin/login/") 
def update_job(request, pk):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    job = Jobs.objects.get(pk=pk)
    if request.method == 'POST':
        form = JobsForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('jobs:job-detail',args=[pk]))

    else:
        form = JobsForm(instance=job)
    return render(request, 'jobs/update_job.html', {'form': form})

@login_required(login_url="/admin/login/") 
def delete_job(request, pk):
    if not request.user.is_superuser:
        logout(request)
        messages.warning(request, 'Access Denied.')
        return HttpResponseRedirect(reverse('index'))
    
    job = Jobs.objects.get(pk=pk)
    if request.method == 'POST':
        job.delete()
        return HttpResponseRedirect(reverse('jobs:job-list'))
    return render(request, 'jobs/delete_job.html', {'job': job})

@login_required(login_url="/admin/login/") 
def select_exam(request, pk,exam):
    try:
        if not request.user.is_superuser:
            logout(request)
            messages.warning(request, 'Access Denied.')
            return HttpResponseRedirect(reverse('index'))
        
        job = Jobs.objects.get(pk=pk)
        if request.method == 'POST':
            JobsExam.objects.get_or_create(job_id=job,exam=exam)
            return JsonResponse({'status': 'Success'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    
    
