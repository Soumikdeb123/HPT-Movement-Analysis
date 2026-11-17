const path = require('path');

require('dotenv').config({
    path: path.join(__dirname, '.env')
});

const express = require('express');
const db = require('./db');
const { checkDatabase, explainDatabaseError } = require('./scripts/check-db');

const app = express();
const port = Number(process.env.PORT || 3000);

app.use(express.json({ limit: '100kb' }));

app.get('/health', async (req, res) => {
    try {
        await db.query('SELECT 1');
        res.json({
            message: 'Backend is running',
            database: 'connected'
        });
    } catch (error) {
        res.status(503).json({
            error: 'Database connection failed'
        });
    }
});

async function start() {
    try {
        if (!process.env.TOKEN || process.env.TOKEN.length < 32) {
            throw new Error('Set TOKEN in auth/.env to a random secret of at least 32 characters.');
        }

        await checkDatabase();

        if (process.env.ADMIN_EMAIL && process.env.ADMIN_PASSWORD) {
            const [existing] = await db.query('SELECT id FROM users WHERE email = ?',
                [process.env.ADMIN_EMAIL.trim().toLowerCase()]);
            if (!existing.length) {
                const hash = await require('bcryptjs').hash(process.env.ADMIN_PASSWORD, 10);
                await db.query(`INSERT INTO users (username, email, passwordHash, role, status)
                    VALUES (?, ?, ?, 'admin', 'registered')`,
                    ['Administrator', process.env.ADMIN_EMAIL.trim().toLowerCase(), hash]);
            }
        }
        const authRouter = require('./routes/auth');
        app.use('/api/auth', authRouter);

        app.use((error, req, res, next) => {
            if (error.type === 'entity.parse.failed') {
                return res.status(400).json({
                    error: 'Invalid JSON'
                });
            }

            if (error.code === 'ER_DUP_ENTRY') {
                return res.status(409).json({ error: 'This email is already registered.' });
            }
            const status = Number.isInteger(error.status) && error.status >= 400 && error.status < 500
                ? error.status : 500;
            if (status === 500) console.error(error.message);
            res.status(status).json({ error: status === 500 ? 'Internal server error' : error.message });
        });

        const server = app.listen(port, '0.0.0.0', () => {
            console.log(`http://localhost:${port}`);
            console.log('Connection Successful');
        });

        server.on('error', (error) => {
            console.error('Failed', error.message);
            process.exit(1);
        });
    } catch (error) {
        console.error('Start failed: ' + explainDatabaseError(error));
        await db.end();
        process.exitCode = 1;
    }
}

start();
