const path = require('path');

require('dotenv').config({
    path: path.join(__dirname, '.env')
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
    } catch (error) {
        res.status(503).json({
            error: 'Database connection failed'
        });
    }
});

async function start() {
    try {
        if (!process.env.TOKEN || process.env.TOKEN.length < 32) {
            throw new Error(' ');
        }

        await db.query('SELECT id FROM users LIMIT 1');

        const authRouter = require('./routes/auth');

        app.use('/api/auth', (req, res, next) => {
            const allowed =
                req.method === 'POST' &&
                ['/signIn', '/login'].includes(req.path);

            if (!allowed) {
                return res.status(404).json({
                    error: 'This endpoint is not enabled'
                });
            }

            next();
        }, authRouter);

        app.use((error, req, res, next) => {
            if (error.type === 'entity.parse.failed') {
                return res.status(400).json({
                    error: 'Invalid JSON'
                });
            }

            console.error(error.message);
            res.status(500).json({
                error: 'Internal server error'
            });
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
        console.error('Start Failed');
        console.dir(error, { depth: null });
        await db.end();
        process.exitCode = 1;
    }
}

start();