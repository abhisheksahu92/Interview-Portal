from django.urls import path
from . import views

app_name = 'empadmin'
urlpatterns = [
    path('',views.adminIndexView,name='admin-index'),
    path('status/<str:status>',views.adminStatusList,name='admin-status'),
    path('canidatelist/?page=n',views.adminCandidateListView,name='admin-candidate-list'),
    path('employeelist/?page=n',views.adminEmployeeeListView,name='admin-employee-list'),
    path('login/',views.adminLoginView,name='admin-login'),
    path('logout/',views.adminLogoutView,name='admin-logout'),
    path('feedback/<int:id>/',views.adminFeedback,name='admin-feedback'),
]