const express = require('express');
const axios = require('axios');
const app = express();
const cors = require('cors')

app.use(cors())

app.get('/user', async (req, res) => {
  const accessToken = req.headers.authorization?.split(' ')[1]; // Expect: Bearer <access_token>

  if (!accessToken) {
    return res.status(401).json({ error: 'Missing access token' });
  }

  try {
    const response = await axios.get('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    res.json(response.data); // User data from Google
  } catch (err) {
    console.error('Failed to fetch user info:', err.response?.data || err.message);
    res.status(500).json({ error: 'Failed to fetch user data from Google' });
  }
});

app.listen(5000, () => {
  console.log('Server running on http://localhost:5000');
});