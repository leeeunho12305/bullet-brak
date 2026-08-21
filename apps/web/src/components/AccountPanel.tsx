// 계정 — 아이디/비밀번호 만들기, 다른 기기에서 로그인, 인계 코드.
//
// 회원가입 화면이 따로 없다. 앱을 열면 이미 익명 계정이 하나 붙어 있고, 여기서
// 아이디/비밀번호를 정하면 **그 계정이 승격된다** — 그래서 코인과 아이템이 그대로
// 따라온다. 다른 기기에서는 그 아이디로 들어오면 같은 계정이 열린다.
import { memo, useCallback, useState } from 'react';
import type { FormEvent, JSX } from 'react';
import {
  issueRecoveryCode,
  setCredentials,
  signIn,
  signInWithCode,
  type AuthOutcome,
} from '@/api/identity';
import { useGameStore } from '@/store/gameStore';

/** 어떤 폼을 펼쳐 두고 있는가. 한 번에 하나만 연다 — 로비가 이미 빽빽하다. */
type Mode = 'idle' | 'signup' | 'login' | 'code';

const ID_MAX = 20;
const PASSWORD_MAX = 128;

/** 서버 규칙과 같은 값. 여기서 미리 걸러 주면 왕복 한 번을 아낀다(판정은 서버가 한다). */
const ID_MIN = 4;
const PASSWORD_MIN = 8;

