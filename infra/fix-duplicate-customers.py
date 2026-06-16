from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("""
        SELECT email, COUNT(*) AS cnt, MIN(id) AS keeper_id
        FROM jobs_customer
        GROUP BY email
        HAVING COUNT(*) > 1
    """)
    dupes = cursor.fetchall()

    if not dupes:
        print('No duplicate emails found.')
    else:
        for email, cnt, keeper_id in dupes:
            print(f'Duplicate: {email} (count={cnt}, keeping id={keeper_id})')

            cursor.execute("""
                UPDATE jobs_job
                SET customer_id = %s
                WHERE customer_id IN (
                    SELECT id FROM jobs_customer WHERE email = %s AND id != %s
                )
            """, [keeper_id, email, keeper_id])
            print(f'  Reassigned {cursor.rowcount} jobs to keeper')

            cursor.execute("""
                DELETE FROM jobs_customer WHERE email = %s AND id != %s
            """, [email, keeper_id])
            print(f'  Deleted {cursor.rowcount} duplicate customer(s)')

print('Deduplication complete.')
