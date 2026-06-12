from django import forms

from .models import WorkRequest, ServicePlanChangeRequest


class LoginForm(forms.Form):
    email = forms.EmailField(label='Your email address')


class ProfileEditForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    phone = forms.CharField(max_length=40, required=False)
    new_email = forms.EmailField(
        required=False,
        label='New email address (leave blank to keep current)',
    )


class WorkRequestForm(forms.Form):
    request_types = forms.MultipleChoiceField(
        choices=WorkRequest.RequestType.choices,
        widget=forms.CheckboxSelectMultiple,
        label='What type of work are you requesting?',
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5}),
        label='Please describe what you need',
    )
    contact_name = forms.CharField(max_length=200)
    contact_email = forms.EmailField()
    contact_phone = forms.CharField(max_length=40, required=False)
    preferred_contact = forms.ChoiceField(
        choices=[('email', 'Email'), ('phone', 'Phone')],
        widget=forms.RadioSelect,
        initial='email',
    )

    def __init__(self, *args, customer=None, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        if properties is not None and properties.count() > 1:
            from jobs.models import Property
            self.fields['property'] = forms.ModelChoiceField(
                queryset=properties,
                empty_label=None,
                label='Property',
            )
            # Move property to the front
            field_order = ['property'] + [k for k in self.fields if k != 'property']
            self.fields = {k: self.fields[k] for k in field_order}


class ServicePlanChangeForm(forms.Form):
    from jobs.models import ServiceTier

    TIER_CHOICES = [
        (ServiceTier.BASIC, ServiceTier.BASIC.label),
        (ServiceTier.STANDARD, ServiceTier.STANDARD.label),
        (ServiceTier.PREMIUM, ServiceTier.PREMIUM.label),
    ]

    request_type = forms.ChoiceField(
        choices=ServicePlanChangeRequest.RequestType.choices,
        label='What would you like to do?',
    )
    requested_tier = forms.ChoiceField(
        choices=[('', '— select a plan —')] + TIER_CHOICES,
        required=False,
        label='New plan',
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Reason (required for cancellations)',
    )

    def clean(self):
        cleaned = super().clean()
        request_type = cleaned.get('request_type')
        reason = cleaned.get('reason', '').strip()
        requested_tier = cleaned.get('requested_tier', '')

        if request_type == ServicePlanChangeRequest.RequestType.CANCEL and not reason:
            self.add_error('reason', 'Please tell us why you want to cancel.')

        if request_type in (
            ServicePlanChangeRequest.RequestType.UPGRADE,
            ServicePlanChangeRequest.RequestType.DOWNGRADE,
        ) and not requested_tier:
            self.add_error('requested_tier', 'Please select the plan you want.')

        return cleaned


class AccountClosureForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label='I understand this will initiate a staff-reviewed account closure process',
    )
