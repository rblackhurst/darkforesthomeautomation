from functools import wraps

from django.shortcuts import redirect

from jobs.models import Customer


def customer_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        customer_id = request.session.get('customer_id')
        if not customer_id:
            return redirect('client_hub:login')
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            request.session.flush()
            return redirect('client_hub:login')
        request.customer = customer
        return view_func(request, *args, **kwargs)
    return wrapper
