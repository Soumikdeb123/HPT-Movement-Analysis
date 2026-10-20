const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

const db = require('../db');
const verifyToken = require('../middleware/verifyToken');

const router = express.Router();

const AVAILABLE_STATUSES = [
    'registered',
    'active',
    'email_updated'
];

function fail(status, message) {
    const error = new Error(message);
    error.status = status;
    throw error;
}

function text(value) {
    return typeof value === 'string' ? value.trim() : '';
}

function validEmail(email) {
    return (
        email.length <= 255 &&
        /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
    );
}

function validPassword(password) {
    return (
        typeof password === 'string' &&
        password.length >= 8 &&
        Buffer.byteLength(password, 'utf8') <= 72 &&
        /[a-z]/.test(password) &&
        /[A-Z]/.test(password) &&
        /\d/.test(password)
    );
}

function publicUser(user) {
    return {
        id: user.id,
        username: user.username,
        email: user.email,
        role: user.role,
        status: user.status
    };
}

function requireAdmin(req, res, next) {
    if (req.user.role !== 'admin') {
        return res.status(403).json({
            error: 'Administrator access required.'
        });
    }

    next();
}

async function confirmPassword(userId, password) {
    if (typeof password !== 'string' || !password) {
        fail(400, 'Current password is required.');
    }

    const [rows] = await db.query(
        'SELECT passwordHash FROM users WHERE id = ?',
        [userId]
    );

    if (
        !rows[0] ||
        !(await bcrypt.compare(password, rows[0].passwordHash))
    ) {
        fail(400, 'Current password is incorrect.');
    }
}
async function updateOwnAccount(req, assignments, values) {
    const [result] = await db.query(
        `UPDATE users
         SET ${assignments}
         WHERE id = ?
           AND token_version = ?
           AND status IN ('registered', 'active', 'email_updated')`,
        [...values, req.user.id, req.user.token_version]
    );

    if (!result.affectedRows) {
        fail(401, 'Session changed. Please sign in again.');
    }
}

router.post('/signIn', async (req, res) => {
    const body = req.body || {};

    const username = text(body.username);
    const email = text(body.email).toLowerCase();

    if (!username || username.length > 80) {
        fail(400, 'Username must contain 1–80 characters.');
    }

    if (!validEmail(email)) {
        fail(400, 'Please enter a valid email.');
    }

    if (!validPassword(body.password)) {
        fail(
            400,
            'Password needs uppercase, lowercase and a number; ' +
            'minimum 8 characters, maximum 72 UTF-8 bytes.'
        );
    }

    const passwordHash = await bcrypt.hash(body.password, 10);

    await db.query(
        `INSERT INTO users
            (username, email, passwordHash, role, status)
         VALUES (?, ?, ?, 'user', 'registered')`,
        [username, email, passwordHash]
    );

    res.status(201).json({
        message: 'Registration successful. Please sign in.'
    });
});

router.post('/login', async (req, res) => {
    const body = req.body || {};
    const email = text(body.email).toLowerCase();

    if (
        !validEmail(email) ||
        typeof body.password !== 'string' ||
        !body.password
    ) {
        fail(400, 'Email and password are required.');
    }

    const [rows] = await db.query(
        'SELECT * FROM users WHERE email = ?',
        [email]
    );

    const user = rows[0];

    if (
        !user ||
        !(await bcrypt.compare(body.password, user.passwordHash))
    ) {
        fail(401, 'Incorrect email or password.');
    }

    if (!AVAILABLE_STATUSES.includes(user.status)) {
        fail(403, 'This account is unavailable.');
    }

    const [updated] = await db.query(
        `UPDATE users
         SET status = 'active'
         WHERE id = ?
           AND token_version = ?
           AND status IN ('registered', 'active', 'email_updated')`,
        [user.id, user.token_version]
    );

    if (!updated.affectedRows) {
        fail(401, 'Account changed. Please sign in again.');
    }

    const token = jwt.sign(
        {
            id: user.id,
            version: user.token_version
        },
        process.env.TOKEN,
        {
            algorithm: 'HS256',
            expiresIn: process.env.AUTH_TOKEN_TTL || '8h'
        }
    );

    res.json({
        message: 'Login successful.',
        token,
        email: user.email,
        role: user.role
    });
});

router.use(verifyToken);

router.get('/session', (req, res) => {
    res.json(publicUser(req.user));
});

router.get('/me', (req, res) => {
    res.json(publicUser(req.user));
});

router.patch('/me', async (req, res) => {
    const body = req.body || {};

    const username = text(body.username);
    const email = text(body.email).toLowerCase();

    if (!username || username.length > 80) {
        fail(400, 'Username must contain 1–80 characters.');
    }

    if (!validEmail(email)) {
        fail(400, 'Please enter a valid email.');
    }

    await confirmPassword(req.user.id, body.currentPassword);

    await updateOwnAccount(
        req,
        'username = ?, email = ?',
        [username, email]
    );

    res.json({
        message: 'Profile updated.',
        username,
        email
    });
});

router.patch('/me/password', async (req, res) => {
    const body = req.body || {};

    if (!validPassword(body.newPassword)) {
        fail(
            400,
            'Password needs uppercase, lowercase and a number; ' +
            'minimum 8 characters, maximum 72 UTF-8 bytes.'
        );
    }

    if (body.currentPassword === body.newPassword) {
        fail(400, 'Please choose a different password.');
    }

    await confirmPassword(req.user.id, body.currentPassword);

    const passwordHash = await bcrypt.hash(body.newPassword, 10);

    await updateOwnAccount(
        req,
        'passwordHash = ?, token_version = token_version + 1',
        [passwordHash]
    );

    res.json({
        message: 'Password changed. Please sign in again.'
    });
});

router.delete('/me', async (req, res) => {
    if (req.user.role === 'admin') {
        fail(403, 'Administrator accounts cannot be deleted here.');
    }

    await confirmPassword(
        req.user.id,
        (req.body || {}).currentPassword
    );

    await updateOwnAccount(
        req,
        "status = 'deleted', token_version = token_version + 1",
        []
    );

    res.json({
        message: 'Account deleted.'
    });
});

router.get('/users', requireAdmin, async (req, res) => {
    const [users] = await db.query(
        `SELECT id, username, email, role, status
         FROM users
         ORDER BY id DESC`
    );

    res.json({ users });
});

router.patch('/users/:id/status', requireAdmin, async (req, res) => {
    const id = Number(req.params.id);
    const status = (req.body || {}).status;

    if (!Number.isSafeInteger(id) || id <= 0) {
        fail(400, 'Invalid user ID.');
    }

    if (!['disabled', 'active'].includes(status)) {
        fail(400, 'Status must be disabled or active.');
    }

    const previousStates = status === 'active'
        ? ['disabled']
        : AVAILABLE_STATUSES;

    const [result] = await db.query(
        `UPDATE users
         SET status = ?,
             token_version = token_version + 1
         WHERE id = ?
           AND role = 'user'
           AND status IN (?)`,
        [status, id, previousStates]
    );

    if (!result.affectedRows) {
        fail(
            409,
            'User not found, protected, or status already changed.'
        );
    }

    res.json({
        message: status === 'disabled'
            ? 'User disabled.'
            : 'User restored. They must sign in again.'
    });
});

module.exports = router;