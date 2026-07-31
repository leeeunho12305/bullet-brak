// 인게임 채팅. store.chat 을 표시하고 Enter 로 전송한다.
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type { JSX, KeyboardEvent } from 'react';
import { net } from '@/net/connection';
import { useGameStore } from '@/store/gameStore';
import type { ChatMessage } from '@/types/game';

const QUICK_CHATS = ['좋은 판!', '미안!', '한 판 더!', '잘한다!'];
const EMOTES = ['😂', '😎', '💀', '🤯'];
const MAX_VISIBLE = 30;

interface StoreSlice {
  chat: readonly ChatMessage[];
}

function ChatBoxInner(): JSX.Element {
  const chat = useGameStore((s: StoreSlice) => s.chat);
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // 새 메시지가 오면 항상 맨 아래로.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat]);

  // Enter 로 입력창 포커스, Esc 로 해제 (게임 입력과 충돌하지 않도록 여기서만 처리).
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent): void => {
      const el = document.activeElement;
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
      if (e.key === 'Enter' && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === 'Escape' && typing) {
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const sendText = useCallback((value: string) => {
    const trimmed = value.trim().slice(0, 80);
    if (!trimmed) return;
    if (net.isOpen()) net.send({ type: 'chat', text: trimmed });
  }, []);

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        sendText(text);
        setText('');
        e.currentTarget.blur();
      } else if (e.key === 'Escape') {
        e.currentTarget.blur();
      }
    },
    [sendText, text],
  );

  const visible = chat.length > MAX_VISIBLE ? chat.slice(chat.length - MAX_VISIBLE) : chat;

  return (
    <div className="chat-box panel">
      <div className="chat-log" ref={listRef}>
        {visible.map((m, i) => (
          <div className="chat-line" key={`${m.time}-${i}`}>
            <span className="chat-sender">{m.sender}</span>
            <span className="chat-text">{m.text}</span>
          </div>
        ))}
        {visible.length === 0 && <div className="chat-empty">Enter 를 눌러 채팅하세요.</div>}
      </div>

      <div className="chat-quick">
        {QUICK_CHATS.map((q) => (
          <button type="button" key={q} className="btn btn-ghost chat-quick-btn" onClick={() => sendText(q)}>
            {q}
          </button>
        ))}
      </div>
      <div className="chat-quick">
        {EMOTES.map((e) => (
          <button type="button" key={e} className="btn btn-ghost chat-emote" onClick={() => sendText(e)}>
            {e}
          </button>
        ))}
      </div>

      <input
        ref={inputRef}
        className="input chat-input"
        value={text}
        maxLength={80}
        placeholder="메시지 입력 후 Enter"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />
    </div>
  );
}

export const ChatBox = memo(ChatBoxInner);
export default ChatBox;
