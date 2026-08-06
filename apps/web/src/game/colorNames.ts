// 플레이어 색 → 사람이 부르는 이름 ("HALF BLUE" 처럼 라운드 결과 문구에 쓴다).
//
// 서버 팔레트(constants.AVATAR_PALETTE)를 표로 박아 두지 않고 색상(hue)으로 판정한다.
// 팔레트가 늘거나 커스텀 색이 들어와도 항상 그럴듯한 이름이 나와야 하기 때문이다.
// 현재 팔레트 11색은 아래 구간에서 전부 서로 다른 이름으로 떨어진다.

interface Hsl {
  h: number; // 0..360
  s: number; // 0..1
  l: number; // 0..1
}

/** #rgb / #rrggbb → HSL. 못 읽으면 null. */
function toHsl(hex: string): Hsl | null {
  let body = (hex || '').trim().replace(/^#/, '');
  if (body.length === 3) body = body[0] + body[0] + body[1] + body[1] + body[2] + body[2];
  if (body.length !== 6 || !/^[0-9a-f]{6}$/i.test(body)) return null;

  const r = parseInt(body.slice(0, 2), 16) / 255;
  const g = parseInt(body.slice(2, 4), 16) / 255;
  const b = parseInt(body.slice(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const l = (max + min) / 2;
  if (delta === 0) return { h: 0, s: 0, l };

  const s = delta / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === r) h = 60 * (((g - b) / delta) % 6);
  else if (max === g) h = 60 * ((b - r) / delta + 2);
  else h = 60 * ((r - g) / delta + 4);
  if (h < 0) h += 360;
  return { h, s, l };
}

/** 색상환 구간 → 이름. [상한(미만), 이름] 순서대로 검사한다. */
const HUE_NAMES: ReadonlyArray<readonly [number, string]> = [
  [12, 'RED'],
  [40, 'ORANGE'],
  [66, 'YELLOW'],
  [100, 'LIME'],
  [150, 'GREEN'],
  [175, 'TEAL'],
  [200, 'CYAN'],
  [222, 'BLUE'],
  [245, 'INDIGO'],
  [290, 'VIOLET'],
  [345, 'PINK'],
  [360, 'RED'], // 345~360 은 다시 빨강
];

/**
 * 색 이름(대문자). 알아볼 수 없는 값이면 fallback 을 돌려준다.
 *
 * 채도가 거의 없으면 색상 대신 밝기로 부른다(회색 계열에 "RED" 라고 하면 안 된다).
 */
export function colorName(hex: string, fallback = 'PLAYER'): string {
  const hsl = toHsl(hex);
  if (!hsl) return fallback;
  if (hsl.s < 0.15) {
    if (hsl.l > 0.85) return 'WHITE';
    if (hsl.l < 0.15) return 'BLACK';
    return 'GREY';
  }
  for (const [limit, name] of HUE_NAMES) {
    if (hsl.h < limit) return name;
  }
  return fallback;
}

export default colorName;
