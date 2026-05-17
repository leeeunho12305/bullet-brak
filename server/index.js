import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = createServer(app);
const io = new Server(server);
const port = process.env.PORT || 4000;

app.use(express.static(path.join(__dirname, '../client')));

const platforms = [
    { x: 0, y: 550, width: 800, height: 50 },
    { x: 100, y: 400, width: 200, height: 20 },
    { x: 500, y: 400, width: 200, height: 20 },
    { x: 300, y: 250, width: 200, height: 20 },
];

const players = {};
let bullets = [];
const gravity = 0.6;
const friction = 0.8;
const colors = ['#ff4757', '#1e90ff', '#2ed573', '#ffa502'];

io.on('connection', (socket) => {
    console.log('Player connected:', socket.id);
    const color = colors[Object.keys(players).length % colors.length];
    
    // Spawn
    players[socket.id] = {
        x: Math.random() * 600 + 100, y: 200,
        width: 30, height: 30, vx: 0, vy: 0,
        color: color, hp: 100,
        speed: 5, jumpPower: -12, grounded: false,
        mouseTarget: { x: 0, y: 0 },
        inputs: { left: false, right: false, jump: false },
        cooldown: 0
    };

    socket.on('input', (inputs) => {
        if(players[socket.id]) players[socket.id].inputs = inputs;
    });

    socket.on('mouseMove', (pos) => {
        if(players[socket.id]) players[socket.id].mouseTarget = pos;
    });

    socket.on('shoot', () => {
        const p = players[socket.id];
        if (!p || p.hp <= 0 || p.cooldown > 0) return;
        
        const cx = p.x + p.width / 2;
        const cy = p.y + p.height / 2;
        const angle = Math.atan2(p.mouseTarget.y - cy, p.mouseTarget.x - cx);
        const speed = 15;
        
        bullets.push({
            x: cx, y: cy,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            color: p.color, owner: socket.id,
            active: true, life: 60
        });
        
        // 반동 (사격 시 살짝 밀림)
        p.vx -= Math.cos(angle) * 2;
        p.cooldown = 15;
    });

    socket.on('disconnect', () => {
        console.log('Player disconnected:', socket.id);
        delete players[socket.id];
    });
});

function checkCollision(p, rect) {
    if (p.x < rect.x + rect.width && p.x + p.width > rect.x &&
        p.y < rect.y + rect.height && p.y + p.height > rect.y) {
        
        const overlapBottom = (p.y + p.height) - rect.y;
        const overlapTop = (rect.y + rect.height) - p.y;
        const overlapRight = (p.x + p.width) - rect.x;
        const overlapLeft = (rect.x + rect.width) - p.x;

        const min = Math.min(overlapBottom, Math.max(0, overlapTop), Math.max(0, overlapRight), Math.max(0, overlapLeft));

        if (min === overlapBottom && p.vy > 0) { p.y = rect.y - p.height; p.vy = 0; p.grounded = true; }
        else if (min === overlapTop && p.vy < 0) { p.y = rect.y + rect.height; p.vy = 0; }
        else if (min === overlapRight) { p.x = rect.x - p.width; p.vx = 0; }
        else if (min === overlapLeft) { p.x = rect.x + rect.width; p.vx = 0; }
    }
}

// Server loop (60 FPS)
setInterval(() => {
    Object.values(players).forEach(p => {
        if (p.hp <= 0) return;

        if (p.cooldown > 0) p.cooldown--;

        if (p.inputs.left) p.vx -= 1.5;
        if (p.inputs.right) p.vx += 1.5;
        if (p.inputs.jump && p.grounded) { p.vy = p.jumpPower; p.grounded = false; }

        if (p.vx > p.speed) p.vx = p.speed;
        if (p.vx < -p.speed) p.vx = -p.speed;
        if (!p.inputs.left && !p.inputs.right) p.vx *= friction;

        p.vy += gravity;
        p.x += p.vx; p.y += p.vy;
        p.grounded = false;

        if (p.x < 0) { p.x = 0; p.vx = 0; }
        if (p.x + p.width > 800) { p.x = 800 - p.width; p.vx = 0; }

        platforms.forEach(plat => checkCollision(p, plat));
    });

    bullets.forEach(b => {
         b.x += b.vx; b.y += b.vy; b.life--;
         if(b.life <= 0) b.active = false;
         
         Object.entries(players).forEach(([id, p]) => {
             if (b.active && p.hp > 0 && b.owner !== id) {
                 if (b.x > p.x && b.x < p.x + p.width && b.y > p.y && b.y < p.y + p.height) {
                     p.hp -= 25;
                     p.vx += b.vx * 0.4;
                     p.vy -= 4;
                     b.active = false;
                 }
             }
         });
    });
    bullets = bullets.filter(b => b.active);

    io.emit('gameState', { players, bullets, platforms });
}, 1000 / 60);

server.listen(port, () => {
    console.log(`Server listening on http://localhost:${port}`);
});
