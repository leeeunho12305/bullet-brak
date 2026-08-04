// 의존성 없는 정적 파일 서버. apps/web/dist 를 $PORT 에 서빙한다.
//
// Render 에서 이 저장소를 Static Site 가 아니라 Node Web Service 로 만들었을 때 쓰인다
// (그 경우 Start Command 기본값이 `yarn start` 라서 루트 package.json 의 start 가 이걸 부른다).
// 도커/단일 VM 운영 경로는 여전히 nginx(apps/web/nginx.conf) 다. 이 파일은 그 대체재가 아니라
// "대시보드를 못 건드리는 상황"의 안전망이다.
//
// /api 와 /ws 는 게임 서버(FastAPI)로 그대로 넘긴다. 프런트 입장에서는 같은 오리진이라
// VITE_API_BASE / VITE_WS_BASE 도, CORS 설정도 필요 없다.
// 게임 서버 주소는 API_ORIGIN 환경변수로 바꾼다(기본값은 render.yaml 이 만드는 이름).
import { spawn, spawnSync } from 'node:child_process';
import { createReadStream, existsSync, statSync } from 'node:fs';
import http, { createServer } from 'node:http';
import https from 'node:https';
import { delimiter as pathDelimiter, extname, join, normalize, resolve, sep } from 'node:path';

const ROOT = resolve(process.cwd(), 'apps/web/dist');
const PORT = Number(process.env.PORT ?? 8080);

const API_ORIGIN = (process.env.API_ORIGIN ?? 'https://bullet-brak-api.onrender.com').replace(
  /\/+$/,
  '',
);

/** 프록시 대상. 내장 API 가 뜨는 데 성공하면 그쪽으로 갈아탄다. */
let target = parseTarget(API_ORIGIN);

/** 내장 API 시도 결과. /healthz 로 노출해서 배포 로그 없이도 원인을 알 수 있게 한다. */
let embedState = 'pending';

function parseTarget(origin) {
  const url = new URL(origin);
  const secure = url.protocol === 'https:';
  return {
    origin,
    hostname: url.hostname,
    host: url.host,
    port: url.port || (secure ? 443 : 80),
    lib: secure ? https : http,
    secure,
  };
}

/** 게임 서버로 넘겨야 하는 경로인가 */
function isApiPath(url) {
  return url.startsWith('/api/') || url === '/api' || url.startsWith('/ws/');
}

function upstreamOptions(req) {
  const options = {
    host: target.hostname,
    port: target.port,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: target.host },
  };
  if (target.secure) options.servername = target.hostname; // https 업스트림 SNI
  return options;
}

