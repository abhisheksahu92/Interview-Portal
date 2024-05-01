from django.urls import path
from . import views

app_name = 'employee'
urlpatterns = [
    path('',views.employeeIndexView,name='employee-index'),
    path('profile/',views.employeeProfileView,name='employee-profile'),
    path('status/<str:status>',views.employeeStatusList,name='employee-status'),
    path('list/?page=n',views.employeeListView,name='employee-list'),
    path('signup/',views.employeeSignupView,name='employee-signup'),
    path('feedback/<int:id>/',views.employeeFeedback,name='employee-feedback'),
    path('login/',views.employeeLoginView,name='employee-login'),
    path('logout/',views.employeeLogoutView,name='employee-logout'),
]