// `pnpm test:api` — venv 파이썬으로 pytest 를 돌린다.
// (`pnpm exec pytest` 는 pnpm 이 node_modules/.bin 만 보기 때문에 동작하지 않는다.)
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { API_DIR, venvPython } from './dev-env.mjs';

const py = venvPython();
if (!existsSync(py)) {
  console.error(`백엔드 venv 가 없다: ${py}\n먼저 \`pnpm bootstrap\` 을 실행한다.`);
  process.exit(1);
}

const args = process.argv.slice(2);
const r = spawnSync(py, ['-m', 'pytest', ...(args.length ? args : ['tests', '-q'])], {
  cwd: API_DIR,
  stdio: 'inherit',
});
process.exit(r.status ?? 1);
