const socket = io();

const lobbyScreen = document.getElementById('lobby');
const roomLobbyScreen = document.getElementById('roomLobby');
const gameScreen = document.getElementById('game');
const lobbyStatus = document.getElementById('lobbyStatus');
const roomInfo = document.getElementById('roomInfo');
const roomCodeInput = document.getElementById('roomCodeInput');
const nicknameInput = document.getElementById('nicknameInput');
const roomCodeDisplay = document.getElementById('roomCodeDisplay');
const playerCountDisplay = document.getElementById('playerCountDisplay');
const roomLobbyCode = document.getElementById('roomLobbyCode');
const roomLobbyCount = document.getElementById('roomLobbyCount');
const playerList = document.getElementById('playerList');
const createRoomBtn = document.getElementById('createRoomBtn');
const joinRoomBtn = document.getElementById('joinRoomBtn');
const soloBtn = document.getElementById('soloBtn');
const enterGameBtn = document.getElementById('enterGameBtn');
const roomLobbyLeaveBtn = document.getElementById('roomLobbyLeaveBtn');
const leaveBtn = document.getElementById('leaveBtn');

const chatInput = document.getElementById('chatInput');
const chatMessages = document.getElementById('chatMessages');
const cardOverlay = document.getElementById('cardOverlay');
const cardContainer = document.getElementById('cardContainer');
const gameOverOverlay = document.getElementById('gameOverOverlay');
const winnerName = document.getElementById('winnerName');
const playAgainBtn = document.getElementById('playAgainBtn');
const menuBtn = document.getElementById('menuBtn');
const coinCountText = document.getElementById('coinCount');

const p1Score = document.getElementById('p1Score');
const p2Score = document.getElementById('p2Score');
const p1Rounds = document.getElementById('p1Rounds');
const p2Rounds = document.getElementById('p2Rounds');

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const inputs = { left: false, right: false, jump: false, block: false };
const mousePos = { x: 0, y: 0 };
const MAX_HP = 120;

let myCoins = parseInt(localStorage.getItem('bulletBrakCoins')) || 0;
if (coinCountText) coinCountText.textContent = myCoins;

function updateCoins(amount) {
    myCoins += amount;
    localStorage.setItem('bulletBrakCoins', myCoins);
    if (coinCountText) coinCountText.textContent = myCoins;
}

const optionGrid = document.getElementById('optionGrid');
const previewCanvas = document.getElementById('previewCanvas');
const pCtx = previewCanvas.getContext('2d');

const customization = {
    eye: 0,
    mouth: 0,
    detail: 0,
    color: '#ff6b6b'
};

