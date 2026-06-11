from django.urls import path

from . import views

app_name = 'client_credentials'

urlpatterns = [
    path('system-credential/<int:pk>/', views.system_credential_detail, name='system_credential_detail'),
    path('device-credential/<int:pk>/', views.device_credential_detail, name='device_credential_detail'),
]
