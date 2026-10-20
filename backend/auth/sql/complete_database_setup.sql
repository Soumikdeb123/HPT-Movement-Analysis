CREATE DATABASE IF NOT EXISTS user_information
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE user_information;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,

    username VARCHAR(80) NOT NULL DEFAULT '',
    email VARCHAR(255) NOT NULL UNIQUE,
    passwordHash VARCHAR(255) NOT NULL,

    role ENUM('user', 'admin') DEFAULT 'user',

    status ENUM(
        'registered',
        'active',
        'deleted',
        'email_updated',
        'disabled'
    ) DEFAULT 'registered',

    token_version INT NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_role (role)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

SET @has_username = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND COLUMN_NAME = 'username'
);

SET @sql_username = IF(
    @has_username = 0,
    'ALTER TABLE users ADD COLUMN username VARCHAR(80) NOT NULL DEFAULT ''''',
    'SELECT ''username already exists'' AS message'
);

PREPARE stmt_username FROM @sql_username;
EXECUTE stmt_username;
DEALLOCATE PREPARE stmt_username;

SET @has_token_version = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND COLUMN_NAME = 'token_version'
);

SET @sql_token_version = IF(
    @has_token_version = 0,
    'ALTER TABLE users ADD COLUMN token_version INT NOT NULL DEFAULT 0',
    'SELECT ''token_version already exists'' AS message'
);

PREPARE stmt_token_version FROM @sql_token_version;
EXECUTE stmt_token_version;
DEALLOCATE PREPARE stmt_token_version;

ALTER TABLE users
    MODIFY COLUMN status ENUM(
        'registered',
        'active',
        'deleted',
        'email_updated',
        'disabled'
    ) DEFAULT 'registered';

DESCRIBE users;

SELECT
    id,
    username,
    email,
    role,
    status,
    token_version
FROM users
ORDER BY id;

SELECT id, username, email
FROM user_information.users
WHERE role = 'admin';

USE user_information;

UPDATE users
SET
    email = '999@qq.com',
    username = 'admin',
    token_version = token_version + 1
WHERE id = 1
  AND role = 'admin';

SELECT id, username, email, role, status
FROM users
WHERE id = 1;