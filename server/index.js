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

const WIDTH = 800;
const HEIGHT = 600;
const TICK_RATE = 1000 / 60;
const MAX_PLAYERS = 2;
const gravity = 0.6;
const friction = 0.8;

const platforms = [
    { x: 0, y: 550, width: 800, height: 50 },
    { x: 100, y: 400, width: 200, height: 20 },
    { x: 500, y: 400, width: 200, height: 20 },
    { x: 300, y: 250, width: 200, height: 20 },
];

const avatarPalette = {
    flare: '#ff6b6b',
    nova: '#4dabf7',
    mint: '#2ed573',
    ember: '#ffa502',
    violet: '#845ef7',
    aqua: '#22b8cf',
    lime: '#94d82d',
    rose: '#f06595',
    bot: '#adb5bd',
};

const rooms = new Map();
const socketRoom = new Map();

function generateRoomCode() {
    let code = '';
    do {
        code = Math.floor(100000 + Math.random() * 900000).toString();
    } while (rooms.has(code));
    return code;
}

function createRoom(mode) {
    const code = generateRoomCode();
    const room = {
        code,
        mode,
        players: new Map(),
        bots: new Map(),
        bullets: [],
        platforms,
        maxPlayers: MAX_PLAYERS,
        botSeq: 0,
    };
    rooms.set(code, room);
    return room;
}

function randomSpawn() {
    return {
        x: 100 + Math.random() * 600,
        y: 150,
    };
}

function assignAvatar(player, avatarId) {
    const safeId = avatarPalette[avatarId] ? avatarId : 'flare';
    player.avatarId = safeId;
    player.color = avatarPalette[safeId];
}

function createPlayer(id, avatarId) {
    const spawn = randomSpawn();
    const player = {
        id,
        x: spawn.x,
        y: spawn.y,
        width: 30,
        height: 30,
        vx: 0,
        vy: 0,
        color: avatarPalette.flare,
        avatarId: 'flare',
        hp: 100,
        speed: 5,
        jumpPower: -12,
        grounded: false,
        mouseTarget: { x: 0, y: 0 },
        inputs: { left: false, right: false, jump: false },
        cooldown: 0,
    };
    assignAvatar(player, avatarId);
    return player;
}

function createBot(room) {
    const spawn = randomSpawn();
    const bot = {
        id: `bot-${room.botSeq++}`,
        x: spawn.x,
        y: spawn.y,
        width: 30,
        height: 30,
        vx: 0,
        vy: 0,
        color: avatarPalette.bot,
        avatarId: 'bot',
        hp: 100,
        speed: 0,
        jumpPower: 0,
        grounded: false,
        mouseTarget: { x: 0, y: 0 },
        inputs: { left: false, right: false, jump: false },
        cooldown: 0,
        isBot: true,
    };
    room.bots.set(bot.id, bot);
    return bot;
}

function isAvatarTaken(room, avatarId, exceptId) {
    for (const player of room.players.values()) {
        if (player.id !== exceptId && player.avatarId === avatarId) {
            return true;
        }
    }
    return false;
}

function getRoomState(room) {
    const players = Array.from(room.players.values()).map((player) => ({
        id: player.id,
        avatarId: player.avatarId,
    }));
    const takenAvatars = players.map((player) => player.avatarId);
    return {
        code: room.code,
        players,
        takenAvatars,
        maxPlayers: room.maxPlayers,
        mode: room.mode,
    };
}

function emitRoomState(room) {
    io.to(room.code).emit('roomState', getRoomState(room));
}

function joinRoom(socket, room) {
    socket.join(room.code);
    socketRoom.set(socket.id, room.code);
}

function leaveRoom(socket) {
    const code = socketRoom.get(socket.id);
    if (!code) return;
    const room = rooms.get(code);
    if (!room) return;
    room.players.delete(socket.id);
    socketRoom.delete(socket.id);
    socket.leave(code);

    if (room.players.size === 0) {
        rooms.delete(code);
        return;
    }
    emitRoomState(room);
}

