// 로컬 개발 스크립트(setup-api.mjs / dev.mjs)가 공유하는 경로·인터프리터 탐색.
// 의존성 0 — pnpm install 전에도 돌아야 한다.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const API_DIR = path.join(ROOT, 'apps', 'api');
export const WEB_DIR = path.join(ROOT, 'apps', 'web');
export const VENV_DIR = path.join(API_DIR, '.venv');

const isWindows = process.platform === 'win32';
const VENV_BIN = path.join(VENV_DIR, isWindows ? 'Scripts' : 'bin');

/** venv 인터프리터 경로. 존재 여부는 호출한 쪽에서 확인한다. */
export function venvPython() {
  return path.join(VENV_BIN, isWindows ? 'python.exe' : 'python');
}

/**
 * venv 를 만들 수 있는 시스템 python 을 찾는다. PYTHON 환경변수가 있으면 그걸 먼저 쓴다.
 * Windows 는 python.exe 가 Microsoft Store 스텁일 수 있어서(실행하면 스토어가 열린다)
 * 실제로 --version 이 나오는지 확인한다.
 */
export function findSystemPython() {
  const candidates = process.env.PYTHON
    ? [{ cmd: process.env.PYTHON, args: [] }]
    : isWindows
      ? [{ cmd: 'py', args: ['-3'] }, { cmd: 'python', args: [] }, { cmd: 'python3', args: [] }]
      : [{ cmd: 'python3', args: [] }, { cmd: 'python', args: [] }];

  for (const c of candidates) {
    const r = spawnSync(c.cmd, [...c.args, '--version'], { encoding: 'utf8' });
    if (r.status === 0 && /Python 3\.(1[0-9]|[2-9][0-9])/.test(`${r.stdout}${r.stderr}`)) return c;
  }
  return null;
}

/** vite 실행 파일(.js). pnpm 을 한 번 더 거치지 않고 node 로 직접 띄운다. */
export function viteBin() {
  return path.join(WEB_DIR, 'node_modules', 'vite', 'bin', 'vite.js');
}

export function webDepsInstalled() {
  return existsSync(viteBin());
}
