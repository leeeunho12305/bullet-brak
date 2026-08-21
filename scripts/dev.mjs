// `pnpm dev` — api(:8000) + web(:5173) 를 한 터미널에서 같이 띄운다. 도커도 make 도 필요 없다.
//
// 왜 스크립트인가 — pnpm 워크스페이스에는 api(파이썬)가 없어서 `pnpm -r dev` 로는 못 묶는다.
// concurrently 같은 패키지를 붙이지 않으려고 node 기본 API 로만 짰다.
//
//   pnpm dev            둘 다
//   pnpm dev:api        FastAPI 만
//   pnpm dev:web        Vite 만
//
// 포트는 API_PORT / WEB_PORT 로 바꾼다.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { API_DIR, venvPython, viteBin, WEB_DIR } from './dev-env.mjs';

const only = process.argv[2]; // 'api' | 'web' | undefined
const API_PORT = process.env.API_PORT ?? '8000';
const WEB_PORT = process.env.WEB_PORT ?? '5173';

const COLORS = { api: '\u001b[36m', web: '\u001b[35m', err: '\u001b[31m', off: '\u001b[0m' };
const useColor = process.stdout.isTTY && !process.env.NO_COLOR;
const tag = (name) => (useColor ? `${COLORS[name]}[${name}]${COLORS.off}` : `[${name}]`);

function fail(msg) {
  console.error(`${useColor ? COLORS.err : ''}${msg}${useColor ? COLORS.off : ''}`);
  process.exit(1);
}

/** 자식 프로세스 출력을 [api]/[web] 접두어를 붙여 줄 단위로 흘린다. */
function pipe(name, stream) {
  let buf = '';
  stream.setEncoding('utf8');
  stream.on('data', (chunk) => {
    buf += chunk;
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() ?? '';
    for (const line of lines) console.log(`${tag(name)} ${line}`);
  });
  stream.on('end', () => {
    if (buf.trim()) console.log(`${tag(name)} ${buf}`);
  });
}

const children = new Map();
let shuttingDown = false;

function start(name, cmd, args, opts) {
  const child = spawn(cmd, args, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] });
  children.set(name, child);
  pipe(name, child.stdout);
  pipe(name, child.stderr);

  child.on('error', (err) => fail(`[${name}] 실행 실패: ${err.message}`));
  child.on('exit', (code, signal) => {
    children.delete(name);
    if (shuttingDown) return;
    console.log(`${tag(name)} 종료 (code=${code ?? signal})`);
    // 하나가 죽으면 나머지도 같이 내린다 — 반쪽만 떠 있으면 게임이 동작하지 않는다.
    shutdown(code ?? 1);
  });
  return child;
}

/** Windows 는 child.kill() 이 손자 프로세스(uvicorn --reload 의 워커)를 남긴다. */
function killTree(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    child.kill('SIGTERM');
  }
}

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children.values()) killTree(child);
  setTimeout(() => process.exit(code), 300).unref();
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

if (only !== 'web') {
  const py = venvPython();
  if (!existsSync(py)) {
    fail(`백엔드 venv 가 없다(또는 껍데기만 남았다): ${py}\n먼저 \`pnpm bootstrap\` 을 실행한다. (Python 3.11+ 필요)`);
  }
  // uvicorn 실행 파일 대신 -m 으로 부른다. Scripts/ 가 비어 있어도(윈도우에서 흔하다) 뜬다.
  start('api', py, ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', API_PORT], {
    cwd: API_DIR,
    // 파이프로 받으면 Windows 콘솔 코드페이지(cp949)로 인코딩돼 한글 로그가 깨진다.
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
  });
}

if (only !== 'api') {
  const vite = viteBin();
  if (!existsSync(vite)) fail(`프론트 의존성이 없다. 먼저 \`pnpm install\` 을 실행한다.`);
  start('web', process.execPath, [vite], {
    cwd: WEB_DIR,
    env: { ...process.env, WEB_PORT, API_PROXY_TARGET: process.env.API_PROXY_TARGET ?? `http://127.0.0.1:${API_PORT}` },
  });
}

if (!only) {
  console.log(`\n  web  -> http://localhost:${WEB_PORT}   (여기 하나만 보면 된다)`);
  console.log(`  api  -> http://127.0.0.1:${API_PORT}/api/health\n`);
}
