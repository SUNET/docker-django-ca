"""
Django management command: provision_acme_account
=================================================
Inserts a pre-generated ACME account into django-ca's database.

Reads the public key PEM from stdin (as produced by generate_acme_key.py),
derives the JWK thumbprint and slug from it, then creates an AcmeAccount record.

Usage
-----
  python generate_acme_key.py \
      --server https://ca.example.com/django_ca/acme/directory/ABCDEF/ \
    | python manage.py provision_acme_account --ca-serial ABCDEF
"""

import base64
import hashlib
import json
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.backends import default_backend

from django_ca.models import AcmeAccount, CertificateAuthority


def thumbprint_from_public_key(public_key) -> str:
    """Compute the RFC 7638 JWK thumbprint from a public key object."""
    pub_numbers = public_key.public_numbers()

    def int_to_base64url(n: int) -> str:
        length = (n.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

    canonical = json.dumps(
        {
            "e": int_to_base64url(pub_numbers.e),
            "kty": "RSA",
            "n": int_to_base64url(pub_numbers.n),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Pre-provision a certbot ACME account in django-ca from a public key on stdin."

    def add_arguments(self, parser):
        parser.add_argument("--ca-serial", required=True,
                            help="Serial of the target CA (colons optional)")
        parser.add_argument("--email", default="",
                            help="Contact email for the ACME account")

    def handle(self, *args, **options):
        pem_data = sys.stdin.read().strip()
        if not pem_data:
            raise CommandError("No public key PEM received on stdin.")

        public_key = load_pem_public_key(pem_data.encode(), backend=default_backend())
        thumbprint = thumbprint_from_public_key(public_key)
        slug = thumbprint[:22]
        self.stdout.write(f"  Thumbprint : {thumbprint}")
        self.stdout.write(f"  Slug       : {slug}")

        ca_serial = options["ca_serial"].replace(":", "")
        try:
            ca = CertificateAuthority.objects.get(serial__icontains=ca_serial)
        except CertificateAuthority.DoesNotExist:
            raise CommandError(f"CA not found for serial: {ca_serial}")

        if AcmeAccount.objects.filter(thumbprint=thumbprint, ca=ca).exists():
            self.stdout.write(self.style.WARNING(
                "Account with this thumbprint already exists — skipping."
            ))
            return

        acme_url = "https://" + settings.CA_DEFAULT_HOSTNAME
        serial_no_colons = ca.serial.replace(":", "").upper()
        kid = acme_url.rstrip("/") + "/django_ca/acme/" + serial_no_colons + "/acct/" + slug + "/"

        email = options["email"]
        account = AcmeAccount(
            ca=ca,
            pem=pem_data.strip(),
            thumbprint=thumbprint,
            contact="mailto:" + email if email else "",
            status="valid",
            terms_of_service_agreed=True,
            slug=slug,
            kid=kid,
        )
        account.save()

        self.stdout.write(self.style.SUCCESS(f"OK — kid: {account.kid}"))
