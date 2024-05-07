from django.urls import path
from .views import candidateProfileView,\
    candidateIndexView,\
    candidateSignupView,\
    candidateLoginView,\
    candidateLogoutView, \
    candidateUpdateView, \
    candidateAssessmentView

app_name = 'candidate'
urlpatterns = [
    path('',candidateIndexView,name='candidate-index'),
    path('assessment/',candidateAssessmentView,name='candidate-assessment'),
    path('profile/',candidateProfileView,name='candidate-profile'),
    path('signup/',candidateSignupView,name='candidate-signup'),
    path('login/',candidateLoginView,name='candidate-login'),
    path('logout/',candidateLogoutView,name='candidate-logout'),
    path('edit/<int:pk>',candidateUpdateView,name='candidate-edit'),
]