SELECT 'CREATE DATABASE bookpile_test OWNER bookpile'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'bookpile_test'
)\gexec

