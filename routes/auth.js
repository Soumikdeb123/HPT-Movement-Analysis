const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('../db');

const router = express.Router();
const TOKEN = process.env.TOKEN;

(async () => {
    try {
        const [rows] = await db.query('SELECT * FROM users WHERE email = ?', [process.env.ADMIN_EMAIL]);
        if (rows.length === 0) {
            const passwordHash = await bcrypt.hash(process.env.ADMIN_PASSWORD, 10);
            await db.query(
                'INSERT INTO users (email, passwordHash, role, status) VALUES (?, ?, ?, ?)',
                [process.env.ADMIN_EMAIL, passwordHash, 'admin', 'registered']
            );
            console.log(`Admin ${process.env.ADMIN_EMAIL} created.`);
        }
    } catch (error) {
        console.error('Error creating admin user:', error);
    }
})();

const verifyToken = require('../middleware/verifyToken');

router.post('/signIn', async (req, res) => {
    try {
        const { email, password } = req.body;
        if (!email || !password) return res.status(400).json({ error: 'Email and password are required' });

        const passwordStrongEnough = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;
        if (!passwordStrongEnough.test(password)) {
            return res.status(400).json({
                error: 'Password too weak. Must contain uppercase, lowercase, number, and be at least 8 characters.'
            });
        }
        const [existing] = await db.query('SELECT id FROM users WHERE email = ?', [email]);
        if (existing.length > 0)
            return res.status(409).json({ error: 'Already registered' });

        const passwordHash = await bcrypt.hash(password, 10);
        await db.query(
            'INSERT INTO users (email, passwordHash, status) VALUES (?, ?, ?)',
            [email, passwordHash, 'registered']
        );

        res.status(201).json({ message: 'User registered successfully' });
    } catch (error) {
        console.error('Registration error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

router.post('/login', async (req, res) => {
    try {
        const { email, password } = req.body;

        const [users] = await db.query('SELECT * FROM users WHERE email = ?', [email]);
        const user = users[0];
        if (!user || user.status === 'deleted') return res.status(401).json({ error: 'Invalid' });

        const match = await bcrypt.compare(password, user.passwordHash);
        if (!match) return res.status(401).json({ error: 'Invalid' });

        await db.query('UPDATE users SET status = ? WHERE email = ?', ['active', email]);

        const token = jwt.sign({ email }, TOKEN, { expiresIn: '15m' });
        res.json({ message: 'Login successful', token, email });
    } catch (error) {
        console.error('Login error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

router.delete('/delete', async (req, res) => {
    try {
        const { email } = req.body;
        if (!email) return res.status(400).json({ error: 'Email required' });

        const [result] = await db.query('UPDATE users SET status = ? WHERE email = ?', ['deleted', email]);
        if (result.affectedRows === 0) return res.status(404).json({ error: 'User not found' });

        res.json({ message: 'User marked as deleted' });
    } catch (error) {
        console.error('Delete user error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});


router.post('/view-emails', async (req, res) => {
    try {
        const { email, password } = req.body;

        const [admins] = await db.query('SELECT * FROM users WHERE email = ? AND role = "admin"', [email]);
        const admin = admins[0];
        if (!admin) return res.status(403).json({ error: 'Not admin' });

        const match = await bcrypt.compare(password, admin.passwordHash);
        if (!match) return res.status(401).json({ error: 'Wrong password' });

        const [users] = await db.query('SELECT email FROM users WHERE role != "admin" AND status != "deleted"');
        const emails = users.map(u => u.email);

        res.json({ message: 'Verified', emails });
    } catch (error) {
        console.error('View emails error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

router.patch('/change-email', verifyToken, async (req, res) => {
    try {
        const { newEmail } = req.body;
        const oldEmail = req.user.email;


        if (!newEmail || typeof newEmail !== 'string') {
            return res.status(400).json({ error: 'Invalid new email' });
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(newEmail)) {
            return res.status(400).json({ error: 'Invalid email format' });
        }

        if (newEmail === oldEmail) {
            return res.status(400).json({ error: 'New email is the same as current email' });
        }

        const [exists] = await db.query('SELECT id FROM users WHERE email = ? AND email != ?', [newEmail, oldEmail]);
        if (exists.length > 0) {
            return res.status(409).json({ error: 'Email already in use' });
        }
        const [result] = await db.query('UPDATE users SET email = ?, status = ? WHERE email = ?', [newEmail, 'email_updated', oldEmail]);
        if (result.affectedRows === 0) {
            return res.status(404).json({ error: 'User not found' });
        }

        res.json({ message: 'Email updated successfully', newEmail });
    } catch (error) {
        console.error('Change email error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

router.patch('/change-password', verifyToken, async (req, res) => {
    try {
        const { oldPassword, newPassword } = req.body;
        const email = req.user.email;


        if (!oldPassword || !newPassword) {
            return res.status(400).json({ error: 'Both old and new passwords are required' });
        }

        if (oldPassword === newPassword) {
            return res.status(400).json({ error: 'New password must be different from current password' });
        }

        const passwordStrongEnough = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$/;
        if (!passwordStrongEnough.test(newPassword)) {
            return res.status(400).json({
                error: 'Password too weak. Must contain uppercase, lowercase, number, symbol, and be at least 8 characters.'
            });
        }

        const [users] = await db.query('SELECT * FROM users WHERE email = ?', [email]);
        const user = users[0];
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }

        const isMatch = await bcrypt.compare(oldPassword, user.passwordHash);
        if (!isMatch) {
            return res.status(401).json({ error: 'Current password is incorrect' });
        }

        const newHash = await bcrypt.hash(newPassword, 10);

        const [result] = await db.query('UPDATE users SET passwordHash = ? WHERE email = ?', [newHash, email]);
        if (result.affectedRows === 0) {
            return res.status(404).json({ error: 'Failed to update password' });
        }

        res.json({ message: 'Password updated successfully. Please log in again.' });
    } catch (error) {
        console.error('Change password error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

module.exports = router;