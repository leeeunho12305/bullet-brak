// `pnpm setup:api` — 백엔드 venv 를 만들고 의존성을 넣는다. (make 없이 pnpm 만으로)
//
// make setup 과 같은 일을 하지만 Windows/macOS/Linux 를 한 파일로 처리하고,
// 깨진 venv(pyvenv.cfg 나 인터프리터가 없는 껍데기)를 감지하면 지우고 다시 만든다.
// 도커에서 만든 venv 가 바인드 마운트로 새어 들어오거나 생성이 중간에 끊기면 이 상태가 된다.
import { spawnSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { API_DIR, findSystemPython, venvPython, VENV_DIR } from './dev-env.mjs';

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (r.error) {
    console.error(`실행 실패: ${cmd} — ${r.error.message}`);
    process.exit(1);
  }
  if (r.status !== 0) process.exit(r.status ?? 1);
}

const python = findSystemPython();
if (!python) {
  console.error('python 을 찾지 못했다. Python 3.11 이상을 설치하고 PATH 에 넣거나 PYTHON=... 로 경로를 지정한다.');
  console.error('  Windows: winget install Python.Python.3.12');
  process.exit(1);
}

// 껍데기 venv 정리 — 있으면 지우고 처음부터 만든다.
if (existsSync(VENV_DIR) && !existsSync(venvPython())) {
  console.log(`==> 손상된 venv 를 발견해 삭제한다: ${VENV_DIR}`);
  rmSync(VENV_DIR, { recursive: true, force: true });
}

if (!existsSync(venvPython())) {
  console.log(`==> venv 생성: ${VENV_DIR}`);
  run(python.cmd, [...python.args, '-m', 'venv', '.venv'], { cwd: API_DIR });
}

const py = venvPython();
console.log('==> 백엔드 의존성 설치');
run(py, ['-m', 'pip', 'install', '--upgrade', 'pip', '--quiet']);
run(py, ['-m', 'pip', 'install', '-r', 'requirements-dev.txt'], { cwd: API_DIR });

console.log('\n완료. `pnpm dev` 로 api(:8000) + web(:5173) 를 함께 띄운다.');
