-- Create the local read-only account for Hari's LLM integration.
-- Run as a MySQL administrator on the POC server.
-- Replace the password placeholder with a unique secret before execution.
-- Grant access only to the specific project schemas approved for LLM use.

CREATE USER IF NOT EXISTS 'haven_llm_reader'@'localhost'
    IDENTIFIED BY 'REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD';

-- Project proj_101 only. Repeat an explicit GRANT for each separately approved
-- project schema after it has been provisioned.
GRANT SELECT ON `repo_project_proj_101`.*
    TO 'haven_llm_reader'@'localhost';

SHOW GRANTS FOR 'haven_llm_reader'@'localhost';
