from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from client_credentials.models import (
    CredentialAccessLog,
    CredentialDeletionRequest,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)
from jobs.models import Customer, Property

from .auth import generate_magic_link_token, validate_magic_link_token
from .decorators import customer_login_required
from .emails import (
    send_account_closure_confirmation,
    send_account_closure_notification,
    send_email_change_confirmation,
    send_email_change_notification,
    send_magic_link,
    send_plan_change_confirmation,
    send_plan_change_notification,
    send_work_request_confirmation,
    send_work_request_notification,
)
from .forms import (
    AccountClosureForm,
    LoginForm,
    ProfileEditForm,
    ServicePlanChangeForm,
    WorkRequestForm,
)
from .models import MagicLinkToken, ServicePlanChangeRequest, WorkRequest


def _get_system_user():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    system_user_id = getattr(settings, 'SYSTEM_USER_ID', None)
    if system_user_id:
        return User.objects.filter(pk=system_user_id).first()
    return User.objects.filter(username='system').first()


# ── Auth views ────────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            customer = Customer.objects.filter(email=email).first()
            if customer:
                # Rate limit: don't generate a new token if one was created in the last 60 s
                recent = MagicLinkToken.objects.filter(
                    customer=customer,
                    used_at__isnull=True,
                    created_at__gte=timezone.now() - timedelta(seconds=60),
                ).exists()
                if not recent:
                    token = generate_magic_link_token(customer)
                    send_magic_link(customer, token, request)
            # Always redirect to login_sent — never reveal whether an email was found.
            return redirect('client_hub:login_sent')
    else:
        form = LoginForm()
    return render(request, 'client_hub/login.html', {'form': form})


def login_sent(request):
    return render(request, 'client_hub/login_sent.html')


def login_verify(request, token):
    customer = validate_magic_link_token(token)
    if customer is None:
        return render(request, 'client_hub/login_verify.html', {'error': True})
    request.session['customer_id'] = customer.id
    request.session.set_expiry(60 * 60 * 24 * 30)
    return redirect('client_hub:dashboard')


