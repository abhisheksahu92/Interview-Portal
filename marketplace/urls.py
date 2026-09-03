from django.urls import path

from marketplace import views

app_name = "marketplace"

urlpatterns = [
    path("", views.index, name="index"),
    path("purchases/", views.purchases, name="purchases"),
    path("pool/", views.pool, name="pool"),
    path("pool/opt-in/", views.pool_opt_in, name="pool_opt_in"),
    path("pool/<int:profile_id>/invite/", views.pool_invite, name="pool_invite"),
    path("packs/<slug:slug>/", views.pack_detail, name="pack_detail"),
    path("packs/<slug:slug>/install/", views.pack_install, name="pack_install"),
]
