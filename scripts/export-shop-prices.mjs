#!/usr/bin/env node
// 파츠 가격표를 프런트(TS) → 서버(JSON) 로 뽑아내는 생성 스크립트.
//
// 왜 손으로 못 옮기나:
//   apps/web/src/game/avatarParts.ts 는 파일 하단에서 네 카탈로그를 tier 기준으로
//   **안정 정렬**한다. 즉 "인덱스 → 가격" 매핑은 그 정렬이 끝난 뒤에야 확정된다.
//   게다가 EYES 는 (눈 모양 × 눈썹) 조합으로 만들어진다. 사람이 재현하면 반드시 어긋난다.
//   그래서 TS 를 실제로 평가해서 결과를 그대로 받아 적는다.
//
// TS 평가 방법: Node 자체 타입 스트리핑(--experimental-strip-types).
//   avatarParts.ts 는 모듈 로드 시점에 DOM 을 건드리지 않고(draw 함수 안에서만 ctx 사용),
//   타입은 전부 지울 수 있는(erasable) 문법이라 별도 번들러 없이 그냥 import 된다.
//   Node 22.18+/23.6+ 는 기본 활성이고, 그 이전(22.6+)은 플래그가 필요해서
//   플래그를 붙인 자식 프로세스로 한 번 다시 띄운다.
//
// 사용: pnpm shop:prices   (= node scripts/export-shop-prices.mjs)
// 출력: apps/api/app/game/shop_prices.json  — 커밋되는 산출물이다.

import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = dirname(HERE);
const SOURCE_REL = 'apps/web/src/game/avatarParts.ts';
const OUT_REL = 'apps/api/app/game/shop_prices.json';

// --------------------------------------------------------------------------
// Node 가 TS 를 못 읽으면 플래그를 달고 자기 자신을 한 번만 다시 띄운다.
// --------------------------------------------------------------------------

if (!process.features.typescript) {
  if (process.env.BULLET_BRAK_SHOP_PRICES_CHILD === '1') {
    console.error(
      '[shop:prices] 이 Node 는 TypeScript 를 읽지 못한다. Node 22.6 이상이 필요하다 ' +
        `(현재 ${process.version}).`,
    );
    process.exit(1);
  }
  const child = spawnSync(
    process.execPath,
    ['--experimental-strip-types', '--no-warnings', fileURLToPath(import.meta.url), ...process.argv.slice(2)],
    { stdio: 'inherit', env: { ...process.env, BULLET_BRAK_SHOP_PRICES_CHILD: '1' } },
  );
  process.exit(child.status ?? 1);
}

// --------------------------------------------------------------------------
// 카탈로그 평가
// --------------------------------------------------------------------------

const parts = await import(pathToFileURL(join(ROOT, SOURCE_REL)).href);

const { TIER_PRICE, EYES, MOUTHS, DETAILS, DETAILS2 } = parts;

// 슬롯 이름은 서버/클라이언트가 쓰는 아이템 키 포맷 "{category}:{index}" 의 category 다.
// colors 는 항상 무료라 가격표에 넣지 않는다.
const SLOTS = [
  ['eyes', EYES],
  ['mouths', MOUTHS],
  ['details', DETAILS],
  ['details2', DETAILS2],
];

function priceOf(tier) {
  const price = TIER_PRICE[tier];
  if (typeof price !== 'number' || !Number.isFinite(price) || price < 0) {
    throw new Error(`알 수 없는 등급 ${tier} — TIER_PRICE 를 확인할 것`);
  }
  return price;
}

const prices = {};
const tiers = {};
const names = {};

for (const [slot, list] of SLOTS) {
  if (!Array.isArray(list) || list.length === 0) {
    throw new Error(`${slot} 카탈로그가 비었다 — ${SOURCE_REL} 를 확인할 것`);
  }
  prices[slot] = list.map((opt) => priceOf(opt.tier));
  tiers[slot] = list.map((opt) => opt.tier);
  // 이름은 서버가 쓰지 않는다. 정렬 때문에 인덱스가 밀렸을 때 사람이 대조하라고 남긴다.
  names[slot] = list.map((opt) => String(opt.name));
}

// --------------------------------------------------------------------------
// 쓰기 — 두 번 돌려도 바이트가 같아야 한다(키 순서 고정 + \n 고정).
// --------------------------------------------------------------------------

const payload = {
  _generated:
    '이 파일은 생성물이다. 직접 고치지 말 것. ' +
    `가격의 단일 진실은 ${SOURCE_REL} 이며, \`pnpm shop:prices\` 로 재생성한다.`,
  _source: SOURCE_REL,
  _script: 'scripts/export-shop-prices.mjs',
  version: 1,
  tier_price: [...TIER_PRICE].map((n) => Number(n)),
  slots: prices,
  tiers,
  names,
};

const outPath = join(ROOT, OUT_REL);
mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');

const total = Object.values(prices).reduce((n, arr) => n + arr.length, 0);
console.log(`[shop:prices] ${OUT_REL} 갱신 — 슬롯 ${SLOTS.length}개, 파츠 ${total}개`);
for (const [slot, arr] of Object.entries(prices)) {
  const paid = arr.filter((p) => p > 0).length;
  console.log(`  ${slot.padEnd(8)} ${String(arr.length).padStart(3)}개 (유료 ${paid}개)`);
}