const options = {
    eyes: [
        { name: 'Normal', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#000';
            ctx.beginPath(); ctx.arc(x + w * 0.3, y + h * 0.45, w * 0.08, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.7, y + h * 0.45, w * 0.08, 0, Math.PI * 2); ctx.fill();
        }},
        { name: 'Angry', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x + w * 0.2, y + h * 0.35); ctx.lineTo(x + w * 0.4, y + h * 0.45); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w * 0.8, y + h * 0.35); ctx.lineTo(x + w * 0.6, y + h * 0.45); ctx.stroke();
            ctx.fillStyle = '#000';
            ctx.beginPath(); ctx.arc(x + w * 0.3, y + h * 0.5, w * 0.06, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.7, y + h * 0.5, w * 0.06, 0, Math.PI * 2); ctx.fill();
        }},
        { name: 'Cute', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#000';
            ctx.beginPath(); ctx.arc(x + w * 0.3, y + h * 0.45, w * 0.1, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.7, y + h * 0.45, w * 0.1, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.beginPath(); ctx.arc(x + w * 0.28, y + h * 0.43, w * 0.03, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.68, y + h * 0.43, w * 0.03, 0, Math.PI * 2); ctx.fill();
        }},
        { name: 'Dead', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x + w * 0.2, y + h * 0.4); ctx.lineTo(x + w * 0.4, y + h * 0.5); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w * 0.4, y + h * 0.4); ctx.lineTo(x + w * 0.2, y + h * 0.5); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w * 0.6, y + h * 0.4); ctx.lineTo(x + w * 0.8, y + h * 0.5); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w * 0.8, y + h * 0.4); ctx.lineTo(x + w * 0.6, y + h * 0.5); ctx.stroke();
        }},
        { name: 'Cool', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#000';
            ctx.fillRect(x + w * 0.15, y + h * 0.4, w * 0.7, h * 0.1);
        }}
    ],
    mouths: [
        { name: 'Smile', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(x + w * 0.5, y + h * 0.6, w * 0.2, 0.1 * Math.PI, 0.9 * Math.PI); ctx.stroke();
        }},
        { name: 'Flat', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x + w * 0.35, y + h * 0.75); ctx.lineTo(x + w * 0.65, y + h * 0.75); ctx.stroke();
        }},
        { name: 'O', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(x + w * 0.5, y + h * 0.75, w * 0.08, 0, Math.PI * 2); ctx.stroke();
        }},
        { name: 'Cat', draw: (ctx, x, y, w, h) => {
            ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(x + w * 0.4, y + h * 0.7, w * 0.1, 0, Math.PI); ctx.stroke();
            ctx.beginPath(); ctx.arc(x + w * 0.6, y + h * 0.7, w * 0.1, 0, Math.PI); ctx.stroke();
        }},
        { name: 'Grin', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#fff'; ctx.strokeStyle = '#000'; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.rect(x + w * 0.35, y + h * 0.7, w * 0.3, h * 0.12); ctx.fill(); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w * 0.35, y + h * 0.76); ctx.lineTo(x + w * 0.65, y + h * 0.76); ctx.stroke();
        }}
    ],
    details: [
        { name: 'None', draw: () => {} },
        { name: 'Blush', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = 'rgba(255, 120, 160, 0.6)';
            ctx.beginPath(); ctx.arc(x + w * 0.25, y + h * 0.6, w * 0.08, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.75, y + h * 0.6, w * 0.08, 0, Math.PI * 2); ctx.fill();
        }},
        { name: 'Bow', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#ff4a9e';
            ctx.beginPath(); ctx.moveTo(x + w * 0.2, y + h * 0.15); ctx.lineTo(x + w * 0.4, y + h * 0.25); ctx.lineTo(x + w * 0.2, y + h * 0.35); ctx.fill();
            ctx.beginPath(); ctx.moveTo(x + w * 0.1, y + h * 0.25); ctx.arc(x + w * 0.1, y + h * 0.25, w * 0.05, 0, Math.PI * 2); ctx.fill();
        }},
        { name: 'Hat', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#333';
            ctx.fillRect(x + w * 0.2, y, w * 0.6, h * 0.15);
            ctx.fillRect(x + w * 0.1, y + h * 0.1, w * 0.8, h * 0.05);
        }},
        { name: 'Mustache', draw: (ctx, x, y, w, h) => {
            ctx.fillStyle = '#222';
            ctx.beginPath(); ctx.arc(x + w * 0.4, y + h * 0.72, w * 0.12, Math.PI, 0); ctx.fill();
            ctx.beginPath(); ctx.arc(x + w * 0.6, y + h * 0.72, w * 0.12, Math.PI, 0); ctx.fill();
        }}
    ],
    colors: [
        { name: 'Red', val: '#ff6b6b' },
        { name: 'Teal', val: '#4ecdc4' },
        { name: 'Cyan', val: '#4cc9e8' },
        { name: 'Mint', val: '#9ad9bf' },
        { name: 'Cream', val: '#ffe8a3' },
        { name: 'Pink', val: '#f06595' },
        { name: 'Seafoam', val: '#9bdccf' },
        { name: 'Yellow', val: '#ffd43b' },
        { name: 'Purple', val: '#c08ad9' },
        { name: 'Blue', val: '#4dabf7' },
        { name: 'Orange', val: '#ffa94d' },
        { name: 'Green', val: '#51cf66' }
    ]
};