function AccountPanelInner(): JSX.Element | null {
  const accountId = useGameStore((s) => s.accountId);
  const localOnly = useGameStore((s) => s.localOnly);
  const loginId = useGameStore((s) => s.loginId);
  const hasRecoveryCode = useGameStore((s) => s.hasRecoveryCode);
  const coins = useGameStore((s) => s.coins);

  const [mode, setMode] = useState<Mode>('idle');
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  /** 방금 발급받은 인계 코드. 화면을 벗어나면 영영 못 본다. */
  const [issued, setIssued] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const close = useCallback(() => {
    setMode('idle');
    setId('');
    setPassword('');
    setCode('');
    setMessage(null);
    setFailed(false);
  }, []);

  const open = useCallback(
    (next: Mode) => {
      close();
      setMode(next);
    },
    [close],
  );

  /** 로그인 결과를 화면 상태로 옮긴다. 성공하면 store 가 통째로 새 계정으로 바뀐다. */
  const settle = useCallback(
    (outcome: AuthOutcome) => {
      if (outcome.kind === 'ok') {
        useGameStore.getState().applyAccount(outcome.account);
        close();
        setMessage(`${outcome.account.nickname} 님으로 로그인했어요.`);
        setFailed(false);
        return;
      }
      setFailed(true);
      setMessage(
        outcome.kind === 'unavailable'
          ? '이 서버에는 계정 기능이 없어요.'
          : outcome.message,
      );
    },
    [close],
  );

  const submitSignup = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      try {
        // 이미 아이디가 있으면 이 폼은 '비밀번호 변경'이다 — 아이디는 그대로 다시 보낸다
        // (서버가 "내 계정이 이미 쓰는 아이디"를 taken 으로 치지 않는다).
        const result = await setCredentials(loginId ?? id, password);
        setFailed(!result.ok);
        setMessage(result.message);
        if (result.ok) {
          // 아이디가 붙었다는 사실만 갱신하면 된다 — 계정 자체는 그대로다.
          useGameStore.setState({ loginId: result.loginId });
          setMode('idle');
          setId('');
          setPassword('');
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, id, loginId, password],
  );

  const submitLogin = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      try {
        settle(await signIn(id, password));
      } finally {
        setBusy(false);
      }
    },
    [busy, id, password, settle],
  );

  const submitCode = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      try {
        settle(await signInWithCode(code));
      } finally {
        setBusy(false);
      }
    },
    [busy, code, settle],
  );

  const requestCode = useCallback(async () => {
    if (busy) return;
    // 재발급은 이전 코드를 죽인다. 되돌릴 수 없으니 한 번 물어본다.
    if (hasRecoveryCode && !window.confirm('새 코드를 만들면 기존 코드는 못 쓰게 돼요. 계속할까요?')) {
      return;
    }
    setBusy(true);
    try {
      const next = await issueRecoveryCode();
      if (next === null) {
        setFailed(true);
        setMessage('코드를 발급하지 못했어요. 잠시 후 다시 시도해 주세요.');
        return;
      }
      setIssued(next);
      setCopied(false);
      useGameStore.setState({ hasRecoveryCode: true });
    } finally {
      setBusy(false);
    }
  }, [busy, hasRecoveryCode]);

  const copyCode = useCallback(async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued);
      setCopied(true);
    } catch {
      /* 클립보드 권한이 없으면 사용자가 눈으로 보고 적으면 된다 */
    }
  }, [issued]);

  // 계정 기능이 없는 배포(서버에 DB 없음)에서는 통째로 감춘다.
  // 부팅이 끝나기 전(accountId 도 localOnly 도 아직 없을 때)에도 그리지 않는다 —
  // 잠깐 나타났다 사라지면 그게 더 헷갈린다.
  if (localOnly) {
    return (
      <p className="hint">💾 계정에 연결되지 않아 코인과 아이템이 이 브라우저에만 저장돼요.</p>
    );
  }
  if (!accountId) return null;

  const idTooShort = id.trim().length < ID_MIN;
  const passwordTooShort = password.length < PASSWORD_MIN;

  return (
    <div className="account-panel">
      {loginId ? (
        <p className="hint">
          🔐 <strong>@{loginId}</strong> 로 로그인돼 있어요. 다른 기기에서 이 아이디로
          들어오면 코인과 아이템이 그대로 따라와요.
        </p>
      ) : (
        <p className="hint">
          ⚠ 이 계정은 <strong>이 브라우저에만</strong> 묶여 있어요. 아이디를 만들어 두면
          다른 기기에서도, 저장소를 지워도 코인({coins})이 남아요.
        </p>
      )}

      {message ? (
        <p className={failed ? 'account-msg account-msg-bad' : 'account-msg account-msg-good'}>
          {message}
        </p>
      ) : null}

      {/* 방금 발급된 코드. 이 화면을 닫으면 다시 볼 수 없다. */}
      {issued ? (
        <div className="recovery-code">
          <p className="label">인계 코드</p>
          <code className="recovery-code-value">{issued}</code>
          <div className="row">
            <button type="button" className="btn" onClick={() => void copyCode()}>
              {copied ? '✅ 복사됨' : '📋 복사'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setIssued(null)}>
              적어 뒀어요
            </button>
          </div>
          <p className="hint">
            ⚠ <strong>다시 볼 수 없어요.</strong> 서버에는 코드가 아니라 그 지문만 남거든요.
            어딘가 적어 두고, 남에게 보이지 마세요 — 이 코드를 가진 사람은 계정에 들어올 수 있어요.
          </p>
        </div>
      ) : null}

      {mode === 'idle' ? (
        <div className="account-actions">
          <button type="button" className="btn btn-block" onClick={() => open('signup')}>
            {loginId ? '🔑 비밀번호 바꾸기' : '🔑 아이디 만들기'}
          </button>
          {!loginId ? (
            <button type="button" className="btn btn-ghost btn-block" onClick={() => open('login')}>
              이미 아이디가 있어요 (로그인)
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost btn-block"
            disabled={busy}
            onClick={() => void requestCode()}
          >
            {hasRecoveryCode ? '🎫 인계 코드 다시 발급' : '🎫 인계 코드 만들기'}
          </button>
          <button type="button" className="btn btn-ghost btn-block" onClick={() => open('code')}>
            인계 코드로 로그인
          </button>
        </div>
      ) : null}

      {mode === 'signup' ? (
        <form className="account-form" onSubmit={(e) => void submitSignup(e)}>
          <div className="field">
            <label className="label" htmlFor="loginId">
              아이디
            </label>
            <input
              id="loginId"
              className="input"
              value={loginId ?? id}
              maxLength={ID_MAX}
              placeholder="minsu99"
              autoComplete="username"
              disabled={Boolean(loginId)}
              onChange={(e) => setId(e.target.value.toLowerCase().slice(0, ID_MAX))}
            />
            <p className="hint">영문 소문자로 시작하는 {ID_MIN}~{ID_MAX}자 (소문자·숫자·밑줄)</p>
          </div>
          <div className="field">
            <label className="label" htmlFor="newPassword">
              비밀번호
            </label>
            <input
              id="newPassword"
              className="input"
              type="password"
              value={password}
              maxLength={PASSWORD_MAX}
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="hint">{PASSWORD_MIN}자 이상. 잊으면 인계 코드로만 되찾을 수 있어요.</p>
          </div>
          <div className="row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={busy || (!loginId && idTooShort) || passwordTooShort}
            >
              {busy ? <span className="spinner" aria-hidden /> : null}
              저장
            </button>
            <button type="button" className="btn btn-ghost" onClick={close}>
              취소
            </button>
          </div>
        </form>
      ) : null}

      {mode === 'login' ? (
        <form className="account-form" onSubmit={(e) => void submitLogin(e)}>
          {coins > 0 ? (
            <p className="hint">
              ⚠ 로그인하면 이 브라우저는 그 계정으로 바뀌어요. 지금 여기 있는 코인({coins})은
              따라가지 않고, 아이디를 만들어 두지 않았다면 다시 열 수 없어요.
            </p>
          ) : null}
          <div className="field">
            <label className="label" htmlFor="signinId">
              아이디
            </label>
            <input
              id="signinId"
              className="input"
              value={id}
              maxLength={ID_MAX}
              autoComplete="username"
              onChange={(e) => setId(e.target.value.toLowerCase().slice(0, ID_MAX))}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="signinPassword">
              비밀번호
            </label>
            <input
              id="signinPassword"
              className="input"
              type="password"
              value={password}
              maxLength={PASSWORD_MAX}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={busy || !id || !password}>
              {busy ? <span className="spinner" aria-hidden /> : null}
              로그인
            </button>
            <button type="button" className="btn btn-ghost" onClick={close}>
              취소
            </button>
          </div>
        </form>
      ) : null}

      {mode === 'code' ? (
        <form className="account-form" onSubmit={(e) => void submitCode(e)}>
          <div className="field">
            <label className="label" htmlFor="recoveryCode">
              인계 코드
            </label>
            <input
              id="recoveryCode"
              className="input code-input"
              value={code}
              maxLength={20}
              autoComplete="off"
              placeholder="XXXX-XXXX-XXXX"
              onChange={(e) => setCode(e.target.value.toUpperCase())}
            />
            <p className="hint">하이픈과 대소문자는 신경 쓰지 않아도 돼요.</p>
          </div>
          <div className="row">
            <button type="submit" className="btn btn-primary" disabled={busy || code.length < 12}>
              {busy ? <span className="spinner" aria-hidden /> : null}
              로그인
            </button>
            <button type="button" className="btn btn-ghost" onClick={close}>
              취소
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

const AccountPanel = memo(AccountPanelInner);
export default AccountPanel;
