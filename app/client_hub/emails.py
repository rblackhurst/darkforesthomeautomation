from django.conf import settings
from django.core.mail import send_mail


def send_magic_link(customer, token, request):
    verify_url = request.build_absolute_uri(
        f'/login/verify/{token}/'
    )
    send_mail(
        subject='Your Dark Forest Home Automation login link',
        message=(
            f'Hi {customer.first_name},\n\n'
            f'Click the link below to log in to your Client Hub. '
            f'This link expires in 20 minutes.\n\n'
            f'{verify_url}\n\n'
            f'If you did not request this link, you can safely ignore this email.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer.email],
    )


def send_work_request_notification(work_request):
    send_mail(
        subject=f'New work request from {work_request.customer}',
        message=(
            f'A new work request has been submitted.\n\n'
            f'Customer: {work_request.customer}\n'
            f'Type(s): {work_request.get_request_types_display()}\n'
            f'Preferred contact: {work_request.preferred_contact}\n'
            f'Contact name: {work_request.contact_name}\n'
            f'Contact email: {work_request.contact_email}\n'
            f'Contact phone: {work_request.contact_phone or "—"}\n'
            f'Service tier: {work_request.service_plan_tier or "—"}\n\n'
            f'Description:\n{work_request.description}\n\n'
            f'Review at: /admin/client_hub/workrequest/'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.STAFF_NOTIFICATION_EMAIL],
    )


def send_work_request_confirmation(work_request):
    send_mail(
        subject='We received your work request',
        message=(
            f'Hi {work_request.contact_name},\n\n'
            f'We received your work request and will be in touch soon.\n\n'
            f'Request type(s): {work_request.get_request_types_display()}\n'
            f'We will contact you by: {work_request.preferred_contact}\n\n'
            f'If you have questions, reply to this email or call us.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[work_request.contact_email],
    )


def send_plan_change_notification(plan_change_request):
    send_mail(
        subject=f'Service plan change request from {plan_change_request.customer}',
        message=(
            f'A service plan change request has been submitted.\n\n'
            f'Customer: {plan_change_request.customer}\n'
            f'Property: {plan_change_request.property}\n'
            f'Request type: {plan_change_request.get_request_type_display()}\n'
            f'Current tier: {plan_change_request.current_tier or "—"}\n'
            f'Requested tier: {plan_change_request.requested_tier or "—"}\n\n'
            f'Reason:\n{plan_change_request.reason or "(none provided)"}\n\n'
            f'Review at: /admin/client_hub/serviceplanchangerequest/'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.STAFF_NOTIFICATION_EMAIL],
    )


def send_plan_change_confirmation(plan_change_request):
    send_mail(
        subject='We received your service plan change request',
        message=(
            f'Hi {plan_change_request.customer.first_name},\n\n'
            f'We received your request to {plan_change_request.get_request_type_display().lower()} '
            f'your service plan. A team member will review it and be in touch soon.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[plan_change_request.customer.email],
    )


def send_email_change_confirmation(customer, new_email, confirm_url):
    send_mail(
        subject='Confirm your new email address — Dark Forest Home Automation',
        message=(
            f'Hi {customer.first_name},\n\n'
            f'Click the link below to confirm your new email address. '
            f'This link expires in 24 hours.\n\n'
            f'{confirm_url}\n\n'
            f'If you did not request this change, you can safely ignore this email.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[new_email],
    )


def send_email_change_notification(customer, new_email):
    send_mail(
        subject='Your email address change request — Dark Forest Home Automation',
        message=(
            f'Hi {customer.first_name},\n\n'
            f'A request was made to change the email address on your Dark Forest '
            f'Home Automation account to: {new_email}\n\n'
            f'If you made this request, no action is needed. '
            f'If you did not make this request, please contact us immediately.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer.email],
    )


def send_account_closure_notification(customer, deletion_request):
    send_mail(
        subject=f'Account closure request from {customer}',
        message=(
            f'An account closure request has been submitted via the Client Hub.\n\n'
            f'Customer: {customer}\n'
            f'Email: {customer.email}\n'
            f'Request ID: {deletion_request.pk}\n\n'
            f'Review at: /admin/client_credentials/credentialdeletionrequest/'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.STAFF_NOTIFICATION_EMAIL],
    )


def send_account_closure_confirmation(customer):
    send_mail(
        subject='We received your account closure request',
        message=(
            f'Hi {customer.first_name},\n\n'
            f'We received your account closure request. A team member will review it '
            f'and contact you to confirm next steps.\n\n'
            f'As a reminder: all of your credential data belongs to you. '
            f'You can request a full copy at any time.\n\n'
            f'Dark Forest Home Automation'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[customer.email],
    )
