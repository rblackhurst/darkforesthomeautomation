from django.urls import path

from . import views

app_name = 'client_hub'

urlpatterns = [
    # Auth
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('login/sent/', views.login_sent, name='login_sent'),
    path('login/verify/<str:token>/', views.login_verify, name='login_verify'),
    path('logout/', views.logout_view, name='logout'),

    # Profile
    path('profile/', views.profile_edit, name='profile_edit'),
    path('profile/email-confirm/<str:token>/', views.email_change_confirm, name='email_change_confirm'),

    # Properties and credentials
    path('property/<int:pk>/', views.property_detail, name='property_detail'),
    path('system/<int:pk>/', views.system_detail, name='system_detail'),
    path('credential/system/<int:pk>/', views.system_credential_detail, name='system_credential_detail'),
    path('credential/device/<int:pk>/', views.device_credential_detail, name='device_credential_detail'),

    # Requests
    path('work-request/', views.work_request_form, name='work_request_form'),
    path('work-request/success/', views.work_request_success, name='work_request_success'),
    path('service-plan/<int:property_pk>/change/', views.service_plan_change, name='service_plan_change'),
    path('service-plan/success/', views.service_plan_change_success, name='service_plan_change_success'),
    path('account/close/', views.account_closure, name='account_closure'),
    path('account/close/success/', views.account_closure_success, name='account_closure_success'),
]
