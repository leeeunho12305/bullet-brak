// package.json 에서 packageManager 필드를 지운다. 빌드 산출물이 업로드되기 직전에 돈다.
//
// 왜 필요한가 —
//   corepack 은 프로젝트에 spec 이 없으면 자기가 하나 써 넣는다(auto-pin).
//     ! The local project doesn't define a 'packageManager' field.
//       Corepack will now add one referencing pnpm@9.15.4.
//   그 결과 빌드 중에 "packageManager": "pnpm@9.15.4" 가 되살아나고, 그대로 업로드되면
//   런타임에서 Start Command(`yarn start`)가 corepack 검사에 걸려 죽는다.
//     This project is configured to use pnpm because .../package.json has a "packageManager" field
//   이 저장소는 그 필드가 있으면 안 된다(이유는 package.json 의 //packageManager 주석 참고).
import { readFileSync, writeFileSync } from 'node:fs';

const PATH = 'package.json';
const pkg = JSON.parse(readFileSync(PATH, 'utf8'));

const removed = [];
if (pkg.packageManager !== undefined) {
  removed.push(`packageManager=${pkg.packageManager}`);
  delete pkg.packageManager;
}
if (pkg.devEngines?.packageManager !== undefined) {
  removed.push('devEngines.packageManager');
  delete pkg.devEngines.packageManager;
}

if (removed.length === 0) {
  console.log('==> package.json 에 packageManager 필드 없음 (정상)');
} else {
  writeFileSync(PATH, `${JSON.stringify(pkg, null, 2)}\n`);
  console.log(`==> package.json 에서 제거: ${removed.join(', ')} (런타임 corepack 충돌 방지)`);
}
