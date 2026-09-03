from django.urls import path
from . import views

app_name = 'empadmin'
urlpatterns = [
    path('',views.adminIndexView,name='admin-index'),
    path('status/<str:status>',views.adminStatusList,name='admin-status'),
    path('candidatelist/?page=n',views.adminCandidateListView,name='admin-candidate-list'),
    path('employeelist/?page=n',views.adminEmployeeeListView,name='admin-employee-list'),
    path('login/',views.adminLoginView,name='admin-login'),
    path('logout/',views.adminLogoutView,name='admin-logout'),
    path('feedback/<int:id>/',views.adminFeedback,name='admin-feedback'),
    path('exam/<str:command>/<int:id>/',views.adminExamUpdate,name='admin-exam'),
    path('update/<int:id>/',views.adminUpdateView,name='admin-update'),
    path('delete/<int:id>/',views.adminDeleteView,name='admin-delete'),
    path('empupdate/<int:id>/',views.adminEmployeeUpdateView,name='admin-emp-update'),
    path('employeelist/empdelete/<int:id>/',views.adminEmployeeDeleteView,name='admin-emp-delete'),
    path('employeelist/empstatusupdate/<str:status>/<int:id>/',views.adminEmployeeStatusView,name='admin-emp-status-update'),
]