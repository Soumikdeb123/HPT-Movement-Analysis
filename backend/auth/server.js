const path = require('path');

require('dotenv').config({
  path: path.join(__dirname, '..', '.env'),
});

const express = require('express');
const db = require('./db');

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
    } catch (_) {
        res.status(503).json({
            error: 'Database connection failed.'
        });
    }
});

async function start() {
    try {
        if (!process.env.TOKEN || process.env.TOKEN.length < 32) {
            throw new Error(
                'TOKEN must contain at least 32 characters.'
            );
        }

        await db.query(
            'SELECT id, username, token_version FROM users LIMIT 1'
        );

        app.use('/api/auth', require('./routes/auth'));

        app.use((error, req, res, next) => {
            if (error.type === 'entity.parse.failed') {
                return res.status(400).json({
                    error: 'Invalid JSON.'
                });
            }

            if (error.code === 'ER_DUP_ENTRY') {
                return res.status(409).json({
                    error: 'This email is already registered.'
                });
            }

            const status =
                Number.isInteger(error.status) &&
                error.status >= 400 &&
                error.status < 500
                    ? error.status
                    : 500;

            if (status === 500) {
                console.error(error);
            }

            res.status(status).json({
                error: status === 500
                    ? 'Internal server error.'
                    : error.message
            });
        });

        const server = app.listen(port, '0.0.0.0', () => {
            console.log(
                `Backend running at http://localhost:${port}`
            );
        });

        server.on('error', error => {
            console.error(error);
            process.exit(1);
        });
    } catch (error) {
        console.error('Start failed:', error.message);
        await db.end();
        process.exitCode = 1;
    }
}

start();