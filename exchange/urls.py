from django.urls import path

from exchange import views

app_name = "exchange"

urlpatterns = [
    path("", views.index, name="index"),
    path("publish/", views.publish, name="publish"),
    path("requirements/", views.requirements, name="requirements"),
    path("requirements/<int:pk>/", views.requirement_detail, name="requirement_detail"),
    path("requirements/<int:pk>/close/", views.requirement_close, name="requirement_close"),
    path("requirements/<int:pk>/submit/", views.submit, name="submit"),
    path("submissions/", views.submissions, name="submissions"),
    path("submissions/<int:pk>/shortlist/", views.submission_shortlist, name="submission_shortlist"),
    path("submissions/<int:pk>/reject/", views.submission_reject, name="submission_reject"),
    path("submissions/<int:pk>/reveal/", views.submission_reveal, name="submission_reveal"),
    path("submissions/<int:pk>/hire/", views.submission_hire, name="submission_hire"),
    path("partners/", views.partners, name="partners"),
    path("partners/<int:pk>/accept/", views.partner_accept, name="partner_accept"),
    path("partners/<int:pk>/block/", views.partner_block, name="partner_block"),
    path("partners/<int:pk>/unblock/", views.partner_unblock, name="partner_unblock"),
    path("deals/", views.deals, name="deals"),
    path("deals/<int:pk>/dispute/", views.deal_dispute, name="deal_dispute"),
]
