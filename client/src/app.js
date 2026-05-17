const socket = io();
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const inputs = { left: false, right: false, jump: false };
const mousePos = { x: 0, y: 0 };

window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyA') inputs.left = true;
    if (e.code === 'KeyD') inputs.right = true;
    if (e.code === 'Space') inputs.jump = true;
    socket.emit('input', inputs);
});

window.addEventListener('keyup', (e) => {
    if (e.code === 'KeyA') inputs.left = false;
    if (e.code === 'KeyD') inputs.right = false;
    if (e.code === 'Space') inputs.jump = false;
    socket.emit('input', inputs);
});

canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    mousePos.x = e.clientX - rect.left;
    mousePos.y = e.clientY - rect.top;
    socket.emit('mouseMove', mousePos);
});

canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0) { // Left click
        socket.emit('shoot');
    }
});

let myId = null;
socket.on('connect', () => {
    myId = socket.id;
});

socket.on('gameState', (state) => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw platforms
    ctx.fillStyle = '#485460';
    state.platforms.forEach(p => ctx.fillRect(p.x, p.y, p.width, p.height));

    // Draw players
    Object.entries(state.players).forEach(([id, p]) => {
        if (p.hp <= 0) return;
        
        ctx.fillStyle = p.color;
        ctx.fillRect(p.x, p.y, p.width, p.height);
        
        ctx.fillStyle = 'red'; ctx.fillRect(p.x, p.y - 12, p.width, 5);
        ctx.fillStyle = '#00ff00'; ctx.fillRect(p.x, p.y - 12, p.width * (p.hp/100), 5);
        
        // 내 캐릭터 텍스트 표시
        if (id === myId) {
            ctx.fillStyle = 'white';
            ctx.font = '10px sans-serif';
            ctx.fillText('Me', p.x + 5, p.y - 15);
        }
        
        // 총구 (마우스 조준 방향)
        const cx = p.x + p.width/2;
        const cy = p.y + p.height/2;
        const angle = Math.atan2(p.mouseTarget.y - cy, p.mouseTarget.x - cx);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(angle)*30, cy + Math.sin(angle)*30);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 4;
        ctx.stroke();
    });

    // Draw bullets
    state.bullets.forEach(b => {
        ctx.beginPath(); ctx.arc(b.x, b.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = b.color; ctx.fill(); ctx.closePath();
    });
});
