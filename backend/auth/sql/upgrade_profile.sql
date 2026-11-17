-- Existing MySQL database: run once before starting this version.
-- Existing users, passwords and IDs are retained. Safe to run again.
USE user_information;
SET @add_username = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'username') = 0,
    'ALTER TABLE users ADD COLUMN username VARCHAR(80) NOT NULL DEFAULT ''''',
    'SELECT 1');
PREPARE stmt FROM @add_username;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @add_version = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'token_version') = 0,
    'ALTER TABLE users ADD COLUMN token_version INT NOT NULL DEFAULT 0',
    'SELECT 1');
PREPARE stmt FROM @add_version;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
ALTER TABLE users MODIFY COLUMN status
    ENUM('registered', 'active', 'deleted', 'email_updated', 'disabled') DEFAULT 'registered';
