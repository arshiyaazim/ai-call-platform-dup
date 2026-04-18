-- Odd mobile employees
SELECT 'odd_emp_mobile' as chk, employee_id, employee_name, employee_mobile FROM wbom_employees WHERE employee_mobile !~ '^01[0-9]{9}$' LIMIT 10;

-- Contact other formats
SELECT 'odd_contact' as chk, contact_id, display_name, whatsapp_number FROM wbom_contacts WHERE whatsapp_number !~ '^01[0-9]{9}$' AND whatsapp_number !~ '^880' LIMIT 10;

-- Contact 880 format
SELECT 'contact_880' as chk, contact_id, display_name, whatsapp_number FROM wbom_contacts WHERE whatsapp_number ~ '^880' LIMIT 5;

-- Transaction 880 format
SELECT 'txn_880' as chk, transaction_id, payment_mobile FROM wbom_cash_transactions WHERE payment_mobile ~ '^880' LIMIT 5;

-- Duplicate transactions
SELECT 'dup_txn' as chk, employee_id, amount, transaction_date, count(*) as c FROM wbom_cash_transactions GROUP BY employee_id, amount, transaction_date HAVING count(*) > 1 ORDER BY c DESC LIMIT 10;

-- fazle_users
SELECT 'fazle_users' as chk, id, username, role, phone FROM fazle_users;

-- users table columns
SELECT 'users_cols' as chk, column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position;

-- users data
\x
SELECT * FROM users LIMIT 3;
\x

-- Relationship graph columns
SELECT 'rel_graph_cols' as chk, column_name FROM information_schema.columns WHERE table_name='fazle_relationship_graph' ORDER BY ordinal_position;

-- Relationship graph sample
\x
SELECT * FROM fazle_relationship_graph LIMIT 3;
\x

-- contact_roles
SELECT 'contact_roles_cols' as chk, column_name FROM information_schema.columns WHERE table_name='fazle_contact_roles' ORDER BY ordinal_position;

-- access rules
\x
SELECT * FROM fazle_access_rules;
\x

-- relation types
SELECT * FROM wbom_relation_types;

-- business types
SELECT * FROM wbom_business_types;

-- Owner numbers in env/config - check fazle_user_rules
SELECT 'user_rules' as chk, * FROM fazle_user_rules;
