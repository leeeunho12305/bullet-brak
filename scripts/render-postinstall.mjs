// 루트 package.json 의 postinstall 훅. 평소에는 아무것도 하지 않고 즉시 빠져나간다.
//
// 왜 존재하나 —
//   Render 대시보드에서 손으로 만든 서비스는 Build Command 가 기본값 `yarn` 이고,
//   이 값은 저장소의 render.yaml 로 덮어쓸 수 없다(render.yaml 은 Blueprint 로 만든
//   서비스에만 적용된다). 즉 저장소만 고쳐서는 빌드 커맨드를 바꿀 방법이 없다.
//   그런데 `yarn` 이 하는 일은 `yarn install` 하나뿐이고, install 은 postinstall 훅을 부른다.
//   그래서 그 훅에 실제 빌드(scripts/render-build.sh)를 매달았다.
//
//   대시보드에서 Build Command 를 ./scripts/render-build.sh 로 바꾸거나 Blueprint 로
//   재생성하면 이 파일은 그냥 놀게 된다(재귀 가드에 걸려 바로 종료). 그게 더 깔끔한 상태다.
import { spawnSync } from 'node:child_process';

// Render 빌드 환경에서만 동작한다. 로컬·CI·도커에서는 pnpm install 이 느려지면 안 된다.
const onRender = process.env.RENDER === 'true' || Boolean(process.env.RENDER_SERVICE_ID);

// 재귀 가드: render-build.sh 안의 pnpm install 이 이 훅을 다시 부른다.
const alreadyBuilding = process.env.BULLET_BRAK_RENDER_BUILD === '1';

if (!onRender || alreadyBuilding) {
  process.exit(0);
}

console.log('==> Render 감지: postinstall 에서 pnpm 빌드로 넘어간다 (Build Command 가 `yarn` 이라서)');

const result = spawnSync('sh', ['scripts/render-build.sh'], {
  stdio: 'inherit',
  env: { ...process.env, BULLET_BRAK_RENDER_BUILD: '1' },
});

if (result.error) {
  console.error('==> render-build.sh 실행 실패:', result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
