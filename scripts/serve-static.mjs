// 의존성 없는 정적 파일 서버. apps/web/dist 를 $PORT 에 서빙한다.
//
// Render 에서 이 저장소를 Static Site 가 아니라 Node Web Service 로 만들었을 때 쓰인다
// (그 경우 Start Command 기본값이 `yarn start` 라서 루트 package.json 의 start 가 이걸 부른다).
// 도커/단일 VM 운영 경로는 여전히 nginx(apps/web/nginx.conf) 다. 이 파일은 그 대체재가 아니라
// "대시보드를 못 건드리는 상황"의 안전망이다.
//
// API(/api, /ws)는 프록시하지 않는다. 프런트가 VITE_API_BASE / VITE_WS_BASE 로 직접 붙는다.
import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve, sep } from 'node:path';

const ROOT = resolve(process.cwd(), 'apps/web/dist');
const PORT = Number(process.env.PORT ?? 8080);

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

createServer((req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }

  const url = req.url ?? '/';
  if (url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' }).end('ok\n');
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
}).listen(PORT, '0.0.0.0', () => {
  console.log(`정적 서버 http://0.0.0.0:${PORT} -> ${ROOT}`);
});