let currentCategory = 'eyes';

function renderOptions() {
    optionGrid.innerHTML = '';
    const items = options[currentCategory];
    items.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'grid-item';
        
        // Simple Economy: Some items cost coins (index > 2)
        const isLocked = index > 2 && currentCategory !== 'colors'; 
        const price = isLocked ? 50 : 0;

        if (currentCategory === 'colors') {
            div.classList.add('color-item');
            div.style.backgroundColor = item.val;
            if (customization.color === item.val) div.classList.add('selected');
        } else {
            const canvas = document.createElement('canvas');
            canvas.width = 40; canvas.height = 40;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ddd';
            ctx.beginPath(); ctx.arc(20, 20, 18, 0, Math.PI * 2); ctx.fill();
            item.draw(ctx, 0, 0, 40, 40);
            div.appendChild(canvas);
            
            if (isLocked) {
                const lock = document.createElement('div');
                lock.style = 'position:absolute; font-size:10px; bottom:0; padding:2px; background:rgba(0,0,0,0.5); width:100%; text-align:center;';
                lock.textContent = `💰${price}`;
                div.appendChild(lock);
            }

            if (customization[currentCategory.slice(0, -1)] === index) div.classList.add('selected');
        }
        
        div.addEventListener('click', () => {
            if (isLocked) {
                if (myCoins >= price) {
                    updateCoins(-price);
                    // In a real game, we'd save "unlockedItems" to localStorage too.
                    // For now, let's just allow picking it once bought.
                } else {
                    alert('코인이 부족합니다! 게임을 플레이하여 코인을 모으세요.');
                    return;
                }
            }

            if (currentCategory === 'colors') {
                customization.color = item.val;
            } else {
                customization[currentCategory.slice(0, -1)] = index;
            }
            renderOptions();
            drawPreview();
        });
        optionGrid.appendChild(div);
    });
}

function drawPreview() {
    pCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
    const x = 25, y = 25, w = 100, h = 100;
    
    // Body
    pCtx.fillStyle = customization.color;
    pCtx.beginPath(); pCtx.arc(x + w/2, y + h/2, w/2, 0, Math.PI * 2); pCtx.fill();
    pCtx.strokeStyle = 'rgba(0,0,0,0.1)'; pCtx.lineWidth = 2; pCtx.stroke();

    options.eyes[customization.eye].draw(pCtx, x, y, w, h);
    options.mouths[customization.mouth].draw(pCtx, x, y, w, h);
    options.details[customization.detail].draw(pCtx, x, y, w, h);
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCategory = btn.dataset.category;
        renderOptions();
    });
});

const avatars = [
    { id: 'red', name: 'Red', primary: '#ff6b6b', secondary: '#ffa8a8' },
    { id: 'teal', name: 'Teal', primary: '#4ecdc4', secondary: '#7ee7df' },
    { id: 'cyan', name: 'Cyan', primary: '#4cc9e8', secondary: '#7dddf2' },
    { id: 'mint', name: 'Mint', primary: '#9ad9bf', secondary: '#c2eadb' },
    { id: 'cream', name: 'Cream', primary: '#ffe8a3', secondary: '#fff2cc' },
    { id: 'pink', name: 'Pink', primary: '#dd9ae2', secondary: '#efc4f0' },
    { id: 'seafoam', name: 'Seafoam', primary: '#9bdccf', secondary: '#c2ece4' },
    { id: 'yellow', name: 'Yellow', primary: '#f7dc62', secondary: '#fbe58f' },
    { id: 'purple', name: 'Purple', primary: '#c08ad9', secondary: '#d8b6ea' },
    { id: 'blue', name: 'Blue', primary: '#8cc6f7', secondary: '#b6ddfb' },
    { id: 'orange', name: 'Orange', primary: '#f7bf6e', secondary: '#ffd79a' },
    { id: 'green', name: 'Green', primary: '#84e08c', secondary: '#b2efb8' },
];

