const socket = io();

const lobbyScreen = document.getElementById('lobby');
const gameScreen = document.getElementById('game');
const avatarGrid = document.getElementById('avatarGrid');
const lobbyStatus = document.getElementById('lobbyStatus');
const roomInfo = document.getElementById('roomInfo');
const roomCodeInput = document.getElementById('roomCodeInput');
const nicknameInput = document.getElementById('nicknameInput');
const roomCodeDisplay = document.getElementById('roomCodeDisplay');
const playerCountDisplay = document.getElementById('playerCountDisplay');
const createRoomBtn = document.getElementById('createRoomBtn');
const joinRoomBtn = document.getElementById('joinRoomBtn');
const soloBtn = document.getElementById('soloBtn');
const leaveBtn = document.getElementById('leaveBtn');

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const inputs = { left: false, right: false, jump: false };
const mousePos = { x: 0, y: 0 };

const avatars = [
    { id: 'blue', name: 'Blue', primary: '#4dabf7', secondary: '#74c0fc', image: '/assets/avatars/blue.png' },
    { id: 'green', name: 'Green', primary: '#51cf66', secondary: '#8ce99a', image: '/assets/avatars/green.png' },
    { id: 'purple', name: 'Purple', primary: '#845ef7', secondary: '#b197fc', image: '/assets/avatars/purple.png' },
    { id: 'orange', name: 'Orange', primary: '#ffa94d', secondary: '#ffd8a8', image: '/assets/avatars/orange.png' },
];

const avatarMap = new Map(avatars.map((avatar) => [avatar.id, avatar]));
avatarMap.set('bot', { id: 'bot', name: 'Bot', primary: '#adb5bd', secondary: '#dee2e6' });
const avatarImages = new Map();

avatars.forEach((avatar) => {
    const img = new Image();
    img.src = avatar.image;
    avatarImages.set(avatar.id, img);
});

let selectedAvatarId = null;
let myId = null;
let currentRoomCode = null;
let latestState = null;

function setStatus(message = '') {
    lobbyStatus.textContent = message;
}

function showLobby() {
    lobbyScreen.classList.add('active');
    gameScreen.classList.remove('active');
}

function showGame() {
    lobbyScreen.classList.remove('active');
    gameScreen.classList.add('active');
}

function renderAvatarGrid() {
    avatarGrid.innerHTML = '';
    avatars.forEach((avatar) => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'avatar-card';
        card.dataset.avatarId = avatar.id;
        card.title = avatar.name;

        const img = document.createElement('img');
        img.className = 'avatar-img';
        img.src = avatar.image;
        img.alt = avatar.name;

        card.appendChild(img);
        card.addEventListener('click', () => selectAvatar(avatar.id));
        avatarGrid.appendChild(card);
    });
}

function updateAvatarCards(taken = []) {
    const cards = avatarGrid.querySelectorAll('.avatar-card');
    cards.forEach((card) => {
        const id = card.dataset.avatarId;
        const isTaken = taken.includes(id) && id !== selectedAvatarId;
        card.classList.toggle('selected', id === selectedAvatarId);
        card.classList.toggle('taken', isTaken);
        card.disabled = isTaken;
    });
}

roomCodeInput.addEventListener('input', () => {
    roomCodeInput.value = roomCodeInput.value.replace(/[^0-9]/g, '').slice(0, 6);
});

function selectAvatar(id) {
    selectedAvatarId = id;
    updateAvatarCards(latestState?.takenAvatars ?? []);
    if (currentRoomCode) {
        socket.emit('selectAvatar', { avatarId: selectedAvatarId }, (response) => {
            if (response?.ok === false) {
                setStatus(response.message || '캐릭터 선택에 실패했습니다.');
            }
        });
    }
}

function ensureAvatarSelected() {
    if (!selectedAvatarId) {
        setStatus('캐릭터를 먼저 선택해 주세요.');
        return false;
    }
    return true;
}

createRoomBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    socket.emit('createRoom', { avatarId: selectedAvatarId, nickname: nicknameInput.value.trim() }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '방 생성에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `초대 코드: ${response.code}`;
        showGame();
    });
});

joinRoomBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    const code = roomCodeInput.value.trim();
    if (!/^[0-9]{6}$/.test(code)) {
        setStatus('6자리 숫자 코드를 입력해 주세요.');
        return;
    }
    socket.emit('joinRoom', { code, avatarId: selectedAvatarId, nickname: nicknameInput.value.trim() }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '방 참가에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `입장 완료: ${response.code}`;
        showGame();
    });
});

soloBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    socket.emit('startSolo', { avatarId: selectedAvatarId, nickname: nicknameInput.value.trim() }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '혼자하기 시작에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `혼자하기 시작: ${response.code}`;
        showGame();
    });
});

leaveBtn.addEventListener('click', () => {
    socket.emit('leaveRoom');
    currentRoomCode = null;
    latestState = null;
    setStatus('');
    roomInfo.textContent = '';
    showLobby();
});

window.addEventListener('keydown', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    if (event.code === 'KeyA') inputs.left = true;
    if (event.code === 'KeyD') inputs.right = true;
    if (event.code === 'Space') inputs.jump = true;
    socket.emit('input', inputs);
});

window.addEventListener('keyup', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    if (event.code === 'KeyA') inputs.left = false;
    if (event.code === 'KeyD') inputs.right = false;
    if (event.code === 'Space') inputs.jump = false;
    socket.emit('input', inputs);
});

canvas.addEventListener('mousemove', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    const rect = canvas.getBoundingClientRect();
    mousePos.x = event.clientX - rect.left;
    mousePos.y = event.clientY - rect.top;
    socket.emit('mouseMove', mousePos);
});

canvas.addEventListener('mousedown', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    if (event.button === 0) {
        socket.emit('shoot');
    }
});

socket.on('connect', () => {
    myId = socket.id;
});

socket.on('roomState', (state) => {
    latestState = state;
    updateAvatarCards(state.takenAvatars || []);
    if (state.code) {
        roomCodeDisplay.textContent = `방 코드: ${state.code}`;
        playerCountDisplay.textContent = `접속 인원: ${state.players.length}/${state.maxPlayers}`;
    }
});

socket.on('gameState', (state) => {
    latestState = state;
    drawState(state);
});

function drawAvatar(entity) {
    const avatar = avatarMap.get(entity.avatarId) || avatarMap.get('bot');
    const img = avatarImages.get(avatar.id);
    if (img && img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, entity.x, entity.y, entity.width, entity.height);
        return;
    }

    ctx.fillStyle = avatar.primary;
    ctx.fillRect(entity.x, entity.y, entity.width, entity.height);

    ctx.fillStyle = avatar.secondary;
    ctx.fillRect(entity.x + 4, entity.y + 4, entity.width - 8, entity.height - 8);

    ctx.fillStyle = '#111';
    ctx.beginPath();
    ctx.arc(entity.x + 10, entity.y + 12, 3, 0, Math.PI * 2);
    ctx.arc(entity.x + entity.width - 10, entity.y + 12, 3, 0, Math.PI * 2);
    ctx.fill();
}

function drawState(state) {
    if (!gameScreen.classList.contains('active')) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#2b2f3a';
    state.platforms.forEach((platform) => {
        ctx.fillRect(platform.x, platform.y, platform.width, platform.height);
    });

    state.players.forEach((player) => {
        if (player.hp <= 0) return;
        drawAvatar(player);

        ctx.fillStyle = '#f03e3e';
        ctx.fillRect(player.x, player.y - 12, player.width, 5);
        ctx.fillStyle = '#37b24d';
        ctx.fillRect(player.x, player.y - 12, player.width * (player.hp / 100), 5);

        if (player.id === myId) {
            ctx.fillStyle = '#fff';
            ctx.font = '10px sans-serif';
            ctx.fillText('Me', player.x + 6, player.y - 16);
        }

        const cx = player.x + player.width / 2;
        const cy = player.y + player.height / 2;
        const angle = Math.atan2(player.mouseTarget.y - cy, player.mouseTarget.x - cx);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(angle) * 26, cy + Math.sin(angle) * 26);
        ctx.stroke();
    });

    state.bots.forEach((bot) => {
        if (bot.hp <= 0) return;
        drawAvatar(bot);
    });

    state.bullets.forEach((bullet) => {
        ctx.beginPath();
        ctx.arc(bullet.x, bullet.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = bullet.color;
        ctx.fill();
    });
}

renderAvatarGrid();
showLobby();
