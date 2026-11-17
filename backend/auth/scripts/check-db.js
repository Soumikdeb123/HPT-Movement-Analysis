const db = require('../db');

function explainDatabaseError(error) {
    const messages = {
        ECONNREFUSED: 'MySQL is not reachable. Start the Windows MySQL service and check DB_HOST / DB_PORT in auth/.env.',
        ETIMEDOUT: 'MySQL connection timed out. Check DB_HOST / DB_PORT in auth/.env.',
        ER_ACCESS_DENIED_ERROR: 'MySQL rejected the login. Set DB_USER and DB_PASSWORD in auth/.env to this Windows MySQL account. The Mac password may differ.',
        ER_BAD_DB_ERROR: 'Database not found. Import the Mac user_information export, or run auth/sql/complete_database_setup.sql for an empty database.',
        ER_NO_SUCH_TABLE: 'The users table is missing. Import the Mac database, or run auth/sql/complete_database_setup.sql.',
        HPT_SCHEMA: 'The users table needs an upgrade. Run auth/sql/upgrade_profile.sql in MySQL Workbench.'
    };
    return messages[error.code] || `${error.code || 'ERROR'}: ${error.message}`;
}

async function checkDatabase() {
    const [columns] = await db.query('SHOW COLUMNS FROM users');
    const actual = new Set(columns.map(column => column.Field));
    const required = ['id', 'username', 'email', 'passwordHash', 'role', 'status', 'token_version'];
    if (required.some(column => !actual.has(column))) {
        const error = new Error('Missing required users columns');
        error.code = 'HPT_SCHEMA';
        throw error;
    }
    const status = columns.find(column => column.Field === 'status');
    if (!status.Type.includes("'disabled'")) {
        const error = new Error('Missing disabled status');
        error.code = 'HPT_SCHEMA';
        throw error;
    }
}

if (require.main === module) {
    (async () => {
        try {
            await checkDatabase();
            console.log('Database connection and users schema: OK');
        } catch (error) {
            console.error(explainDatabaseError(error));
            process.exitCode = 1;
        } finally {
            await db.end();
        }
    })();
}
module.exports = { checkDatabase, explainDatabaseError };
