"""Employee login + TOTP 2FA.

Two-step login flow:
  1. POST /accounts/login/ — email + password. On success, stash the candidate
     user's id in the session as `pending_user_id` and redirect to the 2FA
     step. The user is NOT yet logged in (Django's request.user stays
     anonymous).
  2. /accounts/2fa/verify/ — TOTP code. On success, call `login()` and
     redirect home. If the user has no confirmed TOTP yet, redirect through
     /accounts/2fa/setup/ first.

A separate /accounts/2fa/recovery/ accepts a one-time recovery code in place
of the TOTP code, and revokes that code on use.
"""

import base64
import io

import segno
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, RecoveryCodeForm, TOTPCodeForm
from .models import EmployeeTOTP, RecoveryCode

PENDING_USER_KEY = "pending_user_id"
RECOVERY_CODES_KEY = "fresh_recovery_codes"


def _safe_next(request, default="/"):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    # Only allow same-origin relative paths.
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return default


def _get_pending_user(request):
    uid = request.session.get(PENDING_USER_KEY)
    if not uid:
        return None
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        return User.objects.get(pk=uid, is_active=True)
    except User.DoesNotExist:
        return None


def _qr_data_uri(provisioning_uri):
    """Inline SVG QR as a data: URI — no static-file plumbing needed."""
    buf = io.BytesIO()
    segno.make(provisioning_uri, error="m").save(buf, kind="svg", scale=5, border=2)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, default=reverse("jobs:home")))

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        if user is None:
            messages.error(request, "That email and password didn't match.")
        else:
            # Park the candidate user in the session — don't call login()
            # until 2FA is satisfied (or enrolment is complete).
            request.session[PENDING_USER_KEY] = user.pk
            request.session["pending_next"] = _safe_next(
                request, default=reverse("jobs:home"),
            )
            return redirect("accounts:two_factor_verify")

    return render(request, "accounts/login.html", {
        "form": form,
        "next": _safe_next(request, default=""),
    })


@never_cache
@require_http_methods(["GET", "POST"])
def two_factor_verify(request):
    user = _get_pending_user(request)
    if user is None:
        return redirect("accounts:login")

    totp = EmployeeTOTP.objects.filter(user=user).first()
    if totp is None or not totp.is_confirmed:
        # First-time login: send the user through enrolment instead.
        return redirect("accounts:two_factor_setup")

    form = TOTPCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if totp.verify(form.cleaned_data["code"]):
            return _complete_login(request, user)
        messages.error(request, "That code didn't match. Try the next one your app shows.")

    return render(request, "accounts/totp_verify.html", {
        "form": form,
        "user_email": user.email or user.get_username(),
    })


@never_cache
@require_http_methods(["GET", "POST"])
def two_factor_setup(request):
    """Enrol the pending (or already-logged-in) user in TOTP.

    Reachable in two situations:
      - Right after first password login (pending session).
      - When a logged-in user resets / re-enrols their device (?reset=1).
    """
    user = _get_pending_user(request) or (
        request.user if request.user.is_authenticated else None
    )
    if user is None:
        return redirect("accounts:login")

    totp, _ = EmployeeTOTP.objects.get_or_create(user=user)
    if request.GET.get("reset") == "1" and totp.is_confirmed:
        # Re-enrolment: rotate the secret and invalidate the confirmation.
        from .models import _new_totp_secret
        totp.secret = _new_totp_secret()
        totp.confirmed_at = None
        totp.last_used_counter = 0
        totp.save()

    form = TOTPCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if totp.verify(form.cleaned_data["code"]):
            totp.confirmed_at = now()
            totp.save(update_fields=["confirmed_at", "updated_at"])
            plain_codes = RecoveryCode.generate_batch(user)
            request.session[RECOVERY_CODES_KEY] = plain_codes
            if request.session.get(PENDING_USER_KEY):
                # First-time enrolment from the login flow — log them in now.
                _complete_login(request, user, redirect_to=reverse("accounts:recovery_codes"))
                return redirect("accounts:recovery_codes")
            return redirect("accounts:recovery_codes")
        messages.error(request, "That code didn't match. Check the time on your phone, then try again.")

    return render(request, "accounts/totp_setup.html", {
        "form": form,
        "qr_data_uri": _qr_data_uri(totp.provisioning_uri()),
        "secret": totp.secret,
        "user_email": user.email or user.get_username(),
    })


@never_cache
@require_http_methods(["GET", "POST"])
def recovery_login(request):
    """Trade a one-time recovery code for a logged-in session."""
    user = _get_pending_user(request)
    if user is None:
        return redirect("accounts:login")

    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if RecoveryCode.consume(user, form.cleaned_data["code"]):
            return _complete_login(request, user)
        messages.error(request, "That recovery code isn't valid (or has already been used).")

    return render(request, "accounts/recovery_login.html", {"form": form})


@login_required
def recovery_codes(request):
    """Show freshly-generated codes once.

    The plaintext codes only exist in the session until the user navigates
    away — refreshing this page after that clears them, by design.
    """
    codes = request.session.pop(RECOVERY_CODES_KEY, None)
    if not codes:
        messages.info(
            request,
            "Your recovery codes were already shown. Reset 2FA in your "
            "profile if you need a fresh set.",
        )
        return redirect("jobs:home")
    return render(request, "accounts/recovery_codes.html", {"codes": codes})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("accounts:login")
    return render(request, "accounts/logout_confirm.html")


def _complete_login(request, user, redirect_to=None):
    nxt = redirect_to or request.session.pop("pending_next", None) or reverse("jobs:home")
    request.session.pop(PENDING_USER_KEY, None)
    login(request, user, backend="accounts.auth_backends.EmailOrUsernameBackend")
    return HttpResponseRedirect(nxt)
