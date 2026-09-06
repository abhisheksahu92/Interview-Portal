"""RSS feed of the network's open roles."""

from django.contrib.syndication.views import Feed
from django.urls import reverse

from board.services import network_jobs


class BoardFeed(Feed):
    title = "Open roles on the job network"
    description = "Newest open roles across every company listing on the network."
    link = "/jobs/board/"

    def items(self):
        return network_jobs()[:50]

    def item_title(self, item):
        return f"{item.title} · {item.company.name}"

    def item_description(self, item):
        return (item.description or "")[:600]

    def item_link(self, item):
        return reverse("board:job_detail", args=[item.pk])

    def item_pubdate(self, item):
        return item.created_at
