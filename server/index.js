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

const makeCard = (id, name, desc, category, color, emoji, effect) => ({ id, name, desc, category, color, emoji, effect });

const CARDS = [
    makeCard('empower', 'EMPOWER', '가드 후 다음 발이 강화됨', 'special', '#fcc419', '✨', (p) => { p.empowerCard = true; }),
    makeCard('radiance', 'RADIANCE', '가드 시 빛의 파동이 퍼짐', 'special', '#ffd43b', '🌟', (p) => { p.radianceCard = true; }),
    makeCard('scavenger', 'SCAVENGER', '피해를 주면 재장전이 빨라짐', 'utility', '#845ef7', '🧲', (p) => { p.scavengerCard = true; }),
    makeCard('poison', 'POISON', '적중한 적에게 독을 누적시킴', 'attack', '#2f9e44', '☠️', (p) => { p.poisonCard = (p.poisonCard || 0) + 1; }),
    makeCard('mayhem', 'MAYHEM', '도탄이 많아지고 탄환이 더 난폭해짐', 'utility', '#d9480f', '💥', (p) => { p.maxBounces = (p.maxBounces || 0) + 5; p.damageMult *= 0.85; }),
    makeCard('bombs_away', 'BOMBS AWAY', '도탄한 탄환이 폭발함', 'attack', '#fa5252', '💣', (p) => { p.bombsAwayCard = true; }),
    makeCard('pristine_persistence', 'PRISTINE PERSISTENCE', '체력이 가득할 때 더 강해짐', 'survival', '#4dabf7', '🫧', (p) => { p.pristineCard = true; }),
    makeCard('phoenix', 'PHOENIX', '한 번 죽어도 다시 살아남음', 'survival', '#f76707', '🐦‍🔥', (p) => { p.revives = (p.revives || 0) + 1; }),
    makeCard('quick_reload', 'QUICK RELOAD', '재사용 대기시간 감소', 'attack', '#74c0fc', '🔫', (p) => { p.maxCooldown = Math.max(2, p.maxCooldown - 5); }),
    makeCard('grow', 'GROW', '탄환이 날아갈수록 커지고 강해짐', 'attack', '#ffd43b', '🌱', (p) => { p.growCard = true; }),
    makeCard('supernova', 'SUPERNOVA', '탄환이 터질 때 작은 폭발이 남음', 'attack', '#ff922b', '🌟', (p) => { p.supernovaCard = true; }),
    makeCard('spray', 'SPRAY', '연사 속도는 빨라지고 한 발의 힘은 약해짐', 'attack', '#4dabf7', '🚿', (p) => { p.maxCooldown = 3; p.damageMult *= 0.3; }),
    makeCard('trickster', 'TRICKSTER', '발사가 조금 비틀려 예측이 어려워짐', 'utility', '#f06595', '🃏', (p) => { p.tricksterCard = true; }),
    makeCard('target_bounce', 'TARGET BOUNCE', '튀는 탄환이 다음 적을 노림', 'utility', '#20c997', '🎯', (p) => { p.targetBounceCard = true; }),
    makeCard('timed_detonation', 'TIMED DETONATION', '시간이 지나면 탄환이 폭발함', 'attack', '#fd7e14', '⏱️', (p) => { p.timedDetonationCard = true; }),
    makeCard('sneaky', 'SNEAKY', '탄환이 작고 빠르게 지나감', 'utility', '#adb5bd', '🥷', (p) => { p.sneakyCard = true; p.bulletSpeedMult = (p.bulletSpeedMult || 1) + 0.15; p.bulletSize = Math.max(2, p.bulletSize - 1); }),
    makeCard('homing', 'HOMING', '탄환이 가장 가까운 적을 추적함', 'utility', '#bac8ff', '🧲', (p) => { p.homingCard = true; }),
    makeCard('silence', 'SILENCE', '적중한 적의 발사를 잠시 막음', 'utility', '#9775fa', '🔇', (p) => { p.silenceCard = true; }),
    makeCard('taste_of_blood', 'TASTE OF BLOOD', '피해를 주면 이동 속도가 잠시 증가함', 'utility', '#c92a2a', '🩸', (p) => { p.bloodCard = true; }),
    makeCard('toxic_cloud', 'TOXIC CLOUD', '맞은 자리 주변에 독 구름이 남음', 'attack', '#40c057', '☁️', (p) => { p.toxicCloudCard = true; }),
    makeCard('echo', 'ECHO', '가드하면 반격 탄환이 하나 더 나감', 'utility', '#339af0', '📣', (p) => { p.echoCard = true; }),
    makeCard('shield_charge', 'SHIELD CHARGE', '가드 중 전진 돌진이 발생함', 'utility', '#228be6', '🛡️', (p) => { p.shieldChargeCard = true; }),
    makeCard('tactical_reload', 'TACTICAL RELOAD', '가드 후 재사용 대기시간이 크게 줄어듦', 'utility', '#74b816', '🧰', (p) => { p.tacticalReloadCard = true; }),
    makeCard('bouncy', 'BOUNCY', '탄환이 벽과 발판에 더 많이 튕김', 'utility', '#20c997', '🪃', (p) => { p.maxBounces = (p.maxBounces || 0) + 2; }),
    makeCard('barrage', 'BARRAGE', '한 번 쏠 때 여러 발이 퍼져 나감', 'attack', '#f08c00', '🌧️', (p) => { p.barrageCard = true; }),
    makeCard('refresh', 'REFRESH', '적중 시 쿨타임이 일부 회복됨', 'utility', '#63e6be', '♻️', (p) => { p.refreshCard = true; }),
    makeCard('healing_field', 'HEALING FIELD', '가드하면 회복 장판이 생김', 'survival', '#51cf66', '➕', (p) => { p.healingFieldCard = true; }),
    makeCard('shockwave', 'SHOCKWAVE', '가드가 주변 적을 밀쳐냄', 'utility', '#ff922b', '〰️', (p) => { p.shockwaveCard = true; }),
    makeCard('shields_up', 'SHIELDS UP', '가드 성능이 크게 향상됨', 'survival', '#3b5bdb', '🪖', (p) => { p.shieldsUpCard = true; p.blockCooldownMax = Math.max(40, (p.blockCooldownMax || 120) - 50); }),
    makeCard('teleport', 'TELEPORT', '가드하면 바라보는 방향으로 짧게 이동함', 'special', '#be4bdb', '🌀', (p) => { p.teleportCard = true; }),
    makeCard('explosive_bullet', 'EXPLOSIVE BULLET', '탄환이 맞는 순간 폭발함', 'attack', '#ff6b6b', '🧨', (p) => { p.explosiveCard = true; }),
    makeCard('decay', 'DECAY', '탄환이 오래 갈수록 힘을 잃음', 'attack', '#845ef7', '🕳️', (p) => { p.decayCard = true; }),
    makeCard('emp', 'EMP', '가드 시 주변 적을 마비시킴', 'special', '#00c2ff', '⚡', (p) => { p.empCard = true; }),
    makeCard('lifestealer', 'LIFESTEALER', '준 피해의 일부를 체력으로 돌려받음', 'survival', '#b197fc', '🧛', (p) => { p.lifestealCard = (p.lifestealCard || 0) + 0.3; }),
    makeCard('parasite', 'PARASITE', '적에게 피해를 줄수록 더 버팀', 'survival', '#74c0fc', '🪱', (p) => { p.parasiteCard = true; }),
    makeCard('big_bullet', 'BIG BULLET', '탄환이 커지고 더 무거워짐', 'attack', '#ffa94d', '💣', (p) => { p.bulletSize += 3; p.knockbackMult += 0.5; }),
    makeCard('combine', 'COMBINE', '공격이 크게 강해지지만 느려짐', 'attack', '#fab005', '⚙️', (p) => { p.damageMult *= 3.0; p.maxCooldown *= 3.0; }),
    makeCard('glass_cannon', 'GLASS CANNON', '공격력은 높지만 생존력은 낮아짐', 'attack', '#f06595', '🥃', (p) => { p.damageMult += 1.0; p.maxHp = Math.max(1, Math.floor(p.maxHp / 2)); p.hp = Math.min(p.hp, p.maxHp); }),
    makeCard('saw', 'SAW', '가드하면 톱날이 생겨 공격함', 'special', '#ff922b', '🪚', (p) => { p.sawCard = true; }),
    makeCard('thruster', 'THRUSTER', '반동과 이동 속도가 더 강해짐', 'movement', '#845ef7', '🚀', (p) => { p.speed += 1; p.knockbackMult += 0.3; }),
    makeCard('radar_shot', 'RADAR SHOT', '탄환이 적을 향해 조금 더 잘 꺾임', 'utility', '#12b886', '📡', (p) => { p.radarShotCard = true; }),
    makeCard('fastball', 'FASTBALL', '탄환 속도가 크게 증가함', 'attack', '#fff9db', '⚾', (p) => { p.bulletSpeedMult = (p.bulletSpeedMult || 1) + 1.0; }),
    makeCard('wind_up', 'WIND UP', '천천히 준비할수록 더 강한 한 발', 'attack', '#fab005', '🌀', (p) => { p.windUpCard = true; }),
    makeCard('careful_planning', 'CAREFUL PLANNING', '신중하게 쏘면 더 정확하고 강함', 'utility', '#c0eb75', '🧠', (p) => { p.carefulPlanningCard = true; }),
    makeCard('tank', 'TANK', '체력이 많아지지만 둔해짐', 'survival', '#228be6', '🛡️', (p) => { p.maxHp += 100; p.hp += 100; p.speed -= 2; }),
    makeCard('defender', 'DEFENDER', '가드 쿨타임이 짧아짐', 'survival', '#3b5bdb', '🧱', (p) => { p.maxHp += 30; p.hp += 30; p.blockCooldownMax = Math.max(40, (p.blockCooldownMax || 120) - 40); }),
    makeCard('burst', 'BURST', '발사할 때 점사로 나감', 'attack', '#74c0fc', '〰️', (p) => { p.burst = (p.burst || 0) + 2; }),
    makeCard('drill_ammo', 'DRILL AMMO', '탄환이 적을 관통함', 'attack', '#adb5bd', '🪛', (p) => { p.drillAmmoCard = true; }),
    makeCard('implode', 'IMPLODE', '가드하면 적을 끌어당김', 'utility', '#ae3ec9', '🕳️', (p) => { p.implodeCard = true; }),
    makeCard('static_field', 'STATIC FIELD', '가드하면 정전기 장판이 생김', 'utility', '#339af0', '🌩️', (p) => { p.staticFieldCard = true; }),
    makeCard('leech', 'LEECH', '피해를 줄 때 체력을 조금 회복함', 'survival', '#40c057', '🪱', (p) => { p.leechCard = true; }),
    makeCard('huge', 'HUGE', '플레이어와 탄환이 전부 커짐', 'special', '#1098ad', '🐘', (p) => { p.width *= 1.5; p.height *= 1.5; p.bulletSize += 10; }),
    makeCard('chase', 'CHASE', '탄환이 적을 더 집요하게 좇음', 'utility', '#ff6b6b', '🐾', (p) => { p.chaseCard = true; }),
    makeCard('quick_shot', 'QUICK SHOT', '발사 속도가 더 빨라짐', 'attack', '#ffd43b', '⚡', (p) => { p.maxCooldown = Math.max(2, p.maxCooldown - 7); }),
    makeCard('steady_shot', 'STEADY SHOT', '탄환이 안정적으로 멀리 날아감', 'attack', '#ffe8cc', '🎯', (p) => { p.steadyShotCard = true; }),
    makeCard('ritual_countdown', 'RITUAL COUNTDOWN', '가만히 있을수록 다음 발사가 강해짐', 'special', '#f06595', '⌛', (p) => { p.ritualCountdownCard = true; }),
    makeCard('chilling_presence', 'CHILLING PRESENCE', '주변 적을 서서히 느리게 함', 'utility', '#4dabf7', '🧊', (p) => { p.chillingPresenceCard = true; }),
    makeCard('demonic_pact', 'DEMONIC PACT', '발사 시 체력을 약간 태워 공격력을 올림', 'special', '#ff0000', '😈', (p) => { p.demonicPactCard = true; }),
    makeCard('brawler', 'BRAWLER', '탄환이 더 묵직하고 가까운 싸움에 강함', 'attack', '#e03131', '🥊', (p) => { p.damageMult += 0.5; p.maxHp += 20; p.hp += 20; }),
    makeCard('overpower', 'OVERPOWER', '상대가 약할수록 더 강해짐', 'attack', '#c92a2a', '👊', (p) => { p.overpowerCard = true; }),
    makeCard('frost_slam', 'FROST SLAM', '가드 시 얼음 충격파가 퍼짐', 'utility', '#74c0fc', '❄️', (p) => { p.frostSlamCard = true; }),
    makeCard('cold_bullets', 'COLD BULLETS', '적중한 적의 이동을 둔화시킴', 'utility', '#99e9f2', '❄️', (p) => { p.coldCard = true; }),
    makeCard('dazzle', 'DAZZLE', '적중 시 짧게 기절시킴', 'utility', '#ae3ec9', '✨', (p) => { p.dazzleCard = true; }),
    makeCard('ricochet', 'RICOCHET', '탄환이 벽을 한 번 더 세게 튕김', 'utility', '#ffd43b', '↩️', (p) => { p.maxBounces = (p.maxBounces || 0) + 1; p.ricochetCard = true; }),
    makeCard('remote', 'REMOTE', '탄환을 조금 더 조종할 수 있음', 'special', '#868e96', '🎮', (p) => { p.remoteCard = true; }),
    makeCard('fast_forward', 'FAST FORWARD', '탄환 속도는 더 빠르지만 수명은 짧아짐', 'attack', '#fab005', '⏩', (p) => { p.fastForwardCard = true; p.bulletSpeedMult = (p.bulletSpeedMult || 1) + 0.4; }),
    makeCard('buckshot', 'BUCKSHOT', '여러 발이 퍼져 나가는 산탄', 'special', '#f08c00', '🎇', (p) => { p.buckshot = (p.buckshot || 0) + 3; })
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
        zones: [],
        platforms,
        maxPlayers,
        botSeq: 0,
        tickCount: 0,
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

function applyCardState(player) {
    player.blockCooldownMax = 120;
    player.bulletSpeedMult = 1.0;
    player.revives = 0;
    player.empowerCard = false;
    player.empoweredNextShot = false;
    player.radianceCard = false;
    player.scavengerCard = false;
    player.bombsAwayCard = false;
    player.pristineCard = false;
    player.supernovaCard = false;
    player.tricksterCard = false;
    player.targetBounceCard = false;
    player.timedDetonationCard = false;
    player.sneakyCard = false;
    player.homingCard = false;
    player.silenceCard = false;
    player.bloodCard = false;
    player.toxicCloudCard = false;
    player.echoCard = false;
    player.shieldChargeCard = false;
    player.tacticalReloadCard = false;
    player.refreshCard = false;
    player.healingFieldCard = false;
    player.shockwaveCard = false;
    player.shieldsUpCard = false;
    player.teleportCard = false;
    player.explosiveCard = false;
    player.decayCard = false;
    player.empCard = false;
    player.poisonCard = 0;
    player.activePoison = 0;
    player.growCard = false;
    player.parasiteCard = false;
    player.bombsAwayCard = false;
    player.barrageCard = false;
    player.leechCard = false;
    player.chaseCard = false;
    player.quickShotCard = false;
    player.steadyShotCard = false;
    player.ritualCountdownCard = false;
    player.chillingPresenceCard = false;
    player.demonicPactCard = false;
    player.overpowerCard = false;
    player.frostSlamCard = false;
    player.coldCard = false;
    player.dazzleCard = false;
    player.ricochetCard = false;
    player.remoteCard = false;
    player.fastForwardCard = false;
    player.windUpCard = false;
    player.carefulPlanningCard = false;
    player.buckshot = 0;
    player.burst = 0;
    player.maxBounces = 0;
    player.drillAmmoCard = false;
    player.implodeCard = false;
    player.staticFieldCard = false;
    player.sawCard = false;
    player.radarShotCard = false;
    player.godModeTimer = 0;
    player.windupCharge = 0;
    player.stillTicks = 0;
    player.silencedTimer = 0;
    player.echoCooldown = 0;
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

    applyCardState(player);

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

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function spawnBullet(room, player, angle, extra = {}) {
    const speedMult = (player.bulletSpeedMult || 1) * (extra.speedMult || 1);
    const baseSpeed = 15 * speedMult;
    const shotCharge = clamp(player.windupCharge || 0, 0, 60) / 60;
    const carefulBonus = player.carefulPlanningCard ? 1 + (player.stillTicks >= 20 ? 0.2 : 0) : 1;
    const windUpBonus = player.windUpCard ? 1 + shotCharge * 0.75 : 1;
    const pristineBonus = player.pristineCard && player.hp >= player.maxHp ? 1.2 : 1;
    const damageMult = (player.damageMult || 1) * (extra.damageMult || 1) * carefulBonus * windUpBonus * pristineBonus;
    const spreadAngle = (player.tricksterCard ? (Math.random() - 0.5) * 0.16 : 0) + (extra.spread || 0);
    const finalAngle = angle + spreadAngle;
    const bullet = {
        x: player.x + player.width / 2,
        y: player.y + player.height / 2,
        vx: Math.cos(finalAngle) * baseSpeed,
        vy: Math.sin(finalAngle) * baseSpeed,
        color: player.color,
        owner: player.id,
        active: true,
        life: extra.life || (player.fastForwardCard ? 50 : 80),
        startX: player.x + player.width / 2,
        startY: player.y + player.height / 2,
        size: Math.max(2, (player.bulletSize || 5) + (extra.sizeBonus || 0)),
        damage: (extra.damage || 20) * damageMult,
        knockback: (extra.knockback || 10) * (player.knockbackMult || 1),
        bounces: 0,
        maxBounces: (player.maxBounces || 0) + (extra.maxBounces || 0),
        homingCard: player.homingCard || player.chaseCard || player.radarShotCard,
        targetBounceCard: player.targetBounceCard,
        timedDetonationCard: player.timedDetonationCard,
        supernovaCard: player.supernovaCard,
        explosiveCard: player.explosiveCard,
        bombsAwayCard: player.bombsAwayCard,
        decayCard: player.decayCard,
        remoteCard: player.remoteCard,
        drillAmmoCard: player.drillAmmoCard,
        ricochetCard: player.ricochetCard,
        chaseCard: player.chaseCard,
        fastForwardCard: player.fastForwardCard,
        growCard: player.growCard,
        silentCard: player.silenceCard,
        coldCard: player.coldCard,
        poisonCard: player.poisonCard,
        rayCard: player.radianceCard,
        explodeRadius: extra.explodeRadius || 85,
        ownerMouse: { x: player.mouseTarget.x, y: player.mouseTarget.y },
        pierce: extra.pierce || (player.drillAmmoCard ? 1 : 0),
        decayRate: player.decayCard ? 0.985 : 1,
    };

    if (player.targetBounceCard) bullet.maxBounces += 1;
    if (player.ricochetCard) bullet.maxBounces += 1;
    if (player.fastForwardCard) bullet.vx *= 1.25, bullet.vy *= 1.25;
    return bullet;
}

function createZone(room, zone) {
    room.zones.push(zone);
}

function applyExplosion(room, x, y, ownerId, damage, radius = 90, knockback = 14) {
    room.players.forEach((target) => {
        if (target.hp <= 0) return;
        const dx = target.x + target.width / 2 - x;
        const dy = target.y + target.height / 2 - y;
        const distance = Math.hypot(dx, dy);
        if (distance > radius || distance === 0) return;
        const power = 1 - distance / radius;
        target.hp -= damage * power;
        target.vx += (dx / distance) * knockback * power;
        target.vy += (dy / distance) * knockback * power;
        if (target.hp <= 0) checkPlayerDeath(target.id, ownerId);
    });

    room.bots.forEach((target) => {
        if (target.hp <= 0) return;
        const dx = target.x + target.width / 2 - x;
        const dy = target.y + target.height / 2 - y;
        const distance = Math.hypot(dx, dy);
        if (distance > radius || distance === 0) return;
        const power = 1 - distance / radius;
        target.hp -= damage * power;
        target.vx += (dx / distance) * knockback * power;
        target.vy += (dy / distance) * knockback * power;
    });
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

function checkPlayerDeath(playerId, killerId) {
    for (const room of rooms.values()) {
        const player = room.players.get(playerId);
        if (!player) continue;
        player.hp = 0;
        player.vx = 0;
        player.vy = 0;
        player.blockActiveTime = 0;
        player.blockCooldown = Math.max(player.blockCooldown || 0, 30);
        player.silencedTimer = 0;
        player.activePoison = 0;
        return true;
    }
    return false;
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
            room.loserToPick = null;
            room.phase = 'playing';
            resetRound(room);
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
        if (!player || player.hp <= 0 || player.cooldown > 0 || player.silencedTimer > 0) return;

        const cx = player.x + player.width / 2;
        const cy = player.y + player.height / 2;
        const angle = Math.atan2(player.mouseTarget.y - cy, player.mouseTarget.x - cx);
        const fireCount = player.buckshot > 0 ? player.buckshot + 1 : (player.barrageCard ? 3 : 1);
        const burstCount = player.burst > 0 ? 3 : 1;
        const totalShots = fireCount * burstCount;
        const recoil = player.carefulPlanningCard ? 1.2 : 2;

        for (let i = 0; i < totalShots; i += 1) {
            const spread = totalShots > 1 ? (i - (totalShots - 1) / 2) * 0.08 : 0;
            room.bullets.push(spawnBullet(room, player, angle, { spread }));
        }

        if (player.demonicPactCard) player.hp = Math.max(1, player.hp - 2);
        if (player.ritualCountdownCard) player.windupCharge = clamp((player.windupCharge || 0) + 8, 0, 60);
        player.vx -= Math.cos(angle) * recoil;
        player.cooldown = Math.max(2, player.maxCooldown || 15);
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
        room.tickCount += 1;
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

                if (player.bloodTimer > 0) player.bloodTimer -= 1;
                if (player.coldTimer > 0) player.coldTimer -= 1;
                if (player.dazzleTimer > 0) player.dazzleTimer -= 1;
                if (player.silencedTimer > 0) player.silencedTimer -= 1;
                if (player.echoCooldown > 0) player.echoCooldown -= 1;
                if (player.activePoison > 0 && room.tickCount % 30 === 0) {
                    player.hp -= 1;
                    player.activePoison -= 1;
                    checkPlayerDeath(player.id, null);
                }
                player.stillTicks = (Math.abs(player.vx) < 0.25 && Math.abs(player.vy) < 1.5) ? (player.stillTicks || 0) + 1 : 0;
                player.windupCharge = clamp((player.windupCharge || 0) + (player.stillTicks > 0 ? 1 : -2), 0, 60);

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
                    player.blockActiveTime = player.shieldsUpCard ? 30 : 20;
                    player.blockCooldown = player.blockCooldownMax || 120;
                    const centerX = player.x + player.width / 2;
                    const centerY = player.y + player.height / 2;
                    const aimDx = player.mouseTarget.x - centerX;
                    const aimDy = player.mouseTarget.y - centerY;
                    const aimMag = Math.hypot(aimDx, aimDy) || 1;
                    const dirX = aimDx / aimMag;
                    const dirY = aimDy / aimMag;

                    if (player.shieldChargeCard) {
                        player.vx += dirX * 5;
                        player.vy += dirY * 2;
                    }
                    if (player.teleportCard) {
                        const nextX = clamp(centerX + dirX * 110, 0, WIDTH - player.width);
                        const nextY = clamp(centerY + dirY * 50, 0, HEIGHT - player.height);
                        player.x = nextX;
                        player.y = nextY;
                    }
                    if (player.tacticalReloadCard) player.cooldown = Math.max(0, player.cooldown - 8);
                    if (player.scavengerCard) player.cooldown = Math.max(0, player.cooldown - 4);
                    if (player.radianceCard) createZone(room, { type: 'radiance', x: centerX, y: centerY, radius: 100, duration: 18, owner: player.id });
                    if (player.healingFieldCard) createZone(room, { type: 'heal', x: centerX, y: centerY, radius: 120, duration: 60, owner: player.id });
                    if (player.shockwaveCard) createZone(room, { type: 'shockwave', x: centerX, y: centerY, radius: 110, duration: 1, owner: player.id });
                    if (player.implodeCard) createZone(room, { type: 'implode', x: centerX, y: centerY, radius: 140, duration: 30, owner: player.id });
                    if (player.staticFieldCard) createZone(room, { type: 'static', x: centerX, y: centerY, radius: 130, duration: 45, owner: player.id });
                    if (player.empCard) createZone(room, { type: 'emp', x: centerX, y: centerY, radius: 120, duration: 12, owner: player.id });
                    if (player.frostSlamCard) createZone(room, { type: 'frost', x: centerX, y: centerY, radius: 120, duration: 14, owner: player.id });
                    if (player.echoCard) player.echoCardReady = true;
                    if (player.sawCard) room.bullets.push(spawnBullet(room, player, Math.atan2(dirY, dirX), { speedMult: 0.8, damageMult: 0.7, life: 60, maxBounces: 3 }));
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

                if (bullet.remoteCard || bullet.homingCard || bullet.chaseCard || bullet.targetBounceCard) {
                    let target = null;
                    let closestDist = Infinity;
                    const ownerId = bullet.owner;
                    const ownerPlayer = room.players.get(ownerId);
                    const ownerMouse = bullet.ownerMouse || ownerPlayer?.mouseTarget;

                    if (bullet.remoteCard && ownerMouse) {
                        const tx = ownerMouse.x - bullet.x;
                        const ty = ownerMouse.y - bullet.y;
                        const dist = Math.hypot(tx, ty) || 1;
                        const steer = 0.08;
                        const speed = Math.hypot(bullet.vx, bullet.vy) || 1;
                        bullet.vx = bullet.vx * (1 - steer) + (tx / dist) * speed * steer;
                        bullet.vy = bullet.vy * (1 - steer) + (ty / dist) * speed * steer;
                    }

                    room.players.forEach((player) => {
                        if (player.hp <= 0 || player.id === ownerId) return;
                        const dx = (player.x + player.width / 2) - bullet.x;
                        const dy = (player.y + player.height / 2) - bullet.y;
                        const dist = Math.hypot(dx, dy);
                        if (dist < closestDist) { closestDist = dist; target = player; }
                    });
                    room.bots.forEach((bot) => {
                        if (bot.hp <= 0 || bot.id === ownerId) return;
                        const dx = (bot.x + bot.width / 2) - bullet.x;
                        const dy = (bot.y + bot.height / 2) - bullet.y;
                        const dist = Math.hypot(dx, dy);
                        if (dist < closestDist) { closestDist = dist; target = bot; }
                    });

                    if (target) {
                        const tx = (target.x + target.width / 2) - bullet.x;
                        const ty = (target.y + target.height / 2) - bullet.y;
                        const dist = Math.hypot(tx, ty) || 1;
                        const speed = Math.hypot(bullet.vx, bullet.vy) || 1;
                        const steer = bullet.homingCard ? 0.08 : 0.05;
                        bullet.vx = bullet.vx * (1 - steer) + (tx / dist) * speed * steer;
                        bullet.vy = bullet.vy * (1 - steer) + (ty / dist) * speed * steer;
                    }
                }

                bullet.x += bullet.vx;
                bullet.y += bullet.vy;
                bullet.life -= 1;

                if (bullet.growCard) {
                    bullet.damage += 0.05;
                    bullet.size += 0.01;
                }
                if (bullet.decayCard) {
                    bullet.vx *= bullet.decayRate;
                    bullet.vy *= bullet.decayRate;
                    bullet.damage *= 0.99;
                }

                if (bullet.life <= 0) {
                    if (bullet.explosiveCard || bullet.supernovaCard || bullet.bombsAwayCard) {
                        applyExplosion(room, bullet.x, bullet.y, bullet.owner, bullet.damage * 0.6, bullet.explodeRadius, 16);
                    }
                    bullet.active = false;
                    return;
                }

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
                    if (bullet.explosiveCard || bullet.supernovaCard || bullet.bombsAwayCard) {
                        applyExplosion(room, bullet.x, bullet.y, bullet.owner, bullet.damage * 0.6, bullet.explodeRadius, 16);
                    }
                    bullet.active = false;
                    return;
                }

                for (const plat of room.platforms) {
                    if (!bullet.active || !bulletHitsRect(bullet, plat)) continue;
                    const prevX = bullet.x - bullet.vx;
                    const prevY = bullet.y - bullet.vy;
                    const hitFromTopOrBottom = (prevY < plat.y || prevY > plat.y + plat.height);

                    if (bullet.maxBounces > 0 && (bullet.bounces || 0) < bullet.maxBounces) {
                        if (hitFromTopOrBottom) bullet.vy *= -1;
                        else bullet.vx *= -1;
                        bullet.bounces = (bullet.bounces || 0) + 1;
                        if (bullet.targetBounceCard) bullet.homingCard = true;
                        if (bullet.bombsAwayCard) applyExplosion(room, bullet.x, bullet.y, bullet.owner, bullet.damage * 0.35, 70, 12);
                    } else {
                        if (bullet.explosiveCard || bullet.supernovaCard || bullet.bombsAwayCard) {
                            applyExplosion(room, bullet.x, bullet.y, bullet.owner, bullet.damage * 0.7, bullet.explodeRadius, 16);
                        }
                        bullet.active = false;
                        return;
                    }
                }

                room.players.forEach((player) => {
                    if (!bullet.active || player.hp <= 0 || bullet.owner === player.id) return;
                    if (!(
                        bullet.x > player.x &&
                        bullet.x < player.x + player.width &&
                        bullet.y > player.y &&
                        bullet.y < player.y + player.height
                    )) return;

                    if (player.blockActiveTime > 0) {
                        const reflectedOwnerId = bullet.owner;
                        bullet.vx *= -1.35;
                        bullet.vy *= -1.35;
                        bullet.owner = player.id;
                        bullet.ownerMouse = { x: player.mouseTarget.x, y: player.mouseTarget.y };
                        bullet.bounces = (bullet.bounces || 0) + 1;
                        if (player.echoCard && !player.echoCooldown) {
                            player.echoCooldown = 30;
                            const centerX = player.x + player.width / 2;
                            const centerY = player.y + player.height / 2;
                            const ownerPlayer = room.players.get(reflectedOwnerId) || null;
                            if (ownerPlayer) {
                                const ax = ownerPlayer.x + ownerPlayer.width / 2;
                                const ay = ownerPlayer.y + ownerPlayer.height / 2;
                                room.bullets.push(spawnBullet(room, player, Math.atan2(ay - centerY, ax - centerX), { damageMult: 0.65, speedMult: 1.1 }));
                            }
                        }
                    } else {
                        const ownerPlayer = room.players.get(bullet.owner) || {};
                        const damageMult = ownerPlayer.damageMult || 1.0;
                        const knockbackMult = ownerPlayer.knockbackMult || 1.0;
                        const hitDamage = (bullet.damage || getBulletDamage(bullet)) * damageMult;
                        player.hp -= hitDamage;
                        player.vx += bullet.vx * 0.4 * knockbackMult;
                        player.vy -= 4;
                        if (bullet.poisonCard > 0) player.activePoison += 10 * bullet.poisonCard;
                        if (bullet.coldCard) player.coldTimer = Math.max(player.coldTimer || 0, 60);
                        if (bullet.silentCard) player.silencedTimer = Math.max(player.silencedTimer || 0, 60);
                        if (ownerPlayer.bloodCard) ownerPlayer.bloodTimer = 45;
                        if (ownerPlayer.lifestealCard) ownerPlayer.hp = Math.min(ownerPlayer.maxHp, ownerPlayer.hp + hitDamage * ownerPlayer.lifestealCard);
                        if (ownerPlayer.leechCard) ownerPlayer.hp = Math.min(ownerPlayer.maxHp, ownerPlayer.hp + 2);
                        if (ownerPlayer.scavengerCard) ownerPlayer.cooldown = Math.max(0, ownerPlayer.cooldown - 4);
                        if (ownerPlayer.refreshCard) ownerPlayer.cooldown = Math.max(0, ownerPlayer.cooldown - 8);
                        if (ownerPlayer.parasiteCard) ownerPlayer.maxHp += 1;
                        if (ownerPlayer.radianceCard) createZone(room, { type: 'radiance', x: bullet.x, y: bullet.y, radius: 70, duration: 8, owner: bullet.owner });
                        if (bullet.toxicCloudCard) createZone(room, { type: 'toxic', x: bullet.x, y: bullet.y, radius: 75, duration: 35, owner: bullet.owner });
                        if (bullet.explosiveCard || bullet.supernovaCard) applyExplosion(room, bullet.x, bullet.y, bullet.owner, hitDamage * 0.55, bullet.explodeRadius, 16);
                        if (player.hp <= 0) {
                            if (player.revives > 0) {
                                player.revives -= 1;
                                player.hp = player.maxHp;
                            } else {
                                checkPlayerDeath(player.id, bullet.owner);
                            }
                        }
                        if (bullet.drillAmmoCard && (bullet.pierce || 0) > 0) {
                            bullet.pierce -= 1;
                        } else {
                            bullet.active = false;
                        }
                    }
                });

                room.bots.forEach((bot) => {
                    if (!bullet.active || bot.hp <= 0 || bullet.owner === bot.id) return;
                    if (!(
                        bullet.x > bot.x &&
                        bullet.x < bot.x + bot.width &&
                        bullet.y > bot.y &&
                        bullet.y < bot.y + bot.height
                    )) return;

                    const hitDamage = bullet.damage || getBulletDamage(bullet);
                    bot.hp -= hitDamage;
                    bot.vx += bullet.vx * 0.4;
                    bot.vy -= 4;
                    if (bullet.toxicCloudCard) createZone(room, { type: 'toxic', x: bullet.x, y: bullet.y, radius: 75, duration: 35, owner: bullet.owner });
                    if (bullet.explosiveCard || bullet.supernovaCard) applyExplosion(room, bullet.x, bullet.y, bullet.owner, hitDamage * 0.55, bullet.explodeRadius, 16);
                    if (bullet.drillAmmoCard && (bullet.pierce || 0) > 0) {
                        bullet.pierce -= 1;
                    } else {
                        bullet.active = false;
                    }
                });
            });

            room.bullets = room.bullets.filter((bullet) => bullet.active);

            room.zones.forEach((zone) => {
                zone.duration -= 1;
                const applyToEntity = (entity, setSlow = false) => {
                    if (entity.hp <= 0) return;
                    const dx = (entity.x + entity.width / 2) - zone.x;
                    const dy = (entity.y + entity.height / 2) - zone.y;
                    const distance = Math.hypot(dx, dy);
                    if (distance > zone.radius) return;
                    const power = 1 - (distance / zone.radius);
                    if (zone.type === 'heal') {
                        entity.hp = Math.min(entity.maxHp || MAX_HP, entity.hp + 0.8 * power);
                    } else if (zone.type === 'toxic') {
                        entity.hp -= 0.7 * power;
                        entity.activePoison = (entity.activePoison || 0) + 1;
                    } else if (zone.type === 'static' || zone.type === 'emp') {
                        entity.silencedTimer = Math.max(entity.silencedTimer || 0, 25);
                        entity.dazzleTimer = Math.max(entity.dazzleTimer || 0, 20);
                    } else if (zone.type === 'frost') {
                        entity.coldTimer = Math.max(entity.coldTimer || 0, 50);
                    } else if (zone.type === 'implode') {
                        entity.vx += (-dx / Math.max(distance, 1)) * 0.35 * power;
                        entity.vy += (-dy / Math.max(distance, 1)) * 0.35 * power;
                    } else if (zone.type === 'shockwave') {
                        entity.vx += (dx / Math.max(distance, 1)) * 6 * power;
                        entity.vy += (dy / Math.max(distance, 1)) * 4 * power;
                    } else if (zone.type === 'radiance') {
                        entity.hp = Math.min(entity.maxHp || MAX_HP, entity.hp + 0.25 * power);
                    }
                    if (setSlow) entity.vx *= 0.92;
                };

                room.players.forEach((player) => applyToEntity(player, zone.type === 'chilling'));
                room.bots.forEach((bot) => applyToEntity(bot, zone.type === 'chilling'));
            });
            room.zones = room.zones.filter((zone) => zone.duration > 0);

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
    room.zones = [];
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
        applyCardState(p);
    });
    room.bullets = [];
    room.zones = [];
    room.phase = 'waiting';
    emitRoomState(room);
}

server.listen(port, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${port}`);
});
