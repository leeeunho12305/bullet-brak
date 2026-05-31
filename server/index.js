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
const MAX_HP = 120;
const DAMAGE_CLOSE = 30;
const DAMAGE_FAR = 8;
const DAMAGE_FALLOFF_RANGE = 600;

    const CARDS = [
    { id: 'hp', name: 'Health Up', desc: '최대 체력 +40', category: 'survival', color: '#ff6b6b', emoji: '❤️', effect: (p) => { p.maxHp += 40; p.hp += 40; } },
    { id: 'speed', name: 'Speed Up', desc: '이동 속도 +2', category: 'speed', color: '#ffd43b', emoji: '⚡', effect: (p) => { p.speed += 2; } },
    { id: 'jump', name: 'Jump Up', desc: '다단 점프 가능 및 점프력 상승', category: 'speed', color: '#51cf66', emoji: '☁️', effect: (p) => { p.jumpPower -= 3; p.maxJumps = (p.maxJumps || 1) + 1; } },
    { id: 'reload', name: 'Quick Reload', desc: '공격 속도 증가', category: 'attack', color: '#4dabf7', emoji: '🔫', effect: (p) => { p.maxCooldown = Math.max(2, p.maxCooldown - 5); } },
    { id: 'big', name: 'Big Bullet', desc: '총알 크기 및 넉백 증가', category: 'attack', color: '#ffa94d', emoji: '💣', effect: (p) => { p.bulletSize += 3; p.knockbackMult += 0.5; } },
    { id: 'tank', name: 'Tank', desc: '체력 +100, 속도 -2', category: 'survival', color: '#845ef7', emoji: '🛡️', effect: (p) => { p.maxHp += 100; p.hp += 100; p.speed -= 2; } },
    { id: 'glass', name: 'Glass Cannon', desc: '공격력 대폭 증가, 체력 절반', category: 'attack', color: '#f06595', emoji: '🥃', effect: (p) => { p.damageMult += 1.0; p.maxHp /= 2; p.hp = Math.min(p.hp, p.maxHp); } },
    { id: 'brawler', name: 'BRAWLER', desc: '근접 공격력 강화', category: 'attack', color: '#e03131', emoji: '🥊', effect: (p) => { p.damageMult += 0.5; p.maxHp += 20; p.hp += 20; } },
    { id: 'dazzle', name: 'DAZZLE', desc: '총알이 상대를 기절시킴', category: 'utility', color: '#ae3ec9', emoji: '✨', effect: (p) => { p.dazzleCard = true; } },
    { id: 'huge', name: 'HUGE', desc: '모든 것이 커짐', category: 'special', color: '#1098ad', emoji: '🐘', effect: (p) => { p.width *= 1.5; p.height *= 1.5; p.bulletSize += 10; } },
    { id: 'bounce', name: 'Bouncy', desc: '총알 도탄 +2회', category: 'utility', color: '#20c997', emoji: '🪃', effect: (p) => { p.maxBounces = (p.maxBounces || 0) + 2; } },
    { id: 'empower', name: 'EMPOWER', desc: '가드 시 다음 총알 2배 강화', category: 'special', color: '#fcc419', emoji: '🔥', effect: (p) => { p.empowerCard = true; } },
    { id: 'poison', name: 'POISON', desc: '적중 시 맹독 부여', category: 'attack', color: '#2b8a3e', emoji: '☠️', effect: (p) => { p.poisonCard = (p.poisonCard || 0) + 1; } },
    { id: 'mayhem', name: 'MAYHEM', desc: '도탄 +5회, 대미지 약간 감소', category: 'utility', color: '#d9480f', emoji: '💥', effect: (p) => { p.maxBounces = (p.maxBounces || 0) + 5; p.damageMult *= 0.8; } },
    { id: 'phoenix', name: 'PHOENIX', desc: '사망 시 1회 부활', category: 'survival', color: '#b93636', emoji: '🐦‍🔥', effect: (p) => { p.revives = (p.revives || 0) + 1; } },
    { id: 'grow', name: 'GROW', desc: '총알이 날아갈수록 강해짐', category: 'attack', color: '#ffd43b', emoji: '🌱', effect: (p) => { p.growCard = true; } },
    { id: 'spray', name: 'SPRAY', desc: '공속 폭발, 대미지 감소', category: 'attack', color: '#4dabf7', emoji: '🚿', effect: (p) => { p.maxCooldown = 3; p.damageMult *= 0.3; } },
    { id: 'homing', name: 'HOMING', desc: '총알이 적을 추격함', category: 'utility', color: '#bac8ff', emoji: '🎯', effect: (p) => { p.homingCard = true; } },
    { id: 'taste_of_blood', name: 'TASTE OF BLOOD', desc: '피해를 주면 이동속도 대폭 증가', category: 'utility', color: '#c92a2a', emoji: '🩸', effect: (p) => { p.bloodCard = true; } },
    { id: 'explosive', name: 'EXPLOSIVE', desc: '총알이 터지며 광역 피해', category: 'attack', color: '#fd7e14', emoji: '🧨', effect: (p) => { p.explosiveCard = true; } },
    { id: 'lifestealer', name: 'LIFESTEALER', desc: '적에게 준 피해의 30%를 회복', category: 'survival', color: '#b197fc', emoji: '🧛', effect: (p) => { p.lifestealCard = (p.lifestealCard || 0) + 0.3; } },
    { id: 'combine', name: 'COMBINE', desc: '대미지 3배, 공속 나락', category: 'attack', color: '#fab005', emoji: '⚙️', effect: (p) => { p.damageMult *= 3.0; p.maxCooldown *= 3.0; } },
    { id: 'fastball', name: 'FASTBALL', desc: '총알 비행 속도 2배', category: 'attack', color: '#fff9db', emoji: '⚾', effect: (p) => { p.bulletSpeedMult = (p.bulletSpeedMult || 1.0) + 1.0; } },
    { id: 'defender', name: 'DEFENDER', desc: '가드 쿨타임 감소, 체력 증가', category: 'survival', color: '#3b5bdb', emoji: '🛡️', effect: (p) => { p.maxHp += 30; p.hp += 30; p.blockCooldownMax = (p.blockCooldownMax || 120) - 40; } },
    { id: 'buckshot', name: 'BUCKSHOT', desc: '샷건: 여러 발 동시 발사', category: 'special', color: '#f08c00', emoji: '🎇', effect: (p) => { p.buckshot = (p.buckshot || 0) + 3; } },
    { id: 'burst', name: 'BURST', desc: '한 번 누를 때 3점사', category: 'attack', color: '#74c0fc', emoji: '〰️', effect: (p) => { p.burst = (p.burst || 0) + 2; } },
    { id: 'cold_bullets', name: 'COLD BULLETS', desc: '적중 시 적 이동속도 둔화', category: 'utility', color: '#99e9f2', emoji: '❄️', effect: (p) => { p.coldCard = true; } }
];