const avatarMap = new Map(avatars.map((avatar) => [avatar.id, avatar]));
avatarMap.set('bot', { id: 'bot', name: 'Bot', primary: '#adb5bd', secondary: '#dee2e6' });

let selectedAvatarId = null;
let myId = null;
let currentRoomCode = null;
let latestState = null;
const screens = [lobbyScreen, roomLobbyScreen, gameScreen];

function setStatus(message = '') {
    lobbyStatus.textContent = message;
}

function activateScreen(target) {
    screens.forEach((screen) => {
        if (!screen) return;
        screen.classList.toggle('active', screen === target);
    });
}

function showLobby() {
    activateScreen(lobbyScreen);
}

function showRoomLobby() {
    activateScreen(roomLobbyScreen);
}

function showGame() {
    activateScreen(gameScreen);
}

function selectAvatar(id) {
    selectedAvatarId = id;
}

roomCodeInput.addEventListener('input', () => {
    roomCodeInput.value = roomCodeInput.value.replace(/[^0-9]/g, '').slice(0, 6);
});

function ensureAvatarSelected() {
    return true; 
}

const maxPlayersSelect = document.getElementById('maxPlayersSelect');

createRoomBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    socket.emit('createRoom', { 
        customization, 
        nickname: nicknameInput.value.trim(),
        maxPlayers: parseInt(maxPlayersSelect.value) || 2,
        coins: myCoins
    }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '방 생성에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `초대 코드: ${response.code}`;
        if (roomLobbyCode) roomLobbyCode.textContent = response.code;
        if (roomLobbyCount && response.state) {
            roomLobbyCount.textContent = `접속 인원: ${response.state.players.length}/${response.state.maxPlayers}`;
        }
        showRoomLobby();
    });
});

joinRoomBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    const code = roomCodeInput.value.trim();
    if (!/^[0-9]{6}$/.test(code)) {
        setStatus('6자리 숫자 코드를 입력해 주세요.');
        return;
    }
    socket.emit('joinRoom', { code, customization, nickname: nicknameInput.value.trim(), coins: myCoins }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '방 참가에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `입장 완료: ${response.code}`;
        if (roomLobbyCode) roomLobbyCode.textContent = response.code;
        if (roomLobbyCount && response.state) {
            roomLobbyCount.textContent = `접속 인원: ${response.state.players.length}/${response.state.maxPlayers}`;
        }
        showRoomLobby();
    });
});

soloBtn.addEventListener('click', () => {
    if (!ensureAvatarSelected()) return;
    socket.emit('startTraining', { customization, nickname: nicknameInput.value.trim(), coins: myCoins }, (response) => {
        if (!response?.ok) {
            setStatus(response?.message || '훈련장 입장에 실패했습니다.');
            return;
        }
        currentRoomCode = response.code;
        roomInfo.textContent = `훈련장 입장: ${response.code}`;
        showGame();
    });
});

function resetRoomUi() {
    currentRoomCode = null;
    latestState = null;
    setStatus('');
    roomInfo.textContent = '';
    roomCodeDisplay.textContent = '';
    playerCountDisplay.textContent = '';
    if (roomLobbyCode) roomLobbyCode.textContent = '';
    if (roomLobbyCount) roomLobbyCount.textContent = '';
    if (playerList) playerList.innerHTML = '';
}

function leaveRoomAndReset() {
    socket.emit('leaveRoom');
    resetRoomUi();
    showLobby();
}

leaveBtn.addEventListener('click', leaveRoomAndReset);
if (roomLobbyLeaveBtn) roomLobbyLeaveBtn.addEventListener('click', leaveRoomAndReset);
if (enterGameBtn) enterGameBtn.addEventListener('click', () => showGame());

window.addEventListener('keydown', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    if (event.code === 'KeyA') inputs.left = true;
    if (event.code === 'KeyD') inputs.right = true;
    if (event.code === 'Space' || event.code === 'KeyW') inputs.jump = true;
    if (event.code === 'ShiftLeft' || event.code === 'KeyS') inputs.block = true;
    socket.emit('input', inputs);
});

