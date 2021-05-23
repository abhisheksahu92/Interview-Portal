from django.urls import path
from . import views

app_name = 'employee'
urlpatterns = [
    path('',views.employeeIndexView,name='employee-index'),
    path('profile/',views.employeeProfileView,name='employee-profile'),
    path('selected/',views.employeeSelected,name='employee-selected'),
    path('rejected/',views.employeeRejected,name='employee-rejected'),
    path('list/?page=n',views.employeeListView,name='employee-list'),
    path('signup/',views.employeeSignupView,name='employee-signup'),
    path('feedback/<int:id>/',views.employeeFeedback,name='employee-feedback'),
    path('login/',views.employeeLoginView,name='employee-login'),
    path('logout/',views.employeeLogoutView,name='employee-logout'),
    # path('edit/<int:pk>',EditPhoneView.as_view(),name='phone-edit'),
    # path('delete/<int:pk>',DeletePhoneView.as_view(),name='phone-delete'),
    # path('add-call/<int:pk>',call_add,name='phone-call-add'),
    # path('show-call/<int:pk>',call_list,name='phone-call-show'),
    # path('edit-call/<int:pk>',call_edit,name='phone-call-edit'),
    # path('delete-call/<int:pk>',call_delete,name='phone-call-delete'),
    # path('search/', FilterView.as_view(filterset_class=PhoneFilter,template_name='phone/search.html'), name='search'),
]