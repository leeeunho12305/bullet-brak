"""비밀번호 해싱.

**이 모듈의 두 함수는 절대 이벤트 루프에서 직접 부르면 안 된다.** bcrypt 는 일부러
느리게 설계된 함수라 한 번에 수십~수백 ms 동안 CPU 를 붙잡는다. 그런데 이 서버의
이벤트 루프는 60Hz 게임 틱 루프(`app/main.py`)와 **같은 루프**다 — 여기서 한 번
동기로 해싱하면 틱이 그 시간만큼 통째로 밀린다(16.67ms 예산에 100ms 를 얹는 셈).

그래서 공개 API 는 `hash_password` / `verify_password` 두 개의 **async** 함수이고,
내부에서 `asyncio.to_thread` 로 워커 스레드에 넘긴다. bcrypt 는 C 확장이라 해싱
동안 GIL 을 놓기 때문에 이 방식으로 루프가 실제로 자유로워진다.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib

import bcrypt

#: bcrypt 라운드 수. 12 는 흔한 기본값이지만 요청당 ~250ms 라 게임 서버에는 과하다.
#: 10 이면 ~60ms 이고, 워커 스레드로 빠지는 데다 로그인/설정에서만 도는 저빈도 경로다.
#: 레이트리밋(`app/services/ratelimit.py`)이 무차별 대입 쪽을 따로 막는다.
BCRYPT_ROUNDS = 10

#: 정책상의 최소 길이. 너무 빡빡하게 잡으면 사람들이 종이에 적기 시작한다.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def _prehash(password: str) -> bytes:
    """bcrypt 에 넣기 전에 sha256 으로 눌러 둔다.

    bcrypt 는 **입력의 72바이트까지만 본다.** 한글은 UTF-8 에서 글자당 3바이트라
    24글자만 넘어가도 뒤가 조용히 잘린다 — "비밀번호 뒷부분이 무시되는" 버그다.
    sha256 다이제스트를 base64 로 감싸(=널바이트 제거) 넘기면 길이와 무관해진다.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


async def hash_password(password: str) -> str:
    """비밀번호 -> bcrypt 해시 문자열. 워커 스레드에서 돈다."""
    return await asyncio.to_thread(_hash_sync, password)


async def verify_password(password: str, hashed: str | None) -> bool:
    """비밀번호 대조. 해시가 없는 계정(아이디 미설정)이면 항상 False."""
    if not hashed:
        return False
    return await asyncio.to_thread(_verify_sync, password, hashed)


def _hash_sync(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prehash(password), salt).decode("ascii")


def _verify_sync(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # 해시가 깨졌거나 형식이 다르면 "틀림"으로 처리한다. 예외를 위로 올리면
        # 그 자체가 "이 계정은 뭔가 다르다"는 신호가 된다.
        return False
