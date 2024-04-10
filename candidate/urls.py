from django.urls import path
from .views import candidateProfileView,\
    candidateIndexView,\
    candidateSignupView,\
    candidateLoginView,\
    candidateLogoutView

app_name = 'candidate'
urlpatterns = [
    path('',candidateIndexView,name='candidate-index'),
    path('profile/',candidateProfileView,name='candidate-profile'),
    path('signup/',candidateSignupView,name='candidate-signup'),
    path('login/',candidateLoginView,name='candidate-login'),
    path('logout/',candidateLogoutView,name='candidate-logout'),
]