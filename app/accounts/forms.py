from django import forms


class LoginForm(forms.Form):
    email = forms.CharField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class TOTPCodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "pattern": r"\d{6}",
            "autofocus": True,
        }),
    )


class RecoveryCodeForm(forms.Form):
    code = forms.CharField(
        label="Recovery code",
        max_length=40,
        widget=forms.TextInput(attrs={
            "autocomplete": "one-time-code",
            "autofocus": True,
            "placeholder": "xxxx-xxxx",
        }),
    )
