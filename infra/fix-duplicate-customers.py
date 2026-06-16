from django.db.models import Count
from jobs.models import Customer, Job

dupes = (
    Customer.objects
    .values('email')
    .annotate(n=Count('id'))
    .filter(n__gt=1)
)

for row in dupes:
    email = row['email']
    customers = list(Customer.objects.filter(email=email).order_by('created_at'))
    keeper = customers[0]
    others = customers[1:]
    print(f'Duplicate email: {email}')
    print(f'  Keeping id={keeper.id} (created {keeper.created_at})')
    for dup in others:
        job_count = Job.objects.filter(customer=dup).count()
        print(f'  Merging id={dup.id} ({job_count} jobs) -> id={keeper.id}')
        Job.objects.filter(customer=dup).update(customer=keeper)
        dup.delete()
        print(f'  Deleted id={dup.id}')

print('Deduplication complete.')