window.addEventListener('keyup', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    if (event.code === 'KeyA') inputs.left = false;
    if (event.code === 'KeyD') inputs.right = false;
    if (event.code === 'Space' || event.code === 'KeyW') inputs.jump = false;
    if (event.code === 'ShiftLeft' || event.code === 'KeyS') inputs.block = false;
    socket.emit('input', inputs);
});

gameScreen.addEventListener('contextmenu', (e) => {
    e.preventDefault(); // disable right click menu
});

gameScreen.addEventListener('mousedown', (e) => {
    if (e.button === 2) { // Right Click
        inputs.block = true;
        socket.emit('input', inputs);
    }
    if (e.button === 0) {
        socket.emit('shoot');
    }
});

gameScreen.addEventListener('mouseup', (e) => {
    if (e.button === 2) {
        inputs.block = false;
        socket.emit('input', inputs);
    }
});

canvas.addEventListener('mousemove', (event) => {
    if (!gameScreen.classList.contains('active')) return;
    const rect = canvas.getBoundingClientRect();
    mousePos.x = event.clientX - rect.left;
    mousePos.y = event.clientY - rect.top;
    socket.emit('mouseMove', mousePos);
});

// Using window level for mousedown/up/contextmenu handles so it captures clicks anywhere on game screen
// Handled above in keydown section now

socket.on('connect', () => {
    myId = socket.id;
});

socket.on('roomState', (state) => {
    latestState = state;
    
    // Update personal coins if found
    const me = state.players.find(p => p.id === socket.id);
    if (me && me.coins !== undefined) {
        myCoins = me.coins;
        localStorage.setItem('bulletBrakCoins', myCoins);
        if (coinCountText) coinCountText.textContent = myCoins;
    }

    if (state.code) {
        roomCodeDisplay.textContent = `방 코드: ${state.code}`;
        playerCountDisplay.textContent = `접속 인원: ${state.players.length}/${state.maxPlayers}`;
        if (roomLobbyCode) roomLobbyCode.textContent = state.code;
        if (roomLobbyCount) {
            roomLobbyCount.textContent = `플레이어: ${state.players.length} / ${state.maxPlayers}명`;
        }
        if (playerList) {
            playerList.innerHTML = '';
            state.players.forEach(p => {
                const div = document.createElement('div');
                div.className = 'player-item';
                div.textContent = p.nickname || '익명 플레이어';
                playerList.appendChild(div);
            });
        }
    }
});

socket.on('gameState', (state) => {
    if (latestState && latestState.phase !== state.phase && state.phase === 'playing') {
        lerpedPlayers.clear();
    }
    latestState = state;
    updateOverlay(state);
});

function gameLoop() {
    if (latestState && gameScreen.classList.contains('active')) {
        drawState(latestState);
    }
    requestAnimationFrame(gameLoop);
}
gameLoop();

function updateOverlay(state) {
    if (state.phase === 'picking') {
        const titleSpan = cardOverlay.querySelector('.picking-title');
        if (!cardOverlay.classList.contains('active')) {
            if (state.loserToPick === socket.id) {
                if (titleSpan) titleSpan.textContent = 'PICK A CARD';
                cardOverlay.classList.add('active');
                renderCards(state.availableCards);
            } else {
                if (titleSpan) titleSpan.textContent = 'WAITING...';
                cardContainer.innerHTML = '<p style="color:white; font-size:1.5rem; text-align:center; width:100%;">상대방이 카드를 구성 중입니다...</p>';
                cardOverlay.classList.add('active');
            }
        }
    } else {
        cardOverlay.classList.remove('active');
    }

    if (state.phase === 'finished') {
        const winner = state.players.reduce((prev, current) => (prev.score > current.score) ? prev : current);
        winnerName.textContent = `${winner.nickname} 승리!`;
        gameOverOverlay.classList.add('active');
        
        // Sync coins back from server
        const me = state.players.find(p => p.id === socket.id);
        if (me) {
            myCoins = me.coins;
            localStorage.setItem('bulletBrakCoins', myCoins);
            if (coinCountText) coinCountText.textContent = myCoins;
        }
    } else {
        gameOverOverlay.classList.remove('active');
    }

    // Update Scores & Dots
    if (state.players.length >= 2) {
        const p1 = state.players[0];
        const p2 = state.players[1];
        p1Score.textContent = p1.score;
        p2Score.textContent = p2.score;

        // Rounds
        updateDots(p1Rounds, p1.roundWins);
        updateDots(p2Rounds, p2.roundWins);
    }
}