@require_POST
@customer_login_required
def logout_view(request):
    request.session.flush()
    return redirect('client_hub:login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@customer_login_required
def dashboard(request):
    properties = Property.objects.filter(
        customer=request.customer
    ).prefetch_related('installed_systems')
    return render(request, 'client_hub/dashboard.html', {
        'properties': properties,
    })


# ── Property and credential views ─────────────────────────────────────────────

@customer_login_required
def property_detail(request, pk):
    prop = get_object_or_404(Property, pk=pk, customer=request.customer)
    systems = InstalledSystem.objects.filter(property=prop, is_visible=True)
    return render(request, 'client_hub/property_detail.html', {
        'property': prop,
        'systems': systems,
    })


@customer_login_required
def system_detail(request, pk):
    system = get_object_or_404(
        InstalledSystem, pk=pk, property__customer=request.customer, is_visible=True
    )
    credentials = SystemCredential.objects.filter(system=system, is_visible=True)
    from client_credentials.models import Device
    devices = Device.objects.filter(
        system=system, is_visible=True
    ).prefetch_related('credentials')
    return render(request, 'client_hub/system_detail.html', {
        'system': system,
        'credentials': credentials,
        'devices': devices,
    })


def _log_credential_access(request, obj):
    user = getattr(request.customer, 'user', None) or _get_system_user()
    ct = ContentType.objects.get_for_model(obj)
    CredentialAccessLog.objects.create(
        accessed_by=user,
        content_type=ct,
        object_id=obj.pk,
        action='viewed_by_customer',
    )


@customer_login_required
def system_credential_detail(request, pk):
    cred = get_object_or_404(
        SystemCredential,
        pk=pk,
        system__property__customer=request.customer,
        is_visible=True,
    )
    _log_credential_access(request, cred)
    response = render(request, 'client_hub/credential_detail.html', {
        'credential': cred,
        'credential_type': 'system',
        'accessed_at': timezone.now(),
    })
    response['Cache-Control'] = 'no-store'
    return response


@customer_login_required
def device_credential_detail(request, pk):
    cred = get_object_or_404(
        DeviceCredential,
        pk=pk,
        device__system__property__customer=request.customer,
        is_visible=True,
    )
    _log_credential_access(request, cred)
    response = render(request, 'client_hub/credential_detail.html', {
        'credential': cred,
        'credential_type': 'device',
        'accessed_at': timezone.now(),
    })
    response['Cache-Control'] = 'no-store'
    return response


# ── Profile ───────────────────────────────────────────────────────────────────

@customer_login_required
def profile_edit(request):
    customer = request.customer
    message = None

    if request.method == 'POST':
        form = ProfileEditForm(request.POST)
        if form.is_valid():
            customer.first_name = form.cleaned_data['first_name']
            customer.last_name = form.cleaned_data['last_name']
            customer.phone = form.cleaned_data['phone']
            customer.save(update_fields=['first_name', 'last_name', 'phone', 'updated_at'])

            new_email = form.cleaned_data.get('new_email', '').strip()
            if new_email and new_email != customer.email:
                if Customer.objects.filter(email=new_email).exclude(pk=customer.pk).exists():
                    form.add_error('new_email', 'That email address is already in use.')
                else:
                    token = signing.dumps({'customer_id': customer.id, 'new_email': new_email})
                    confirm_url = request.build_absolute_uri(
                        f'/profile/email-confirm/{token}/'
                    )
                    request.session['pending_email'] = new_email
                    send_email_change_confirmation(customer, new_email, confirm_url)
                    send_email_change_notification(customer, new_email)
                    message = 'Profile updated. Check your new email address for a confirmation link.'
            else:
                message = 'Profile updated.'
    else:
        form = ProfileEditForm(initial={
            'first_name': customer.first_name,
            'last_name': customer.last_name,
            'phone': customer.phone,
        })

    return render(request, 'client_hub/profile_edit.html', {
        'form': form,
        'message': message,
    })


def email_change_confirm(request, token):
    try:
        payload = signing.loads(token, max_age=86400)
    except signing.BadSignature:
        return render(request, 'client_hub/email_change_confirm.html', {'error': True})

    customer_id = payload.get('customer_id')
    new_email = payload.get('new_email')
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return render(request, 'client_hub/email_change_confirm.html', {'error': True})

    customer.email = new_email
    customer.save(update_fields=['email', 'updated_at'])

    if 'pending_email' in request.session:
        del request.session['pending_email']

    # Log the customer out so they re-authenticate with the new address.
    request.session.flush()
    return render(request, 'client_hub/email_change_confirm.html', {'success': True})


# ── Work request ──────────────────────────────────────────────────────────────

@customer_login_required
def work_request_form(request):
    customer = request.customer
    properties = Property.objects.filter(customer=customer)

    if request.method == 'POST':
        form = WorkRequestForm(request.POST, customer=customer, properties=properties)
        if form.is_valid():
            cd = form.cleaned_data

            if properties.count() > 1:
                prop = cd.get('property')
            else:
                prop = properties.first()

            wr = WorkRequest.objects.create(
                customer=customer,
                property=prop,
                request_types=','.join(cd['request_types']),
                description=cd['description'],
                contact_name=cd['contact_name'],
                contact_email=cd['contact_email'],
                contact_phone=cd.get('contact_phone', ''),
                preferred_contact=cd['preferred_contact'],
                service_plan_tier=prop.service_plan_tier if prop else '',
                service_since=prop.created_at if prop else None,
            )
            send_work_request_notification(wr)
            send_work_request_confirmation(wr)
            return redirect('client_hub:work_request_success')
    else:
        form = WorkRequestForm(
            customer=customer,
            properties=properties,
            initial={
                'contact_name': f'{customer.first_name} {customer.last_name}'.strip(),
                'contact_email': customer.email,
                'contact_phone': customer.phone,
            },
        )

    return render(request, 'client_hub/work_request_form.html', {'form': form})


def work_request_success(request):
    return render(request, 'client_hub/work_request_success.html')


# ── Service plan change ───────────────────────────────────────────────────────

@customer_login_required
def service_plan_change(request, property_pk):
    prop = get_object_or_404(Property, pk=property_pk, customer=request.customer)

    if not prop.stripe_subscription_id:
        return redirect('client_hub:dashboard')

    if request.method == 'POST':
        form = ServicePlanChangeForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            pcr = ServicePlanChangeRequest.objects.create(
                customer=request.customer,
                property=prop,
                request_type=cd['request_type'],
                current_tier=prop.service_plan_tier,
                requested_tier=cd.get('requested_tier', ''),
                reason=cd.get('reason', ''),
            )
            send_plan_change_notification(pcr)
            send_plan_change_confirmation(pcr)
            return redirect('client_hub:service_plan_change_success')
    else:
        form = ServicePlanChangeForm()

    return render(request, 'client_hub/service_plan_change_form.html', {
        'form': form,
        'property': prop,
    })


def service_plan_change_success(request):
    return render(request, 'client_hub/service_plan_change_success.html')


# ── Account closure ───────────────────────────────────────────────────────────

@customer_login_required
def account_closure(request):
    customer = request.customer

    if request.method == 'POST':
        form = AccountClosureForm(request.POST)
        if form.is_valid():
            dr = CredentialDeletionRequest.objects.create(
                customer=customer,
                requested_by=f'{customer.first_name} {customer.last_name} (via Client Hub)',
                scope_notes='Account closure request — full data deletion and access revocation',
                status=CredentialDeletionRequest.Status.PENDING,
            )
            send_account_closure_notification(customer, dr)
            send_account_closure_confirmation(customer)
            return redirect('client_hub:account_closure_success')
    else:
        form = AccountClosureForm()

    return render(request, 'client_hub/account_closure_form.html', {'form': form})


def account_closure_success(request):
    return render(request, 'client_hub/account_closure_success.html')
