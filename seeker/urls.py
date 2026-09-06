from django.urls import path

from seeker import views

app_name = "seeker"

urlpatterns = [
    path("", views.feed, name="feed"),
    path("save/<str:kind>/<int:pk>/", views.save, name="save"),
    path("saved/", views.saved, name="saved"),
    path("saved/bulk/", views.bulk, name="bulk"),
    path("compose/", views.compose, name="compose"),
    path("mailbox/", views.mailbox, name="mailbox"),
    path("mailbox/preferences/", views.preferences, name="preferences"),
    path("mailbox/disconnect/", views.mailbox_disconnect, name="mailbox_disconnect"),
    path("mailbox/gmail/", views.gmail_connect, name="gmail_connect"),
    path("mailbox/gmail/callback/", views.gmail_callback, name="gmail_callback"),
    path("add/", views.add_lead, name="add_lead"),
    path("upgrade/", views.upgrade, name="upgrade"),
]
