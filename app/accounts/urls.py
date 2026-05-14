from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("2fa/verify/", views.two_factor_verify, name="two_factor_verify"),
    path("2fa/setup/", views.two_factor_setup, name="two_factor_setup"),
    path("2fa/recovery/", views.recovery_login, name="recovery_login"),
    path("2fa/codes/", views.recovery_codes, name="recovery_codes"),
]
