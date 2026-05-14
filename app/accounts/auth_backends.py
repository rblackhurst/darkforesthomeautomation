from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate by email (case-insensitive) first, then by username.

    Lets staff log in with the email address shown on their account without
    forcing existing username-based superusers (e.g. the one created by
    `manage.py createsuperuser`) to change anything.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        User = get_user_model()
        ident = username.strip()

        try:
            user = User.objects.get(email__iexact=ident)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username__iexact=ident)
            except User.DoesNotExist:
                # Run the default hasher anyway so timing doesn't leak which
                # accounts exist.
                User().set_password(password)
                return None
        except User.MultipleObjectsReturned:
            # Email collisions shouldn't happen in practice (3–4 employees)
            # but if they do, fall back to username lookup to disambiguate.
            try:
                user = User.objects.get(username__iexact=ident)
            except User.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
