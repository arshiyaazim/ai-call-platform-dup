-- WBOM Full Database Audit
-- Run on VPS: cat /tmp/audit.sql | docker exec -i ai-postgres psql -U postgres

-- 1. Duplicate employees
SELECT '=== DUPLICATE EMPLOYEES ===' AS audit;
SELECT employee_mobile, COUNT(*) AS cnt
FROM wbom_employees
GROUP BY employee_mobile HAVING COUNT(*) > 1;

-- 2. Constraints on wbom_employees
SELECT '=== EMPLOYEE CONSTRAINTS ===' AS audit;
SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'wbom_employees'::regclass;

-- 3. Null/empty employee fields
SELECT '=== NULL EMPLOYEE DATA ===' AS audit;
SELECT
    COUNT(*) FILTER (WHERE employee_mobile IS NULL OR employee_mobile = '') AS null_mobiles,
    COUNT(*) FILTER (WHERE employee_name IS NULL OR employee_name = '') AS null_names
FROM wbom_employees;

-- 4. Payments without valid employee
SELECT '=== ORPHAN TRANSACTIONS ===' AS audit;
SELECT COUNT(*) AS orphan_txns
FROM wbom_cash_transactions t
LEFT JOIN wbom_employees e ON e.employee_id = t.employee_id
WHERE e.employee_id IS NULL;

-- 5. Inconsistent method values
SELECT '=== PAYMENT METHODS ===' AS audit;
SELECT payment_method, COUNT(*) FROM wbom_cash_transactions GROUP BY payment_method ORDER BY COUNT(*) DESC;

-- 6. Inconsistent transaction types
SELECT '=== TRANSACTION TYPES ===' AS audit;
SELECT transaction_type, COUNT(*) FROM wbom_cash_transactions GROUP BY transaction_type ORDER BY COUNT(*) DESC;

-- 7. Null-critical transaction fields
SELECT '=== NULL TRANSACTION DATA ===' AS audit;
SELECT
    COUNT(*) FILTER (WHERE amount IS NULL) AS null_amounts,
    COUNT(*) FILTER (WHERE transaction_date IS NULL) AS null_dates,
    COUNT(*) FILTER (WHERE payment_method IS NULL) AS null_methods,
    COUNT(*) FILTER (WHERE employee_id IS NULL) AS null_employee_ids
FROM wbom_cash_transactions;

-- 8. Duplicate contacts
SELECT '=== DUPLICATE CONTACTS (wbom) ===' AS audit;
SELECT whatsapp_number, COUNT(*) AS cnt
FROM wbom_contacts
GROUP BY whatsapp_number HAVING COUNT(*) > 1;

-- 9. Cross-table contact overlap
SELECT '=== CONTACT OVERLAP: social vs wbom ===' AS audit;
SELECT COUNT(*) AS overlapping_contacts
FROM fazle_social_contacts sc
JOIN wbom_contacts wc ON REPLACE(REPLACE(REPLACE(sc.identifier, '+880', '0'), '-', ''), ' ', '') = wc.whatsapp_number;

-- 10. Employees with mobile matching contacts
SELECT '=== EMPLOYEE-CONTACT OVERLAP ===' AS audit;
SELECT COUNT(*) AS emp_in_contacts
FROM wbom_employees e
JOIN wbom_contacts c ON e.employee_mobile = c.whatsapp_number;

-- 11. Program status audit
SELECT '=== PROGRAM STATUS ===' AS audit;
SELECT status, COUNT(*) FROM wbom_escort_programs GROUP BY status;

-- 12. Indexes check
SELECT '=== INDEXES ON KEY TABLES ===' AS audit;
SELECT tablename, indexname
FROM pg_indexes
WHERE tablename LIKE 'wbom_%'
ORDER BY tablename, indexname;

-- 13. Employee designation distribution
SELECT '=== EMPLOYEE DESIGNATIONS ===' AS audit;
SELECT designation, COUNT(*) FROM wbom_employees GROUP BY designation;

-- 14. Relation type distribution in contacts
SELECT '=== CONTACT RELATION TYPES ===' AS audit;
SELECT rt.relation_name, COUNT(c.contact_id)
FROM wbom_contacts c
LEFT JOIN wbom_relation_types rt ON rt.relation_type_id = c.relation_type_id
GROUP BY rt.relation_name;