function checkCollision(entity, rect) {
    if (
        entity.x < rect.x + rect.width &&
        entity.x + entity.width > rect.x &&
        entity.y < rect.y + rect.height &&
        entity.y + entity.height > rect.y
    ) {
        const overlapBottom = entity.y + entity.height - rect.y;
        const overlapTop = rect.y + rect.height - entity.y;
        const overlapRight = entity.x + entity.width - rect.x;
        const overlapLeft = rect.x + rect.width - entity.x;

        const min = Math.min(
            overlapBottom,
            Math.max(0, overlapTop),
            Math.max(0, overlapRight),
            Math.max(0, overlapLeft)
        );

        if (min === overlapBottom && entity.vy > 0) {
            entity.y = rect.y - entity.height;
            entity.vy = 0;
            entity.grounded = true;
        } else if (min === overlapTop && entity.vy < 0) {
            entity.y = rect.y + rect.height;
            entity.vy = 0;
        } else if (min === overlapRight) {
            entity.x = rect.x - entity.width;
            entity.vx = 0;
        } else if (min === overlapLeft) {
            entity.x = rect.x + rect.width;
            entity.vx = 0;
        }
    }
}

function bulletHitsRect(bullet, rect) {
    return (
        bullet.x >= rect.x &&
        bullet.x <= rect.x + rect.width &&
        bullet.y >= rect.y &&
        bullet.y <= rect.y + rect.height
    );
}

io.on('connection', (socket) => {
    socket.on('createRoom', ({ avatarId } = {}, ack) => {
        leaveRoom(socket);
        const room = createRoom('pvp');
        const player = createPlayer(socket.id, avatarId);
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    });

    socket.on('joinRoom', ({ code, avatarId } = {}, ack) => {
        const room = rooms.get(code);
        if (!room) {
            if (typeof ack === 'function') ack({ ok: false, message: '존재하지 않는 방입니다.' });
            return;
        }
        if (room.players.size >= room.maxPlayers) {
            if (typeof ack === 'function') ack({ ok: false, message: '방이 가득 찼습니다.' });
            return;
        }
        if (isAvatarTaken(room, avatarId)) {
            if (typeof ack === 'function') ack({ ok: false, message: '이미 선택된 캐릭터입니다.' });
            return;
        }
        leaveRoom(socket);
        const player = createPlayer(socket.id, avatarId);
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    });

    socket.on('startSolo', ({ avatarId } = {}, ack) => {
        leaveRoom(socket);
        const room = createRoom('solo');
        const player = createPlayer(socket.id, avatarId);
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        for (let i = 0; i < 3; i += 1) {
            createBot(room);
        }
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    });

    socket.on('selectAvatar', ({ avatarId } = {}, ack) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room) return;
        if (isAvatarTaken(room, avatarId, socket.id)) {
            if (typeof ack === 'function') ack({ ok: false, message: '이미 선택된 캐릭터입니다.' });
            return;
        }
        const player = room.players.get(socket.id);
        if (!player) return;
        assignAvatar(player, avatarId);
        emitRoomState(room);
        if (typeof ack === 'function') ack({ ok: true });
    });

    socket.on('input', (inputs) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        const player = room?.players.get(socket.id);
        if (player) {
            player.inputs = inputs;
        }
    });

    socket.on('mouseMove', (pos) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        const player = room?.players.get(socket.id);
        if (player) {
            player.mouseTarget = pos;
        }
    });

    socket.on('shoot', () => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        const player = room?.players.get(socket.id);
        if (!player || player.hp <= 0 || player.cooldown > 0) return;

        const cx = player.x + player.width / 2;
        const cy = player.y + player.height / 2;
        const angle = Math.atan2(player.mouseTarget.y - cy, player.mouseTarget.x - cx);
        const speed = 15;

        room.bullets.push({
            x: cx,
            y: cy,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            color: player.color,
            owner: player.id,
            active: true,
            life: 80,
        });

        player.vx -= Math.cos(angle) * 2;
        player.cooldown = 15;
    });

    socket.on('leaveRoom', () => {
        leaveRoom(socket);
    });

    socket.on('disconnect', () => {
        leaveRoom(socket);
    });
});

