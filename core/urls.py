from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.account_home, name="account_home"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("signup/", views.candidate_signup, name="candidate_signup"),
    path("signup/company/", views.company_signup, name="company_signup"),
    path(
        "invite/<str:token>/",
        views.invite_accept,
        name="invite_accept",
    ),
    path("switch-company/", views.switch_company, name="switch_company"),
]
