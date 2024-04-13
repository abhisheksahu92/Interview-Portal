from django.urls import path
from . import views
from django_filters.views import FilterView
from .filters import CandidateFilter

app_name = 'dashboard'
urlpatterns = [
    path('',views.dashboardIndexView,name='dashboard-index'),
    path('selected',views.dashboardSelectedView,name='dashboard-selected'),
    path('rejected',views.dashboardRejectedView,name='dashboard-rejected'),
    path('candidates',views.dashboardCandidatesView,name='dashboard-candidates'),
    path('search/', FilterView.as_view(filterset_class=CandidateFilter,template_name='dashboard/search.html'), name='search'),
    # path('profile/',views.employeeProfileView,name='employee-profile'),
    # path('selected/',views.employeeSelected,name='employee-selected'),
    # path('rejected/',views.employeeRejected,name='employee-rejected'),
    # path('list/?page=n',views.employeeListView,name='employee-list'),
    # path('signup/',views.employeeSignupView,name='employee-signup'),
    # path('feedback/<int:id>/',views.employeeFeedback,name='employee-feedback'),
    # path('login/',views.employeeLoginView,name='employee-login'),
    # path('logout/',views.employeeLogoutView,name='employee-logout'),
]