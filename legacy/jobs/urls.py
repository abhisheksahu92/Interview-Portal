# urls.py
from django.urls import path
from . import views

app_name = 'jobs'

urlpatterns = [
    path('', views.job_list, name='job-list'),
    path('<int:pk>/', views.job_detail, name='job-detail'),
    path('create/', views.create_job, name='create-job'),
    path('<int:pk>/selectexam/<str:exam>', views.select_exam, name='select-exam'),
    path('<int:pk>/update/', views.update_job, name='update-job'),
    path('<int:pk>/delete/', views.delete_job, name='delete-job'),
]
