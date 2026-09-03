"""Generate a fresh Ed25519 licence-signing keypair.

Print the private key once and store it in a secrets manager as
``LICENSE_SIGNING_KEY``; paste the public key into
``partners.licensing.LICENSE_PUBLIC_KEY`` and ship it with every install.
"""

from django.core.management.base import BaseCommand

from partners.licensing import generate_keypair


class Command(BaseCommand):
    help = "Generate an Ed25519 licence-signing keypair (private + public, base64)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet-private",
            action="store_true",
            help="Print only the public key (private key withheld).",
        )

    def handle(self, *args, **options):
        private, public = generate_keypair()
        self.stdout.write(self.style.SUCCESS(f"LICENSE_PUBLIC_KEY = {public!r}"))
        if options["quiet_private"]:
            self.stdout.write("Private key withheld (--quiet-private).")
            return public
        self.stdout.write("")
        self.stdout.write(f"LICENSE_SIGNING_KEY={private}")
        self.stdout.write(
            self.style.WARNING(
                "Store the private key in your secrets manager. Never commit it."
            )
        )
        return public
