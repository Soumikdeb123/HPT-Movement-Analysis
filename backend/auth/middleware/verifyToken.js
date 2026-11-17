const jwt = require('jsonwebtoken');
const db = require('../db');

// Resolve the account on every request: password changes, disable and deletion
// invalidate existing sessions through token_version and current DB status.
module.exports = async function verifyToken(req, res, next) {
    const match = /^Bearer ([^\s]+)$/.exec(req.headers.authorization || '');
    if (!match) return res.status(401).json({ error: 'Please sign in again.' });
    let claims;
    try {
        claims = jwt.verify(match[1], process.env.TOKEN, { algorithms: ['HS256'] });
        if (!Number.isSafeInteger(claims.id) || !Number.isInteger(claims.version)) {
            return res.status(401).json({ error: 'Please sign in again.' });
        }
    } catch (_) {
        return res.status(401).json({ error: 'Session ended. Please sign in again.' });
    }
    try {
        const [rows] = await db.query(
            `SELECT id, username, email, role, status, token_version FROM users
             WHERE id = ? AND token_version = ?
             AND status IN ('registered', 'active', 'email_updated')`,
            [claims.id, claims.version]
        );
        if (!rows[0]) return res.status(401).json({ error: 'Session ended. Please sign in again.' });
        req.user = rows[0];
        return next();
    } catch (error) {
        return next(error);
    }
};
