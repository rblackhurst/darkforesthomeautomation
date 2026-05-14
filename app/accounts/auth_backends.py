from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate by email or username, case-insensitively.

    Default Django usernames are unique but case-sensitive at the DB level,
    so `Ron` and `ron` can both exist. We resolve that ambiguity by:
      1. Matching `email iexact OR username iexact` in a single query.
      2. Preferring an exact-case hit if both are present.
      3. Trying each remaining candidate's password — first success wins.

    This means an existing username-based superuser (e.g. created via
    `createsuperuser` with no email) can still log in with their username,
    and any duplicate accounts won't crash login.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        User = get_user_model()
        ident = username.strip()

        candidates = list(
            User.objects.filter(
                Q(email__iexact=ident) | Q(username__iexact=ident),
            )
        )
        # Try exact-case matches before case-insensitive ones, but still try
        # *every* candidate's password — the right user is whichever account
        # the password unlocks.
        candidates.sort(
            key=lambda u: 0 if (u.email == ident or u.username == ident) else 1,
        )

        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        if not candidates:
            # Run the default hasher anyway so timing doesn't leak which
            # accounts exist.
            User().set_password(password)
        return None
