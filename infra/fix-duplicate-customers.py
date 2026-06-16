from django.db import connection

with connection.cursor() as cursor:
    # Find all tables with FKs pointing at jobs_customer so we don't miss any
    cursor.execute("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        JOIN information_schema.key_column_usage ccu
            ON rc.unique_constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'jobs_customer'
          AND ccu.column_name = 'id'
        ORDER BY tc.table_name
    """)
    fk_refs = cursor.fetchall()
    print('FK references to jobs_customer:')
    for tbl, col in fk_refs:
        print(f'  {tbl}.{col}')

    # Find duplicate emails
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

            # Reassign all FK references to the keeper
            for tbl, col in fk_refs:
                cursor.execute(f"""
                    UPDATE {tbl}
                    SET {col} = %s
                    WHERE {col} IN (
                        SELECT id FROM jobs_customer WHERE email = %s AND id != %s
                    )
                """, [keeper_id, email, keeper_id])
                if cursor.rowcount:
                    print(f'  Reassigned {cursor.rowcount} rows in {tbl}.{col}')

            # Delete duplicates
            cursor.execute("""
                DELETE FROM jobs_customer WHERE email = %s AND id != %s
            """, [email, keeper_id])
            print(f'  Deleted {cursor.rowcount} duplicate customer(s)')

print('Deduplication complete.')
