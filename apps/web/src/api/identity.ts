// 디바이스 토큰 기반 신원. docs/PROTOCOL.md §1.
//
// 로그인 화면 없이 계정을 갖기 위한 장치다. 브라우저가 불투명 토큰 하나를
// localStorage 에 들고 있고, 서버는 그 해시로 계정을 찾는다.
//
// **이 모듈은 실패해도 앱을 막지 않는다.** 서버에 DB 가 없거나(503) 네트워크가
// 죽어 있으면 조용히 '로컬 모드'로 떨어지고, 게임은 예전처럼 localStorage 만으로 돈다.
// 그래서 여기서 던지는 예외는 하나도 없다 — 전부 null 로 흡수한다.
import {
  ApiError,
  api,
  type AccountResponse,
  type AuthResultResponse,
  type BuyItemResponse,
} from '@/api/client';
import type { Customization } from '@/types/game';

/** 토큰 저장 키. 이 값을 잃으면 그 계정으로 다시 못 돌아온다. */
export const TOKEN_KEY = 'bulletBrakToken';

/** 최초 계정 생성 시 서버로 넘길 localStorage 잔재 */
export interface IdentitySeed {
  nickname: string;
  customization: Customization;
  coins: number;
  ownedItems: string[];
}

export function loadToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // 시크릿 모드 등
  }
}

function saveToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* 저장 못 해도 이번 세션은 메모리의 토큰으로 굴러간다 */
  }
}

function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 무시 */
  }
}

/**
 * 토큰을 확보하고 계정을 가져온다.
 *
 * 1. 토큰이 있으면 그걸로 조회한다. 서버가 401 이면(계정이 지워졌거나 DB 를 갈아엎었거나)
 *    낡은 토큰을 버리고 새로 발급받는다.
 * 2. 토큰이 없으면 localStorage 프로필을 씨앗으로 넘겨 익명 계정을 만든다.
 *
 * @returns 계정, 또는 계정 기능을 쓸 수 없을 때 null(= 로컬 모드)
 */
export async function bootstrapIdentity(seed: IdentitySeed): Promise<AccountResponse | null> {
  const existing = loadToken();

  if (existing) {
    try {
      return await api.getMe(existing);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken(); // 낡은 토큰 — 아래에서 새로 만든다
      } else {
        return null; // 503(DB 없음) / 네트워크 오류 -> 로컬 모드
      }
    }
  }

  try {
    const created = await api.createAnonAccount({
      nickname: seed.nickname,
      customization: seed.customization,
      seed_coins: seed.coins,
      seed_items: seed.ownedItems,
    });
    saveToken(created.token);
    return created.account;
  } catch {
    return null;
  }
}

/**
 * 닉네임/아바타를 서버에 올린다. 실패는 무시한다 —
 * 값은 이미 localStorage 에 있으므로 다음 기회에 다시 올라간다.
 */
export async function pushProfile(patch: {
  nickname?: string;
  customization?: Customization;
}): Promise<void> {
  const token = loadToken();
  if (!token) return;
  try {
    await api.patchMe(token, patch);
  } catch {
    /* 프로필 동기화 실패로 게임을 막지 않는다 */
  }
}

/**
 * 구매 시도의 결말. 세 갈래인 이유:
 * - 'local'  : 계정 자체가 없다(토큰 없음 / 서버에 DB 없음). 호출부가 예전처럼 localStorage 로 처리한다.
 * - 'server' : 서버가 판정했다. 성공이든 거절이든 응답이 곧 진실이다.
 * - 'error'  : 계정은 있는데 서버에 못 닿았다. 이때 로컬로 깎아버리면 서버와 어긋나므로 아무것도 하지 않는다.
 */
export type PurchaseOutcome =
  | { kind: 'local' }
  | { kind: 'server'; result: BuyItemResponse }
  | { kind: 'error'; message: string };

/** 토큰이 있으면 서버에 구매를 맡긴다. 없으면 로컬 모드임을 알린다. */
export async function purchaseItem(itemKey: string): Promise<PurchaseOutcome> {
  const token = loadToken();
  if (!token) return { kind: 'local' };

  try {
    return { kind: 'server', result: await api.buyItem(token, itemKey) };
  } catch (err) {
    // 503 = 서버에 DB 가 없다. 계정 기능이 통째로 꺼진 배포이므로 로컬 모드로 되돌아간다.
    if (err instanceof ApiError && err.status === 503) return { kind: 'local' };
    if (err instanceof ApiError && err.status === 401) {
      // 토큰이 서버에서 사라졌다. 다음 부팅 때 bootstrapIdentity 가 새로 발급한다.
      clearToken();
      return { kind: 'error', message: '계정 정보가 만료됐습니다. 새로고침 후 다시 시도해 주세요.' };
    }
    return { kind: 'error', message: '구매에 실패했습니다. 잠시 후 다시 시도해 주세요.' };
  }
}

/** 아바타 편집기는 드래그 한 번에 수십 번 값을 바꾼다. 멈춘 뒤에 한 번만 올린다. */
const PUSH_DELAY_MS = 800;
let pushTimer: ReturnType<typeof setTimeout> | null = null;
let pending: { nickname?: string; customization?: Customization } = {};

