const jwt = require('jsonwebtoken');
const db = require('../db');

async function verifyToken(req, res, next) {
    const header = req.headers.authorization || '';
    const match = /^Bearer\s+(\S+)$/i.exec(header);

    if (!match) {
        return res.status(401).json({
            error: 'Please sign in.'
        });
    }

    let payload;

    try {
        payload = jwt.verify(match[1], process.env.TOKEN, {
            algorithms: ['HS256']
        });
    } catch (_) {
        return res.status(401).json({
            error: 'Session expired. Please sign in again.'
        });
    }

    if (
        !payload ||
        !Number.isSafeInteger(payload.id) ||
        !Number.isSafeInteger(payload.version)
    ) {
        return res.status(401).json({
            error: 'Please sign in again.'
        });
    }

    try {
        const [rows] = await db.query(
            `SELECT id, username, email, role, status, token_version
             FROM users
             WHERE id = ?`,
            [payload.id]
        );

        const user = rows[0];

        if (
            !user ||
            !['registered', 'active', 'email_updated'].includes(user.status) ||
            user.token_version !== payload.version
        ) {
            return res.status(401).json({
                error: 'Account unavailable or session expired.'
            });
        }

        // 角色和账号状态始终读取数据库中的最新值。
        req.user = user;

        next();
    } catch (error) {
        next(error);
    }
}

module.exports = verifyToken;