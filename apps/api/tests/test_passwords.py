"""비밀번호 해싱이 **게임 루프를 막지 않는지** 확인한다.

이 서버의 이벤트 루프는 60Hz 틱 루프(`app/main.py`)와 같은 루프다. bcrypt 는
일부러 느린 함수라서 이벤트 루프에서 동기로 부르면 그 시간만큼 틱이 통째로 밀린다.
`app/services/passwords.py` 가 `asyncio.to_thread` 로 빼는 이유가 그것이고,
이 파일은 누군가 그 우회를 "간단하게" 걷어냈을 때 울리라고 있는 테스트다.
"""

from __future__ import annotations

import asyncio

from app.services import passwords

#: 루프가 살아 있다고 인정할 최소 양보 횟수. 동기로 해싱하면 이 값은 0~1 에 머문다.
#: (`sleep(0)` 으로 세는 이유: Windows 의 기본 타이머 해상도가 ~15ms 라, 시간 기반으로
#:  세면 "루프는 멀쩡한데 횟수가 적은" 상황과 진짜로 막힌 상황이 구별되지 않는다.)
MIN_YIELDS = 50


async def _count_yields(stop: asyncio.Event) -> int:
    """stop 이 설정될 때까지 이벤트 루프에 몇 번이나 제어가 돌아왔는지 센다."""
    yields = 0
    while not stop.is_set():
        await asyncio.sleep(0)
        yields += 1
    return yields


async def test_hashing_does_not_stall_the_event_loop() -> None:
    stop = asyncio.Event()
    ticker = asyncio.create_task(_count_yields(stop))

    # 해싱 자체는 수십 ms 가 걸린다. 그동안 루프가 멈춰 있으면 안 된다.
    await passwords.hash_password("f7#kQ2mz")
    stop.set()
    yields = await ticker

    assert yields >= MIN_YIELDS, f"해싱 중 이벤트 루프가 {yields}번밖에 못 돌았다 — 틱이 막힌다"


async def test_verify_also_runs_off_the_loop() -> None:
    hashed = await passwords.hash_password("f7#kQ2mz")

    stop = asyncio.Event()
    ticker = asyncio.create_task(_count_yields(stop))
    assert await passwords.verify_password("f7#kQ2mz", hashed) is True
    stop.set()
    assert await ticker >= MIN_YIELDS


async def test_wrong_password_and_broken_hash_are_both_just_false() -> None:
    hashed = await passwords.hash_password("f7#kQ2mz")
    assert await passwords.verify_password("f7#kQ2mZ", hashed) is False
    assert await passwords.verify_password("f7#kQ2mz", None) is False
    # 해시가 깨져 있어도 예외를 올리지 않는다 — 올리면 그 자체가 "이 계정은 다르다"는 신호다.
    assert await passwords.verify_password("f7#kQ2mz", "이건-해시가-아니다") is False


async def test_hash_is_salted() -> None:
    """같은 비밀번호라도 해시가 달라야 한다(레인보우 테이블 방어)."""
    first = await passwords.hash_password("f7#kQ2mz")
    second = await passwords.hash_password("f7#kQ2mz")
    assert first != second
    assert await passwords.verify_password("f7#kQ2mz", first) is True
    assert await passwords.verify_password("f7#kQ2mz", second) is True
