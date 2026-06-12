import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def generate_magic_link_token(customer):
    """
    Invalidate any existing unused tokens for this customer, then create a new one.
    Returns the token string.
    """
    from .models import MagicLinkToken

    MagicLinkToken.objects.filter(
        customer=customer,
        used_at__isnull=True,
    ).update(expires_at=timezone.now())

    token_string = secrets.token_urlsafe(32)
    expiry = timezone.now() + timedelta(
        seconds=getattr(settings, 'MAGIC_LINK_EXPIRY_SECONDS', 1200)
    )
    MagicLinkToken.objects.create(
        customer=customer,
        token=token_string,
        expires_at=expiry,
    )
    return token_string


def validate_magic_link_token(token_string):
    """
    Returns the Customer if the token is valid, None otherwise.
    Marks the token as used on success.
    """
    from .models import MagicLinkToken

    try:
        token = MagicLinkToken.objects.select_related('customer').get(
            token=token_string,
            used_at__isnull=True,
        )
    except MagicLinkToken.DoesNotExist:
        return None

    if not token.is_valid:
        return None

    token.used_at = timezone.now()
    token.save(update_fields=['used_at'])
    return token.customer