function updateDots(container, wins) {
    const dots = container.querySelectorAll('.round-dot');
    dots.forEach((dot, i) => {
        dot.classList.toggle('won', i < wins);
    });
}

function renderCards(cards) {
    cardContainer.innerHTML = '';
    const total = cards.length;
    const arcRadius = 380;
    const spanAngle = Math.PI * 0.45;

    cards.forEach((card, index) => {
        const div = document.createElement('div');
        div.className = 'card-item';
        
        // Arc positioning
        const angle = (index - (total - 1) / 2) * (spanAngle / Math.max(1, total - 1)) - Math.PI / 2;
        const x = Math.cos(angle) * arcRadius;
        const y = Math.sin(angle) * (arcRadius * 0.5) + 200;
        const rotation = (angle + Math.PI / 2) * (180 / Math.PI);

        div.style.left = `calc(50% + ${x}px - 80px)`;
        div.style.top = `${y}px`;
        div.style.transform = `rotate(${rotation}deg)`;
        
        if (card.color) {
            div.style.borderColor = card.color;
            div.style.setProperty('--accent-glow', `${card.color}66`);
        }

        div.innerHTML = `
            <div class="card-category" style="color: ${card.color || 'var(--accent)'}">${card.category || 'Special'}</div>
            <div class="card-icon">${card.emoji || '🃏'}</div>
            <div>
                <div class="card-name">${card.name}</div>
                <div class="card-desc">${card.desc}</div>
            </div>
        `;
        div.onclick = () => {
            socket.emit('pickCard', { cardId: card.id });
            cardOverlay.classList.remove('active');
        };
        cardContainer.appendChild(div);
    });
}

function getCardEmoji(id) {
    const emojis = {
        hp: '❤️', speed: '⚡', jump: '☁️', reload: '🔫', 
        big: '💣', tank: '🛡️', glass: '🥃', brawler: '🥊',
        dazzle: '✨', huge: '🐘'
    };
    return emojis[id] || '🃏';
}

chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        const text = chatInput.value.trim();
        if (text) {
            socket.emit('chat', text);
            chatInput.value = '';
        }
    }
});

socket.on('chat', (msg) => {
    const div = document.createElement('div');
    div.innerHTML = `<span style="color:var(--accent); font-weight:700;">${msg.sender}:</span> ${msg.text}`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
});

playAgainBtn.addEventListener('click', () => {
    socket.emit('restartGame');
});

menuBtn.addEventListener('click', () => {
    leaveRoomAndReset();
});

enterGameBtn.addEventListener('click', () => {
    socket.emit('startGame');
});

socket.on('gameStarted', () => {
    showGame();
});

let lerpedPlayers = new Map();