export function pushProfileDebounced(patch: {
  nickname?: string;
  customization?: Customization;
}): void {
  pending = { ...pending, ...patch };
  if (pushTimer !== null) clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    const payload = pending;
    pending = {};
    pushTimer = null;
    void pushProfile(payload);
  }, PUSH_DELAY_MS);
}

// ── 로그인 ────────────────────────────────────────────────────────────────
//
// 어느 경로(아이디/비밀번호, 인계 코드)든 서버가 돌려주는 건 **이 기기의 디바이스
// 토큰** 하나다. 그 토큰을 localStorage 에 덮어쓰는 순간부터 이 브라우저가 그
// 계정이 된다 — 세션도 쿠키도 없고, 게임(WS) 쪽 경로는 아무것도 바뀌지 않는다.

/**
 * 로그인 시도의 결말.
 * - 'ok'          : 계정이 바뀌었다. 호출부가 store 의 applyAccount 로 반영한다.
 * - 'rejected'    : 서버가 정상적으로 거절했다(아이디/비번 틀림, 코드 틀림).
 * - 'unavailable' : 서버에 DB 가 없다. 이 배포에는 계정 기능 자체가 없다.
 * - 'error'       : 못 닿았거나 시도 제한(429)에 걸렸다.
 */
export type AuthOutcome =
  | { kind: 'ok'; account: AccountResponse }
  | { kind: 'rejected'; message: string }
  | { kind: 'unavailable' }
  | { kind: 'error'; message: string };

/** 거절 사유 -> 사용자 문구. 서버가 일부러 뭉뚱그려 주는 값이라 여기서도 뭉뚱그린다. */
function rejectionText(reason: string): string {
  if (reason === 'invalid_code') return '코드를 찾을 수 없어요. 다시 확인해 주세요.';
  return '아이디 또는 비밀번호가 올바르지 않아요.';
}

/** 로그인 계열 응답을 공통 처리한다 — 성공하면 토큰을 갈아 끼운다. */
function settle(result: AuthResultResponse): AuthOutcome {
  if (!result.ok || !result.token || !result.account) {
    return { kind: 'rejected', message: rejectionText(result.reason) };
  }
  // 여기서부터 이 브라우저는 다른 계정이다. 예전 토큰은 버린다(계정에는 남아 있지만
  // 이 기기가 더 이상 그걸로 들어가지 않는다).
  saveToken(result.token);
  return { kind: 'ok', account: result.account };
}

function authFailure(err: unknown): AuthOutcome {
  if (err instanceof ApiError && err.status === 503) return { kind: 'unavailable' };
  if (err instanceof ApiError) return { kind: 'error', message: err.message };
  return { kind: 'error', message: '로그인에 실패했어요. 잠시 후 다시 시도해 주세요.' };
}

/** 아이디/비밀번호 로그인. */
export async function signIn(loginId: string, password: string): Promise<AuthOutcome> {
  try {
    return settle(await api.login(loginId, password));
  } catch (err) {
    return authFailure(err);
  }
}

/** 인계 코드 로그인. 비밀번호를 잊었을 때의 우회로다. */
export async function signInWithCode(code: string): Promise<AuthOutcome> {
  try {
    return settle(await api.redeemCode(code));
  } catch (err) {
    return authFailure(err);
  }
}

/** 아이디/비밀번호 설정 결과. `ok` 가 false 여도 message 는 항상 보여줄 값이 들어 있다. */
export interface CredentialsOutcome {
  ok: boolean;
  message: string;
  /** 성공했을 때 확정된 아이디(서버가 소문자로 정규화한 값) */
  loginId: string | null;
}

/**
 * 지금 쓰던 계정에 아이디/비밀번호를 붙인다(이미 있으면 변경).
 *
 * **새 계정을 만드는 게 아니다** — 코인도 아이템도 그대로 있는 채로 그 계정에
 * 로그인 수단만 생긴다. 그래서 별도의 회원가입 화면이 없다.
 */
export async function setCredentials(
  loginId: string,
  password: string,
): Promise<CredentialsOutcome> {
  const token = loadToken();
  if (!token) {
    return { ok: false, message: '계정 기능을 쓸 수 없는 상태예요.', loginId: null };
  }
  try {
    const res = await api.setCredentials(token, loginId, password);
    return { ok: res.ok, message: res.message, loginId: res.login_id };
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      return { ok: false, message: '이 서버에는 계정 기능이 없어요.', loginId: null };
    }
    return { ok: false, message: '저장하지 못했어요. 잠시 후 다시 시도해 주세요.', loginId: null };
  }
}

/**
 * 인계 코드를 발급한다. 돌려준 평문은 **다시 볼 수 없다** — 서버는 해시만 갖는다.
 *
 * ⚠ 이미 코드가 있었다면 이 호출로 그 코드는 죽는다. 그게 곧 "유출됐을 때의 폐기 수단"이다.
 */
export async function issueRecoveryCode(): Promise<string | null> {
  const token = loadToken();
  if (!token) return null;
  try {
    return (await api.issueRecoveryCode(token)).code;
  } catch {
    return null;
  }
}