/** /api/* HTTP 프록시. 실패하면 프런트가 그대로 읽을 수 있는 detail 을 돌려준다. */
function proxyHttp(req, res) {
  const proxyReq = target.lib.request(upstreamOptions(req), (proxyRes) => {
    const status = proxyRes.statusCode ?? 502;
    const type = String(proxyRes.headers['content-type'] ?? '');

    // 우리 API 는 에러도 JSON({"detail": ...}) 으로 준다. 에러인데 JSON 이 아니면
    // 게임 서버가 아니라 그 앞단이 답한 것이다(예: 서비스가 없는 호스트에 Render 엣지가
    // 돌려주는 404 HTML). 그대로 흘리면 화면에 "요청에 실패했습니다. (404)" 만 뜬다.
    if (status >= 400 && !type.includes('application/json')) {
      proxyRes.resume(); // 본문은 버린다
      res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(
        JSON.stringify({
          detail: `게임 서버(${target.origin})가 응답하지 않습니다(${status}). API 서비스가 배포돼 있는지 확인해 주세요.`,
        }),
      );
      return;
    }

    res.writeHead(status, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (err) => {
    console.error(`API 프록시 실패 ${req.method} ${req.url}: ${err.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
    }
    res.end(
      JSON.stringify({
        detail: `게임 서버(${target.origin})에 연결할 수 없습니다. API 서비스가 떠 있는지 확인해 주세요.`,
      }),
    );
  });

  req.pipe(proxyReq);
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

if (!existsSync(join(ROOT, 'index.html'))) {
  console.error(`${ROOT}/index.html 이 없다. 먼저 빌드해야 한다: sh scripts/render-build.sh`);
  process.exit(1);
}

/** URL 경로를 dist 안의 실제 파일로 해석한다. dist 밖으로 나가면 null. */
function resolveFile(rawUrl) {
  let decoded;
  try {
    decoded = decodeURIComponent(rawUrl.split('?')[0]);
  } catch {
    return null; // 깨진 퍼센트 인코딩
  }
  const candidate = resolve(join(ROOT, normalize(decoded)));
  if (candidate !== ROOT && !candidate.startsWith(ROOT + sep)) return null;
  return existsSync(candidate) && statSync(candidate).isFile() ? candidate : null;
}

const server = createServer((req, res) => {
  const url = req.url ?? '/';

  // 게임 서버로 넘길 요청이 먼저다. (이 분기가 없어서 POST /api/rooms 가 405 로 튕겼다)
  if (isApiPath(url)) {
    proxyHttp(req, res);
    return;
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }

  // 정적 서버 자체의 상태 + 내장 API 를 띄웠는지. 배포 로그를 못 볼 때 밖에서 진단하는 창구다.
  if (url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' }).end(
      `${JSON.stringify({ static: 'ok', api_target: target.origin, embedded: embedState })}\n`,
    );
    return;
  }

  // SPA 폴백: 해당 파일이 없으면 index.html 을 준다.
  const file = resolveFile(url) ?? join(ROOT, 'index.html');
  // 해시가 박힌 번들만 영구 캐시. index.html 은 항상 재검증. (nginx.conf 와 같은 정책)
  const immutable = file.includes(`${sep}assets${sep}`);

  res.writeHead(200, {
    'Content-Type': MIME[extname(file).toLowerCase()] ?? 'application/octet-stream',
    'Cache-Control': immutable ? 'public, immutable, max-age=31536000' : 'no-cache',
  });

  if (req.method === 'HEAD') {
    res.end();
    return;
  }

  createReadStream(file)
    .on('error', () => res.end())
    .pipe(res);
});

/** /ws/* WebSocket 업그레이드 프록시. 60Hz 스냅샷이 흐르므로 Nagle 을 끈다. */
server.on('upgrade', (req, socket, head) => {
  if (!isApiPath(req.url ?? '')) {
    socket.destroy();
    return;
  }

  const proxyReq = target.lib.request({ ...upstreamOptions(req), method: 'GET' });

  proxyReq.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    const headers = Object.entries(proxyRes.headers)
      .flatMap(([k, v]) => (Array.isArray(v) ? v.map((one) => `${k}: ${one}`) : [`${k}: ${v}`]))
      .join('\r\n');
    socket.write(`HTTP/1.1 101 ${proxyRes.statusMessage ?? 'Switching Protocols'}\r\n${headers}\r\n\r\n`);

    if (proxyHead?.length) proxySocket.unshift(proxyHead);
    if (head?.length) proxySocket.write(head);

    socket.setNoDelay(true);
    proxySocket.setNoDelay(true);

    const close = () => {
      proxySocket.destroy();
      socket.destroy();
    };
    socket.on('error', close);
    proxySocket.on('error', close);
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });

  // 업그레이드가 아니라 일반 응답이면(방 없음 등) 상태줄만 전달하고 끊는다.
  proxyReq.on('response', (proxyRes) => {
    socket.write(`HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage ?? ''}\r\n\r\n`);
    socket.destroy();
  });
  proxyReq.on('error', (err) => {
    console.error(`WS 프록시 실패 ${req.url}: ${err.message}`);
    socket.destroy();
  });
  proxyReq.end();
});

// --------------------------------------------------------------------------
// 내장 게임 서버
//
// Render 대시보드로 만든 Node 서비스 하나에 프런트와 API 를 같이 태운다.
// (서비스를 추가로 만들려면 대시보드를 거쳐야 하는데 그게 불가능한 상황을 위한 길이다.)
// python3 나 의존성이 없으면 조용히 포기하고 외부 API_ORIGIN 프록시로 남는다 —
// 즉 실패해도 지금 동작에서 나빠지지 않는다. EMBED_API=0 으로 끌 수 있다.
// --------------------------------------------------------------------------

const EMBED_PORT = Number(process.env.EMBEDDED_API_PORT ?? 8001);

function findPython() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  for (const candidate of ['python3', 'python']) {
    const probe = spawnSync(candidate, ['--version'], { stdio: 'ignore' });
    if (!probe.error && probe.status === 0) return candidate;
  }
  return null;
}

function healthy(port) {
  return new Promise((done) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: '/api/health', timeout: 1500 },
      (res) => {
        res.resume();
        done(res.statusCode === 200);
      },
    );
    req.on('error', () => done(false));
    req.on('timeout', () => {
      req.destroy();
      done(false);
    });
  });
}

async function startEmbeddedApi() {
  if (process.env.EMBED_API === '0') {
    embedState = 'disabled';
    return;
  }

  const python = findPython();
  if (!python) {
    embedState = 'no-python';
    console.log('내장 API: python 이 없어 건너뛴다. 프록시는 외부 API_ORIGIN 을 쓴다.');
    return;
  }

  const apiDir = resolve(process.cwd(), 'apps/api');
  if (!existsSync(join(apiDir, 'app', 'main.py'))) {
    embedState = 'no-source';
    console.log('내장 API: apps/api 가 없어 건너뛴다.');
    return;
  }

  // 빌드가 --target 으로 여기에 의존성을 심는다. --user 는 런타임에 HOME/버전이
  // 달라지면 못 찾아서 uvicorn 이 exited(1) 로 죽었다.
  const pydeps = join(apiDir, '.pydeps');
  const pythonPath = [pydeps, process.env.PYTHONPATH].filter(Boolean).join(pathDelimiter);

  console.log(`내장 API 시작 시도: ${python} -m uvicorn (127.0.0.1:${EMBED_PORT})`);
  console.log(`  PYTHONPATH=${pythonPath} (.pydeps ${existsSync(pydeps) ? '있음' : '없음'})`);

  const child = spawn(
    python,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(EMBED_PORT),
      '--workers', '1', '--no-access-log'],
    {
      cwd: apiDir,
      stdio: ['ignore', 'inherit', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONPATH: pythonPath },
    },
  );

  // 죽은 이유를 밖(/healthz)에서도 볼 수 있게 stderr 끝부분을 들고 있는다.
  let stderrTail = '';
  child.stderr?.on('data', (chunk) => {
    const text = String(chunk);
    process.stderr.write(text);
    stderrTail = (stderrTail + text).slice(-600);
  });

  const lastLine = () =>
    stderrTail.split('\n').map((l) => l.trim()).filter(Boolean).pop() ?? '(stderr 없음)';

  child.on('error', (err) => {
    embedState = `spawn-failed: ${err.message}`;
    console.error(`내장 API 실행 실패: ${err.message}`);
  });
  child.on('exit', (code) => {
    if (embedState !== 'ok') embedState = `exited(${code}): ${lastLine()}`;
    console.error(`내장 API 종료(code=${code}).`);
  });
  process.on('exit', () => child.kill());

  // 최대 20초까지 헬스체크를 기다린다(콜드 스타트에서 import 가 느릴 수 있다).
  for (let i = 0; i < 40; i += 1) {
    await new Promise((r) => setTimeout(r, 500));
    if (child.exitCode !== null) break;
    if (await healthy(EMBED_PORT)) {
      target = parseTarget(`http://127.0.0.1:${EMBED_PORT}`);
      embedState = 'ok';
      console.log(`내장 API 준비 완료. /api, /ws -> ${target.origin}`);
      return;
    }
  }
  if (embedState === 'pending') embedState = 'timeout';
  console.error(`내장 API 가 뜨지 않았다. 외부 ${API_ORIGIN} 로 계속 간다.`);
}

server.listen(PORT, '0.0.0.0', () => {
  console.log(`정적 서버 http://0.0.0.0:${PORT} -> ${ROOT}`);
  console.log(`  /api, /ws -> ${target.origin}`);
  // 정적 서빙을 막지 않도록 기다리지 않는다.
  void startEmbeddedApi();
});
