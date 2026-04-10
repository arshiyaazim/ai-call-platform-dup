SELECT table_name, column_name 
FROM information_schema.columns 
WHERE table_name IN ('fazle_social_messages', 'fazle_social_contacts', 'fazle_contacts', 'fazle_leads')
ORDER BY table_name, ordinal_position;
