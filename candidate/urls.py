from django.urls import path
from .views import candidateProfileView,\
    CandidateIndexView,\
    candidateSignupView,\
    candidateLoginView,\
    candidateLogoutView

app_name = 'candidate'
urlpatterns = [
    path('',CandidateIndexView.as_view(),name='candidate-index'),
    path('profile/',candidateProfileView,name='candidate-profile'),
    path('signup/',candidateSignupView,name='candidate-signup'),
    path('login/',candidateLoginView,name='candidate-login'),
    path('logout/',candidateLogoutView,name='candidate-logout'),
    # path('edit/<int:pk>',EditPhoneView.as_view(),name='phone-edit'),
    # path('delete/<int:pk>',DeletePhoneView.as_view(),name='phone-delete'),
    # path('add-call/<int:pk>',call_add,name='phone-call-add'),
    # path('show-call/<int:pk>',call_list,name='phone-call-show'),
    # path('edit-call/<int:pk>',call_edit,name='phone-call-edit'),
    # path('delete-call/<int:pk>',call_delete,name='phone-call-delete'),
    # path('search/', FilterView.as_view(filterset_class=PhoneFilter,template_name='phone/search.html'), name='search'),
]