import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const app = express();
const port = process.env.PORT || 4000;

app.use(express.json());
app.use(express.static(path.join(__dirname, '../client')));

app.get('/api/status', (req, res) => {
  res.json({ status: 'ok', message: 'Bullet Brak server is running' });
});

app.listen(port, () => {
  console.log(`Server listening on http://localhost:${port}`);
});