function drawAvatar(entity) {
    const shadowX = entity.x + entity.width / 2;
    const shadowY = entity.y + entity.height - 2;

    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.beginPath();
    ctx.ellipse(shadowX, shadowY, entity.width * 0.35, entity.height * 0.12, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    const cust = entity.customization || { color: '#ff6b6b', eye: 0, mouth: 0, detail: 0 };
    
    // Body
    ctx.fillStyle = cust.color;
    ctx.beginPath();
    ctx.arc(entity.x + entity.width/2, entity.y + entity.height/2, entity.width/2, 0, Math.PI * 2);
    ctx.fill();

    // Features
    if (options.eyes[cust.eye]) options.eyes[cust.eye].draw(ctx, entity.x, entity.y, entity.width, entity.height);
    if (options.mouths[cust.mouth]) options.mouths[cust.mouth].draw(ctx, entity.x, entity.y, entity.width, entity.height);
    if (options.details[cust.detail]) options.details[cust.detail].draw(ctx, entity.x, entity.y, entity.width, entity.height);
}

function drawState(state) {
    if (!gameScreen.classList.contains('active')) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#1b2438';
    state.platforms.forEach((platform) => {
        ctx.fillRect(platform.x, platform.y, platform.width, platform.height);
        ctx.strokeStyle = 'rgba(93, 226, 221, 0.2)';
        ctx.strokeRect(platform.x, platform.y, platform.width, platform.height);
    });

    state.players.forEach((player) => {
        // Simple Lerping for smoother motion
        if (!lerpedPlayers.has(player.id)) {
            lerpedPlayers.set(player.id, { x: player.x, y: player.y });
        }
        let lp = lerpedPlayers.get(player.id);
        lp.x += (player.x - lp.x) * 0.35;
        lp.y += (player.y - lp.y) * 0.35;

        const drawPlayer = { ...player, x: lp.x, y: lp.y };
        
        ctx.save();
        if (player.hp <= 0) {
            ctx.translate(lp.x + player.width / 2, lp.y + player.height / 2);
            ctx.rotate(Math.PI / 2);
            // Translate back for drawing
            drawPlayer.x = -player.width / 2;
            drawPlayer.y = -player.height / 2;
        }

        drawAvatar(drawPlayer);
        ctx.restore();

        if (player.hp > 0) {
            
            // Draw Block Shield
            if (player.blockActiveTime > 0) {
                ctx.save();
                ctx.beginPath();
                ctx.arc(lp.x + player.width/2, lp.y + player.height/2, player.width * 0.8, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 3;
                ctx.stroke();
                ctx.restore();
            }

            const bx = lp.x, by = lp.y, bw = player.width;
            ctx.fillStyle = '#333';
            ctx.fillRect(bx, by - 14, bw, 6);
            ctx.fillStyle = player.id === myId ? '#5de2dd' : '#f03e3e';
            ctx.fillRect(bx, by - 14, bw * (player.hp / player.maxHp), 6);

            ctx.fillStyle = '#fff';
            ctx.font = 'bold 12px Outfit';
            ctx.textAlign = 'center';
            ctx.fillText(player.nickname || '익명', bx + bw/2, by - 22);
            ctx.textAlign = 'left';

            // Draw weapon line
            const cx = lp.x + player.width / 2;
            const cy = lp.y + player.height / 2;
            const angle = Math.atan2(player.mouseTarget.y - cy, player.mouseTarget.x - cx);
            ctx.strokeStyle = 'rgba(255,255,255,0.5)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(angle) * 30, cy + Math.sin(angle) * 30);
            ctx.stroke();
        }
    });

    state.bots.forEach((bot) => {
        ctx.save();
        const drawBot = { ...bot };
        
        if (bot.hp <= 0) {
            ctx.translate(bot.x + bot.width / 2, bot.y + bot.height / 2);
            ctx.rotate(Math.PI / 2);
            drawBot.x = -bot.width / 2;
            drawBot.y = -bot.height / 2;
        }
        
        drawAvatar(drawBot);
        ctx.restore();

        if (bot.hp > 0) {
            ctx.fillStyle = '#f03e3e';
            ctx.fillRect(bot.x, bot.y - 12, bot.width, 5);
            ctx.fillStyle = '#37b24d';
            ctx.fillRect(bot.x, bot.y - 12, bot.width * (bot.hp / MAX_HP), 5);
        }
    });

    state.bullets.forEach((bullet) => {
        ctx.beginPath();
        ctx.arc(bullet.x, bullet.y, bullet.size || 5, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.shadowBlur = 10;
        ctx.shadowColor = '#5de2dd';
        ctx.fill();
        ctx.shadowBlur = 0;
    });
}

function initCustomization() {
    renderOptions();
    drawPreview();
}

initCustomization();
showLobby();