const platforms = [
    { x: 0, y: 550, width: 800, height: 50 },
    { x: 100, y: 400, width: 200, height: 20 },
    { x: 500, y: 400, width: 200, height: 20 },
    { x: 300, y: 250, width: 200, height: 20 },
];

const avatarPalette = {
    blue: '#4dabf7',
    green: '#51cf66',
    purple: '#845ef7',
    orange: '#ffa94d',
    red: '#ff6b6b',
    yellow: '#ffd43b',
    teal: '#20c997',
    cyan: '#3bc9db',
    indigo: '#5c7cfa',
    pink: '#f06595',
    lime: '#94d82d',
    bot: '#adb5bd',
};

const rooms = new Map();
const socketRoom = new Map();

const BAD_WORDS = /바보|멍청이|정치|섹스|성미|노무|문재|윤석|이재|정당|공산|친일|선정/gi;

function generateRoomCode() {
    let code = '';
    do {
        code = Math.floor(100000 + Math.random() * 900000).toString();
    } while (rooms.has(code));
    return code;
}

function createRoom(mode, maxPlayers = MAX_PLAYERS) {
    const code = generateRoomCode();
    const room = {
        code,
        mode,
        players: new Map(),
        bots: new Map(),
        bullets: [],
        platforms,
        maxPlayers,
        botSeq: 0,
        phase: 'waiting', // waiting, playing, picking, finished
        roundWins: {}, // playerId -> 0,1,2
        scores: {},    // playerId -> 0-5
        loserToPick: null, 
        availableCards: [],
        messages: []
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

function createPlayer(id, customization, room = null, initialCoins = 0) {
    const spawn = randomSpawn();
    const player = {
        id,
        x: spawn.x,
        y: spawn.y,
        width: 30,
        height: 30,
        vx: 0,
        vy: 0,
        hp: MAX_HP,
        speed: 5,
        jumpPower: -16,
        grounded: false,
        jumps: 0,
        maxJumps: 1,
        mouseTarget: { x: 0, y: 0 },
        inputs: { left: false, right: false, jump: false, block: false },
        cooldown: 0,
        maxCooldown: 15,
        maxHp: MAX_HP,
        damageMult: 1.0,
        bulletSize: 5,
        knockbackMult: 1.0,
        maxBounces: 0,
        blockCooldown: 0,
        blockCooldownMax: 120,
        blockActiveTime: 0,
        bulletSpeedMult: 1.0,
        revives: 0,
        empowerCard: false,
        empoweredNextShot: false,
        poisonCard: 0,
        activePoison: 0,
        growCard: false,
        homingCard: false,
        bloodCard: false,
        bloodTimer: 0,
        explosiveCard: false,
        lifestealCard: 0,
        buckshot: 0,
        burst: 0,
        coldCard: false,
        coldTimer: 0,
        dazzleCard: false,
        dazzleTimer: 0,
        customization: customization || { eye: 0, mouth: 0, detail: 0, color: '#ff6b6b' },
        nickname: '익명',
        cards: [],
        coins: initialCoins
    };

    // Assign random color if in a room
    if (room) {
        const takenColors = Array.from(room.players.values()).map(p => p.customization.color);
        const availablePalette = Object.values(avatarPalette);
        const available = availablePalette.filter(c => !takenColors.includes(c));
        player.customization.color = (available.length > 0) ? available[Math.floor(Math.random() * available.length)] : availablePalette[0];
    }
    
    return player;
}

function createBot(room) {
    const spawn = randomSpawn();
    const availablePalette = Object.values(avatarPalette);
    const bot = {
        id: `bot-${room.botSeq++}`,
        x: spawn.x,
        y: spawn.y,
        width: 30,
        height: 30,
        vx: 0,
        vy: 0,
        hp: MAX_HP,
        speed: 3.5,
        jumpPower: -14,
        grounded: false,
        mouseTarget: { x: 0, y: 0 },
        inputs: { left: false, right: false, jump: false },
        cooldown: 0,
        isBot: true,
        ai: {
            dir: 0,
            timer: 0,
            jumpCooldown: 0,
        },
        customization: {
            eyes: Math.floor(Math.random() * 5),
            mouth: Math.floor(Math.random() * 5),
            detail: Math.floor(Math.random() * 5),
            color: availablePalette[Math.floor(Math.random() * availablePalette.length)]
        }
    };
    room.bots.set(bot.id, bot);
    return bot;
}

function getRoomState(room) {
    const players = Array.from(room.players.values()).map((player) => ({
        id: player.id,
        customization: player.customization,
        nickname: player.nickname,
        coins: player.coins,
    }));
    return {
        code: room.code,
        players,
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
            entity.jumps = 0;
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

function getBulletDamage(bullet) {
    const dx = bullet.x - bullet.startX;
    const dy = bullet.y - bullet.startY;
    const distance = Math.hypot(dx, dy);
    const t = Math.min(distance / DAMAGE_FALLOFF_RANGE, 1);
    const damage = DAMAGE_CLOSE - (DAMAGE_CLOSE - DAMAGE_FAR) * t;
    return Math.round(damage);
}

function updateBot(bot, platforms) {
    if (!bot.ai) {
        bot.ai = { dir: 0, timer: 0, jumpCooldown: 0 };
    }

    if (bot.ai.timer <= 0) {
        const roll = Math.random();
        if (roll < 0.35) {
            bot.ai.dir = 0;
        } else {
            bot.ai.dir = Math.random() < 0.5 ? -1 : 1;
        }
        bot.ai.timer = 20 + Math.floor(Math.random() * 80);
    }

    bot.ai.timer -= 1;
    if (bot.ai.jumpCooldown > 0) {
        bot.ai.jumpCooldown -= 1;
    }

    if (bot.ai.dir === -1) bot.vx -= 1.2;
    if (bot.ai.dir === 1) bot.vx += 1.2;

    if (bot.vx > bot.speed) bot.vx = bot.speed;
    if (bot.vx < -bot.speed) bot.vx = -bot.speed;
    if (bot.ai.dir === 0) bot.vx *= friction;

    if (bot.grounded && bot.ai.jumpCooldown === 0 && Math.random() < 0.02) {
        bot.vy = bot.jumpPower;
        bot.grounded = false;
        bot.ai.jumpCooldown = 40;
    }

    bot.vy += gravity;
    bot.x += bot.vx;
    bot.y += bot.vy;
    bot.grounded = false;

    if (bot.x < 0) {
        bot.x = 0;
        bot.vx = 0;
    }
    if (bot.x + bot.width > WIDTH) {
        bot.x = WIDTH - bot.width;
        bot.vx = 0;
    }

    platforms.forEach((plat) => checkCollision(bot, plat));
}

io.on('connection', (socket) => {
    socket.on('createRoom', ({ customization, nickname, maxPlayers, coins } = {}, ack) => {
        leaveRoom(socket);
        const room = createRoom('pvp', maxPlayers);
        const player = createPlayer(socket.id, customization, room, coins);
        player.nickname = nickname || '익명';
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    });

    socket.on('joinRoom', ({ code, customization, nickname, coins } = {}, ack) => {
        const room = rooms.get(code);
        if (!room) {
            if (typeof ack === 'function') ack({ ok: false, message: '존재하지 않는 방입니다.' });
            return;
        }
        if (room.players.size >= room.maxPlayers) {
            if (typeof ack === 'function') ack({ ok: false, message: '방이 가득 찼습니다.' });
            return;
        }
        leaveRoom(socket);
        const player = createPlayer(socket.id, customization, room, coins);
        player.nickname = nickname || '익명';
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    });

    const startTraining = ({ customization, nickname, coins } = {}, ack) => {
        leaveRoom(socket);
        const room = createRoom('training');
        room.phase = 'playing';
        const player = createPlayer(socket.id, customization, room, coins);
        player.nickname = nickname || '익명';
        room.players.set(socket.id, player);
        joinRoom(socket, room);
        for (let i = 0; i < 3; i += 1) {
            createBot(room);
        }
        emitRoomState(room);
        if (typeof ack === 'function') {
            ack({ ok: true, code: room.code, state: getRoomState(room) });
        }
    };

    socket.on('startTraining', startTraining);
    socket.on('startSolo', startTraining);

    socket.on('startGame', () => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room) return;
        room.phase = 'playing';
        io.to(code).emit('gameStarted');
    });

    socket.on('pickCard', ({ cardId }) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room || room.phase !== 'picking' || room.loserToPick !== socket.id) return;

        const card = CARDS.find(c => c.id === cardId);
        const player = room.players.get(socket.id);
        if (card && player) {
            player.cards.push(card.id);
            card.effect(player);
            room.phase = 'roundOver'; // Temporary state to avoid multiple picks
            setTimeout(() => {
                if (!rooms.has(room.code)) return;
                room.phase = 'playing';
                room.loserToPick = null;
                resetRound(room);
            }, 1000);
        }
    });

    socket.on('chat', (text) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room) return;

        const player = room.players.get(socket.id);
        const censoredText = text.replace(BAD_WORDS, '***');
        const msg = {
            sender: player ? player.nickname : 'System',
            text: censoredText,
            time: Date.now()
        };
        room.messages.push(msg);
        if (room.messages.length > 5) room.messages.shift();
        io.to(code).emit('chat', msg);
    });

    socket.on('restartGame', () => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room || room.phase !== 'finished') return;
        resetMatch(room);
    });

    socket.on('selectAvatar', ({ customization } = {}, ack) => {
        const code = socketRoom.get(socket.id);
        const room = rooms.get(code);
        if (!room) return;
        const player = room.players.get(socket.id);
        if (!player) return;
        player.customization = customization;
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
            startX: cx,
            startY: cy,
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
        if (room.phase === 'playing' || room.phase === 'roundOver') {
            room.players.forEach((player) => {
                if (player.hp <= 0) {
                    player.vy += gravity;
                    player.x += player.vx;
                    player.y += player.vy;
                    // Dead players apply simple bounds and floor so they don't fall forever
                    if (player.x < 0) { player.x = 0; player.vx *= -0.5; }
                    if (player.x > WIDTH) { player.x = WIDTH; player.vx *= -0.5; }
                    room.platforms.forEach((plat) => {
                        const overlapLeft = (player.x + player.width) - plat.x;
                        const overlapRight = (plat.x + plat.width) - player.x;
                        const overlapTop = (player.y + player.height) - plat.y;
                        const overlapBottom = (plat.y + plat.height) - player.y;

                        if (overlapLeft > 0 && overlapRight > 0 && overlapTop > 0 && overlapBottom > 0) {
                            const min = Math.min(overlapBottom, Math.max(0, overlapTop), Math.max(0, overlapRight), Math.max(0, overlapLeft));
                            if (min === overlapBottom && player.vy > 0) {
                                player.y = plat.y - player.height;
                                player.vy = 0;
                                player.vx *= 0.8; // friction
                            }
                        }
                    });
                    return;
                }

                if (player.cooldown > 0) player.cooldown -= 1;

                // Smoother acceleration
                const accel = 0.8;
                if (!player.blockActiveTime) {
                    if (player.inputs.left) player.vx -= accel;
                    if (player.inputs.right) player.vx += accel;
                    if (player.inputs.jump && player.jumps < (player.maxJumps || 1) && !player.inputs.jumpProcessed) {
                        player.vy = player.jumpPower;
                        player.grounded = false;
                        player.jumps += 1;
                        player.inputs.jumpProcessed = true;
                    }
                } else {
                    player.vx *= 0.5; // slow down while blocking
                }
                if (!player.inputs.jump) {
                    player.inputs.jumpProcessed = false;
                }

                if (player.blockCooldown > 0) player.blockCooldown -= 1;
                if (player.blockActiveTime > 0) player.blockActiveTime -= 1;

                if (player.inputs.block && player.blockCooldown <= 0) {
                    player.blockActiveTime = 20; // active for 20 ticks
                    player.blockCooldown = 120; // 2 seconds cooldown
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
                if (bot.hp <= 0) {
                    bot.vy += gravity;
                    bot.x += bot.vx;
                    bot.y += bot.vy;
                    if (bot.x < 0) { bot.x = 0; bot.vx *= -0.5; }
                    if (bot.x > WIDTH) { bot.x = WIDTH; bot.vx *= -0.5; }
                    room.platforms.forEach((plat) => {
                        const overlapLeft = (bot.x + bot.width) - plat.x;
                        const overlapRight = (plat.x + plat.width) - bot.x;
                        const overlapTop = (bot.y + bot.height) - plat.y;
                        const overlapBottom = (plat.y + plat.height) - bot.y;

                        if (overlapLeft > 0 && overlapRight > 0 && overlapTop > 0 && overlapBottom > 0) {
                            const min = Math.min(overlapBottom, Math.max(0, overlapTop), Math.max(0, overlapRight), Math.max(0, overlapLeft));
                            if (min === overlapBottom && bot.vy > 0) {
                                bot.y = plat.y - bot.height;
                                bot.vy = 0;
                                bot.vx *= 0.8;
                            }
                        }
                    });
                    return;
                }
                updateBot(bot, room.platforms);
            });

                room.bullets.forEach((bullet) => {
                if (!bullet.active) return;
                bullet.x += bullet.vx;
                bullet.y += bullet.vy;
                bullet.life -= 1;

                if (bullet.life <= 0) {
                    bullet.active = false;
                    return;
                }

                // Window Bounds Bounce (도탄)
                if (bullet.x < 0) {
                    bullet.x = 0;
                    bullet.vx *= -1;
                    bullet.bounces = (bullet.bounces || 0) + 1;
                } else if (bullet.x > WIDTH) {
                    bullet.x = WIDTH;
                    bullet.vx *= -1;
                    bullet.bounces = (bullet.bounces || 0) + 1;
                }
                if (bullet.y < 0) {
                    bullet.y = 0;
                    bullet.vy *= -1;
                    bullet.bounces = (bullet.bounces || 0) + 1;
                } else if (bullet.y > HEIGHT) {
                    bullet.y = HEIGHT;
                    bullet.vy *= -1;
                    bullet.bounces = (bullet.bounces || 0) + 1;
                }

                if (bullet.bounces > (bullet.maxBounces || 0)) {
                    bullet.active = false;
                    return;
                }

                for (const plat of room.platforms) {
                    if (bulletHitsRect(bullet, plat)) {
                        // Platform Bounce Logic (Simple reflection based on entry side)
                        if (bullet.maxBounces > 0 && (bullet.bounces || 0) < bullet.maxBounces) {
                            // Determine which side it hit
                            const prevX = bullet.x - bullet.vx;
                            const prevY = bullet.y - bullet.vy;
                            const hitFromTopOrBottom = (prevY < plat.y || prevY > plat.y + plat.height);
                            
                            if (hitFromTopOrBottom) {
                                bullet.vy *= -1;
                            } else {
                                bullet.vx *= -1;
                            }
                            bullet.bounces = (bullet.bounces || 0) + 1;
                        } else {
                            bullet.active = false;
                            return;
                        }
                    }
                }

                room.players.forEach((player) => {
                    if (!bullet.active || player.hp <= 0 || (bullet.owner === player.id && (!bullet.bounces || bullet.bounces === 0))) return;
                    if (
                        bullet.x > player.x &&
                        bullet.x < player.x + player.width &&
                        bullet.y > player.y &&
                        bullet.y < player.y + player.height
                    ) {
                        if (player.blockActiveTime > 0) {
                            // Blocked! Reflect bullet
                            bullet.vx *= -1.5;
                            bullet.vy *= -1.5;
                            bullet.owner = player.id; // now owned by the blocking player
                            bullet.bounces = (bullet.bounces || 0) + 1;
                        } else {
                            const ownerPlayer = room.players.get(bullet.owner) || {};
                            const damageMult = ownerPlayer.damageMult || 1.0;
                            const knockbackMult = ownerPlayer.knockbackMult || 1.0;
                            const damage = getBulletDamage(bullet) * damageMult;
                            player.hp -= damage;
                            player.vx += bullet.vx * 0.4 * knockbackMult;
                            player.vy -= 4;
                            bullet.active = false;
                        }
                    }
                });

                room.bots.forEach((bot) => {
                    if (!bullet.active || bot.hp <= 0 || (bullet.owner === bot.id && (!bullet.bounces || bullet.bounces === 0))) return;
                    if (
                        bullet.x > bot.x &&
                        bullet.x < bot.x + bot.width &&
                        bullet.y > bot.y &&
                        bullet.y < bot.y + bot.height
                    ) {
                        const damage = getBulletDamage(bullet);
                        bot.hp -= damage;
                        bot.vx += bullet.vx * 0.4;
                        bot.vy -= 4;
                        bullet.active = false;
                    }
                });
            });

            room.bullets = room.bullets.filter((bullet) => bullet.active);

            // Round End Logic
            if (room.phase === 'playing') {
                if (room.mode === 'pvp') {
                    const alive = Array.from(room.players.values()).filter(p => p.hp > 0);
                    if (alive.length <= 1 && room.players.size > 1) {
                        room.phase = 'roundOver';
                        const winner = alive[0];
                        const allPlayers = Array.from(room.players.keys());
                        const loserId = allPlayers.find(id => id !== winner?.id);
                        
                        if (winner) {
                            room.roundWins[winner.id] = (room.roundWins[winner.id] || 0) + 1;
                            winner.coins += 10;
                        }

                        setTimeout(() => {
                            if (!rooms.has(room.code)) return;

                            if (winner) {
                                if (room.roundWins[winner.id] >= 2) {
                                    room.scores[winner.id] = (room.scores[winner.id] || 0) + 1;
                                    room.roundWins = {};
                                    
                                    if (room.scores[winner.id] >= 5) {
                                        room.phase = 'finished';
                                        winner.coins += 100;
                                    } else {
                                        room.phase = 'picking';
                                        room.loserToPick = loserId;
                                        room.availableCards = CARDS.sort(() => 0.5 - Math.random()).slice(0, 5);
                                    }
                                } else {
                                    resetRound(room);
                                }
                            } else {
                                resetRound(room);
                            }
                        }, 2000);
                    }
                } else if (room.mode === 'training') {
                    const player = Array.from(room.players.values())[0];
                    if (player && player.hp <= 0) {
                        room.phase = 'roundOver';
                        setTimeout(() => {
                            if (!rooms.has(room.code)) return;
                            room.phase = 'picking';
                            room.loserToPick = player.id;
                            room.availableCards = CARDS.sort(() => 0.5 - Math.random()).slice(0, 5);
                        }, 2000);
                    }
                }
            }
        }

        if (room.mode === 'training') {
            room.bots.forEach((bot, id) => {
                if (bot.hp <= 0 && bot.y > HEIGHT + 200) room.bots.delete(id);
            });
            if (room.phase === 'playing') {
                while (room.bots.size < 3) {
                    createBot(room);
                }
            }
        }

        // Handle Death by falling out of bounds
        if (room.mode === 'pvp' || room.mode === 'training') {
            room.players.forEach((player) => {
                if (player.y > HEIGHT + 100) player.hp = 0;
            });
        }
        
        io.to(room.code).emit('gameState', {
            code: room.code,
            mode: room.mode,
            phase: room.phase,
            players: Array.from(room.players.values()).map(p => ({
                ...p,
                roundWins: room.roundWins[p.id] || 0,
                score: room.scores[p.id] || 0
            })),
            bots: Array.from(room.bots.values()),
            bullets: room.bullets,
            platforms: room.platforms,
            maxPlayers: room.maxPlayers,
            loserToPick: room.loserToPick,
            availableCards: room.availableCards,
            messages: room.messages
        });
    });
}, TICK_RATE);

function resetRound(room) {
    if (room.phase === 'finished') return;
    room.phase = 'playing';
    room.bullets = [];
    room.players.forEach(p => {
        const spawn = randomSpawn();
        p.x = spawn.x;
        p.y = spawn.y;
        p.hp = p.maxHp;
        p.vx = 0;
        p.vy = 0;
        p.cooldown = 0;
    });
    if (room.mode === 'training') {
        room.bots.clear();
        room.botSeq = 0;
        for (let i = 0; i < 3; i++) {
            createBot(room);
        }
    }
}

function resetMatch(room) {
    room.scores = {};
    room.roundWins = {};
    room.players.forEach(p => {
        p.maxHp = MAX_HP;
        p.hp = MAX_HP;
        p.speed = 5;
        p.jumpPower = -16;
        p.maxCooldown = 15;
        p.damageMult = 1.0;
        p.bulletSize = 5;
        p.knockbackMult = 1.0;
        p.cards = [];
    });
    room.phase = 'waiting';
    emitRoomState(room);
}

server.listen(port, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${port}`);
});
