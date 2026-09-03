from django.urls import path

from offers import views

app_name = "offers"

urlpatterns = [
    path("", views.index, name="index"),
    path("mine/", views.my_offers, name="mine"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/preview/", views.template_preview, name="template_preview"),
    path("templates/<int:pk>/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("new/<int:application_id>/", views.offer_create, name="create"),
    path("new/<int:application_id>/preview/", views.offer_preview, name="offer_preview"),
    path("sign/<str:token>/", views.sign, name="sign"),
    path("sign/<str:token>/accept/", views.sign_accept, name="sign_accept"),
    path("sign/<str:token>/decline/", views.sign_decline, name="sign_decline"),
    path("sign/<str:token>/pdf/", views.sign_pdf, name="sign_pdf"),
    path("<int:pk>/", views.offer_detail, name="detail"),
    path("<int:pk>/send/", views.offer_send, name="send"),
    path("<int:pk>/resend/", views.offer_resend, name="resend"),
    path("<int:pk>/withdraw/", views.offer_withdraw, name="withdraw"),
    path("<int:pk>/pdf/", views.offer_pdf, name="pdf"),
]
