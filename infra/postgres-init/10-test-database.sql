-- The integration test suite needs a second database next to the application one.
SELECT 'CREATE DATABASE vendoriq_test OWNER vendoriq'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vendoriq_test')\gexec
