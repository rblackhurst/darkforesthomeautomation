from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import CredentialAccessLog, DeviceCredential, SystemCredential


@login_required
def system_credential_detail(request, pk):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    credential = get_object_or_404(SystemCredential, pk=pk)
    ct = ContentType.objects.get_for_model(SystemCredential)
    log_entry = CredentialAccessLog.objects.create(
        accessed_by=request.user,
        content_type=ct,
        object_id=pk,
        action='viewed',
    )

    response = render(request, 'client_credentials/system_credential_detail.html', {
        'credential': credential,
        'log_entry': log_entry,
    })
    response['Cache-Control'] = 'no-store'
    return response


@login_required
def device_credential_detail(request, pk):
    if not request.user.is_staff:
        return HttpResponseForbidden()

    credential = get_object_or_404(DeviceCredential, pk=pk)
    ct = ContentType.objects.get_for_model(DeviceCredential)
    log_entry = CredentialAccessLog.objects.create(
        accessed_by=request.user,
        content_type=ct,
        object_id=pk,
        action='viewed',
    )

    response = render(request, 'client_credentials/device_credential_detail.html', {
        'credential': credential,
        'log_entry': log_entry,
    })
    response['Cache-Control'] = 'no-store'
    return response
