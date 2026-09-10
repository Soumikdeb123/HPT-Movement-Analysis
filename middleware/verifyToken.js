const jwt = require('jsonwebtoken');
const dotenv = require('dotenv');
dotenv.config();

const TOKEN = process.env.TOKEN;

const verifyToken = (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) return res.status(401).json({ error: 'Token missing' });

  jwt.verify(token, TOKEN, (err, user) => {
    if (err) return res.status(401).json({ error: 'Invalid token, please log in again.' }); 
    req.user = user;
    next();

  });
};

module.exports = verifyToken;