"""Flip video-screen invites past their deadline to EXPIRED."""

from django.core.management.base import BaseCommand

from video.services import expire_stale_invites


class Command(BaseCommand):
    help = "Expire video-screen invites whose deadline has passed."

    def handle(self, *args, **options):
        count = expire_stale_invites()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} video invite(s)."))
        return count
