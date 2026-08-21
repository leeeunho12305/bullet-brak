"""카드 목록 자체에 거는 규칙.

효과 검증은 test_damage / test_guard / test_knockback 이 한다. 여기서는 "카드 설명이
플레이어가 읽을 수 있는 글인가"와 "없앤 카드가 정말 없어졌는가"만 본다.
"""

from __future__ import annotations

from app.game import cards, sim
from app.game.models import Player, Room


def test_no_card_description_talks_about_ticks() -> None:
    """"틱"은 내부 단위다. 60틱 = 1초라는 걸 플레이어는 알 방법이 없다."""
    offenders = [c.id for c in cards.CARDS if "틱" in c.desc]
    assert offenders == [], f"설명에 '틱'이 남아 있다: {offenders}"


def test_no_card_description_uses_raw_multiplier_notation() -> None:
    """"×1.6" 같은 표기 대신 "60% 늘어난다"로 적는다 — 곱셈 기호는 표에서나 쓴다."""
    offenders = [c.id for c in cards.CARDS if "×" in c.desc]
    assert offenders == [], f"설명에 배율 기호가 남아 있다: {offenders}"


def test_every_card_has_a_description() -> None:
    for card in cards.CARDS:
        assert card.desc.strip(), f"{card.id} 에 설명이 없다"
        assert card.category in ("attack", "survival", "utility", "movement", "special")


def test_card_ids_are_unique() -> None:
    ids = [c.id for c in cards.CARDS]
    assert len(ids) == len(set(ids))
    assert cards.all_card_ids() == ids


def test_teleport_card_is_gone() -> None:
    """가드하는 순간 조준 방향으로 순간이동하던 카드. 제거 요청으로 뺐다."""
    assert "teleport" not in cards.CARD_BY_ID
    assert cards.apply_card(Player(id="a"), "teleport") is False


def test_guarding_never_teleports_the_player() -> None:
    """flags 에 남은 찌꺼기(예전 세이브)로도 순간이동이 되살아나면 안 된다."""
    room = Room(code="444444")
    room.phase = "playing"
    p = Player(id="a", x=100.0, y=300.0)
    room.players["a"] = p
    p.flags["teleport"] = True
    p.aim.x, p.aim.y = 700.0, 300.0
    p.inputs.block = True

    sim.update_player(room, p)

    assert p.x < 110.0, "가드했더니 조준 방향으로 순간이동했다"
