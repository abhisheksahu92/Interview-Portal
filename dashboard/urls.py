from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [
    path('',views.dashboardIndexView,name='dashboard-index'),
    # path('profile/',views.employeeProfileView,name='employee-profile'),
    # path('selected/',views.employeeSelected,name='employee-selected'),
    # path('rejected/',views.employeeRejected,name='employee-rejected'),
    # path('list/?page=n',views.employeeListView,name='employee-list'),
    # path('signup/',views.employeeSignupView,name='employee-signup'),
    # path('feedback/<int:id>/',views.employeeFeedback,name='employee-feedback'),
    # path('login/',views.employeeLoginView,name='employee-login'),
    # path('logout/',views.employeeLogoutView,name='employee-logout'),
]