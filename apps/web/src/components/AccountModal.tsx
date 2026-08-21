// 계정 모달 — 아이디/비밀번호 만들기, 다른 기기에서 로그인, 인계 코드.
//
// 회원가입 화면이 따로 없다. 앱을 열면 이미 익명 계정이 하나 붙어 있고, 여기서
// 아이디/비밀번호를 정하면 **그 계정이 승격된다** — 그래서 코인과 아이템이 그대로
// 따라온다. 다른 기기에서는 그 아이디로 들어오면 같은 계정이 열린다.
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent, JSX } from 'react';
import {
  issueRecoveryCode,
  setCredentials,
  signIn,
  signInWithCode,
  type AuthOutcome,
} from '@/api/identity';
import { useGameStore } from '@/store/gameStore';

/** 모달 안의 탭. 한 번에 하나만 보여 준다. */
type Tab = 'create' | 'login' | 'code';

const ID_MAX = 20;
const PASSWORD_MAX = 128;

/** 서버 규칙과 같은 값. 여기서 미리 걸러 주면 왕복 한 번을 아낀다(판정은 서버가 한다). */
const ID_MIN = 4;
const PASSWORD_MIN = 8;

/** 인계 코드는 하이픈을 빼면 12자다. 그 아래로는 보낼 필요도 없다. */
const CODE_MIN = 12;

interface Props {
  onClose(): void;
}

