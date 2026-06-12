from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Delete expired and used MagicLinkTokens older than 7 days.'

    def handle(self, *args, **options):
        from client_hub.models import MagicLinkToken

        cutoff = timezone.now() - timedelta(days=7)
        expired = MagicLinkToken.objects.filter(expires_at__lt=cutoff).delete()
        used = MagicLinkToken.objects.filter(used_at__lt=cutoff).delete()
        self.stdout.write(f'Deleted {expired[0]} expired and {used[0]} used tokens.')