setInterval(() => {
    rooms.forEach((room) => {
        room.players.forEach((player) => {
            if (player.hp <= 0) return;

            if (player.cooldown > 0) player.cooldown -= 1;

            if (player.inputs.left) player.vx -= 1.5;
            if (player.inputs.right) player.vx += 1.5;
            if (player.inputs.jump && player.grounded) {
                player.vy = player.jumpPower;
                player.grounded = false;
            }

            if (player.vx > player.speed) player.vx = player.speed;
            if (player.vx < -player.speed) player.vx = -player.speed;
            if (!player.inputs.left && !player.inputs.right) player.vx *= friction;

            player.vy += gravity;
            player.x += player.vx;
            player.y += player.vy;
            player.grounded = false;

            if (player.x < 0) {
                player.x = 0;
                player.vx = 0;
            }
            if (player.x + player.width > WIDTH) {
                player.x = WIDTH - player.width;
                player.vx = 0;
            }

            room.platforms.forEach((plat) => checkCollision(player, plat));
        });

        room.bots.forEach((bot) => {
            if (bot.hp <= 0) return;
            bot.vy += gravity;
            bot.x += bot.vx;
            bot.y += bot.vy;
            bot.grounded = false;
            if (bot.x < 0) bot.x = 0;
            if (bot.x + bot.width > WIDTH) bot.x = WIDTH - bot.width;
            room.platforms.forEach((plat) => checkCollision(bot, plat));
        });

        room.bullets.forEach((bullet) => {
            if (!bullet.active) return;
            bullet.x += bullet.vx;
            bullet.y += bullet.vy;
            bullet.life -= 1;

            if (
                bullet.life <= 0 ||
                bullet.x < 0 ||
                bullet.x > WIDTH ||
                bullet.y < 0 ||
                bullet.y > HEIGHT
            ) {
                bullet.active = false;
                return;
            }

            for (const plat of room.platforms) {
                if (bulletHitsRect(bullet, plat)) {
                    bullet.active = false;
                    return;
                }
            }

            room.players.forEach((player) => {
                if (!bullet.active || player.hp <= 0 || bullet.owner === player.id) return;
                if (
                    bullet.x > player.x &&
                    bullet.x < player.x + player.width &&
                    bullet.y > player.y &&
                    bullet.y < player.y + player.height
                ) {
                    player.hp -= 25;
                    player.vx += bullet.vx * 0.4;
                    player.vy -= 4;
                    bullet.active = false;
                }
            });

            room.bots.forEach((bot) => {
                if (!bullet.active || bot.hp <= 0 || bullet.owner === bot.id) return;
                if (
                    bullet.x > bot.x &&
                    bullet.x < bot.x + bot.width &&
                    bullet.y > bot.y &&
                    bullet.y < bot.y + bot.height
                ) {
                    bot.hp -= 50;
                    bot.vx += bullet.vx * 0.4;
                    bot.vy -= 4;
                    bullet.active = false;
                }
            });
        });

        room.bullets = room.bullets.filter((bullet) => bullet.active);

        if (room.mode === 'solo') {
            room.bots.forEach((bot, id) => {
                if (bot.hp <= 0) room.bots.delete(id);
            });
            while (room.bots.size < 3) {
                createBot(room);
            }
        }

        io.to(room.code).emit('gameState', {
            code: room.code,
            mode: room.mode,
            players: Array.from(room.players.values()),
            bots: Array.from(room.bots.values()),
            bullets: room.bullets,
            platforms: room.platforms,
            maxPlayers: room.maxPlayers,
        });
    });
}, TICK_RATE);

server.listen(port, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${port}`);
});