export default function AccountModal({ onClose }: Props): JSX.Element {
  const loginId = useGameStore((s) => s.loginId);
  const hasRecoveryCode = useGameStore((s) => s.hasRecoveryCode);
  const coins = useGameStore((s) => s.coins);
  const nickname = useGameStore((s) => s.nickname);

  const [tab, setTab] = useState<Tab>('create');
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  /** 방금 발급받은 인계 코드. 이 화면을 벗어나면 영영 못 본다. */
  const [issued, setIssued] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Esc 로 닫는다(튜토리얼과 같은 규칙).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const switchTab = useCallback((next: Tab) => {
    setTab(next);
    setPassword('');
    setCode('');
    setMessage(null);
    setFailed(false);
  }, []);

  /** 로그인 결과를 화면 상태로 옮긴다. 성공하면 store 가 통째로 새 계정으로 바뀐다. */
  const settle = useCallback((outcome: AuthOutcome) => {
    if (outcome.kind === 'ok') {
      useGameStore.getState().applyAccount(outcome.account);
      setPassword('');
      setCode('');
      setFailed(false);
      setMessage(`${outcome.account.nickname} 님으로 로그인했어요.`);
      return;
    }
    setFailed(true);
    setMessage(
      outcome.kind === 'unavailable' ? '이 서버에는 계정 기능이 없어요.' : outcome.message,
    );
  }, []);

  const submitCreate = useCallback(
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
    if (
      hasRecoveryCode &&
      !window.confirm('새 코드를 만들면 기존 코드는 못 쓰게 돼요. 계속할까요?')
    ) {
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
      setMessage(null);
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

  const idTooShort = id.trim().length < ID_MIN;
  const passwordTooShort = password.length < PASSWORD_MIN;

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="계정"
      // 바깥을 눌러도 닫힌다. 안쪽 클릭이 올라와서 닫히지 않게 대상까지 확인한다.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal account-modal">
        <header className="modal-head">
          <h2>
            <span aria-hidden>🔐</span> 계정
          </h2>
          <button
            type="button"
            className="btn btn-ghost modal-x"
            onClick={onClose}
            aria-label="닫기"
          >
            ✕
          </button>
        </header>

        <div className="modal-body account-body">
          {/* 지금 상태 — 이 계정이 어디에 묶여 있는지부터 알려 준다. */}
          {loginId ? (
            <p className="account-state is-safe">
              🔐 <strong>@{loginId}</strong> 로 로그인돼 있어요. 다른 기기에서 이 아이디로
              들어오면 코인({coins})과 아이템이 그대로 따라와요.
            </p>
          ) : (
            <p className="account-state is-warn">
              ⚠ <strong>{nickname || '익명'}</strong> 님의 계정은 지금 <strong>이 브라우저에만</strong>{' '}
              묶여 있어요. 아이디를 만들어 두면 다른 기기에서도, 저장소를 지워도 코인({coins})이 남아요.
            </p>
          )}

          <div className="account-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'create'}
              className={tab === 'create' ? 'btn is-on' : 'btn btn-ghost'}
              onClick={() => switchTab('create')}
            >
              {loginId ? '비밀번호' : '아이디'}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'login'}
              className={tab === 'login' ? 'btn is-on' : 'btn btn-ghost'}
              onClick={() => switchTab('login')}
            >
              로그인
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'code'}
              className={tab === 'code' ? 'btn is-on' : 'btn btn-ghost'}
              onClick={() => switchTab('code')}
            >
              인계 코드
            </button>
          </div>

          {message ? (
            <p className={failed ? 'account-msg account-msg-bad' : 'account-msg account-msg-good'}>
              {message}
            </p>
          ) : null}

          {tab === 'create' ? (
            <form className="account-form" onSubmit={(e) => void submitCreate(e)}>
              <div className="field">
                <label className="label" htmlFor="accountId">
                  아이디
                </label>
                {loginId ? (
                  // 이미 정해진 아이디는 바꾸지 않는다 — 이 폼은 비밀번호 변경이다.
                  <p className="account-fixed-id">@{loginId}</p>
                ) : (
                  <>
                    <input
                      id="accountId"
                      className="input"
                      value={id}
                      maxLength={ID_MAX}
                      placeholder="minsu99"
                      autoComplete="username"
                      onChange={(e) => setId(e.target.value.toLowerCase().slice(0, ID_MAX))}
                    />
                    <p className="hint">
                      영문 소문자로 시작하는 {ID_MIN}~{ID_MAX}자 (소문자·숫자·밑줄). 대소문자는
                      가리지 않아요.
                    </p>
                  </>
                )}
              </div>

              <div className="field">
                <label className="label" htmlFor="accountPassword">
                  {loginId ? '새 비밀번호' : '비밀번호'}
                </label>
                <input
                  id="accountPassword"
                  className="input"
                  type="password"
                  value={password}
                  maxLength={PASSWORD_MAX}
                  autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)}
                />
                <p className="hint">
                  {PASSWORD_MIN}자 이상. 잊으면 인계 코드로만 되찾을 수 있으니 하나 만들어 두세요.
                </p>
              </div>

              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={busy || (!loginId && idTooShort) || passwordTooShort}
              >
                {busy ? <span className="spinner" aria-hidden /> : null}
                {loginId ? '비밀번호 바꾸기' : '아이디 만들기'}
              </button>

              {!loginId ? (
                <p className="hint">
                  💡 지금 쓰던 계정에 로그인 수단만 붙는 거예요. <strong>새 계정이 아니라서</strong>{' '}
                  코인·아이템·아바타가 그대로 남아요.
                </p>
              ) : null}
            </form>
          ) : null}

          {tab === 'login' ? (
            <form className="account-form" onSubmit={(e) => void submitLogin(e)}>
              {!loginId && coins > 0 ? (
                <p className="account-state is-warn">
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
                  placeholder="minsu99"
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

              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={busy || !id || !password}
              >
                {busy ? <span className="spinner" aria-hidden /> : null}
                로그인
              </button>
              <p className="hint">
                비밀번호가 기억나지 않으면 <strong>인계 코드</strong> 탭에서 코드로 들어올 수 있어요.
              </p>
            </form>
          ) : null}

          {tab === 'code' ? (
            <div className="account-form">
              {/* 발급 직후에만 보이는 코드. 이 화면을 닫으면 다시 볼 수 없다. */}
              {issued ? (
                <div className="recovery-code">
                  <p className="label">내 인계 코드</p>
                  <code className="recovery-code-value">{issued}</code>
                  <div className="row">
                    <button type="button" className="btn" onClick={() => void copyCode()}>
                      {copied ? '✅ 복사됨' : '📋 복사'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setIssued(null)}
                    >
                      적어 뒀어요
                    </button>
                  </div>
                  <p className="hint">
                    ⚠ <strong>다시 볼 수 없어요.</strong> 서버에는 코드가 아니라 그 지문만 남거든요.
                    어딘가 적어 두고 남에게 보이지 마세요 — 이 코드를 가진 사람은 계정에 들어올 수
                    있어요.
                  </p>
                </div>
              ) : (
                <div className="field">
                  <p className="hint">
                    비밀번호를 잊었을 때 쓰는 열쇠예요. 발급해서 <strong>어딘가 적어 두면</strong>{' '}
                    어느 기기에서든 이 코드로 계정을 열 수 있어요.
                  </p>
                  <button
                    type="button"
                    className="btn btn-block"
                    disabled={busy}
                    onClick={() => void requestCode()}
                  >
                    {busy ? <span className="spinner" aria-hidden /> : null}
                    {hasRecoveryCode ? '🎫 코드 다시 발급' : '🎫 코드 발급받기'}
                  </button>
                  {hasRecoveryCode ? (
                    <p className="hint">
                      이미 코드가 하나 있어요. 다시 발급하면 <strong>예전 코드는 못 쓰게 됩니다</strong>{' '}
                      — 유출됐을 때 이렇게 무효로 만드세요.
                    </p>
                  ) : null}
                </div>
              )}

              <div className="divider" />

              <form onSubmit={(e) => void submitCode(e)}>
                <div className="field">
                  <label className="label" htmlFor="recoveryCode">
                    코드로 로그인
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
                <button
                  type="submit"
                  className="btn btn-primary btn-block"
                  disabled={busy || code.replace(/[^0-9A-Z]/g, '').length < CODE_MIN}
                >
                  {busy ? <span className="spinner" aria-hidden /> : null}
                  코드로 로그인
                </button>
              </form>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
