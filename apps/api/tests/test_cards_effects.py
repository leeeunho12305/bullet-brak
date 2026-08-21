"""효과가 비어 있던 카드 6장 + 카드 선택 중복 방지 + 회복 장판 아군 전용.

여기 있는 카드들은 예전에 flags 만 세우고 아무 데서도 읽지 않아서
뽑아도 아무 일이 없었다(EMPOWER/OVERPOWER/STEADY SHOT/DAZZLE/
TASTE OF BLOOD, 그리고 체력만 깎고 이득이 없던 DEMONIC PACT).
"""

from __future__ import annotations

import pytest

from app.game import bullets, cards, constants as C, engine, sim
from app.game.models import Player
from app.game.rooms import RoomManager
from app.game.stats import bullet_falloff


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _playing_room(manager: RoomManager):
    room = manager.create("pvp", 2, map_id="classic")
    room.phase = "playing"
    return room


def _add_player(room, pid: str = "a", x: float = 100.0, y: float = 300.0) -> Player:
    p = Player(id=pid, nickname=pid, x=x, y=y)
    p.aim.x, p.aim.y = x + 200.0, y
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _shoot(room, p: Player) -> float:
    """한 발 쏘고 그 탄의 위력을 돌려준다."""
    room.bullets.clear()
    p.cooldown = 0.0
    bullets.fire(room, p)
    return room.bullets[0].damage


# --------------------------------------------------------------------------
# EMPOWER — 가드로 충전, 다음 한 발에 소비
# --------------------------------------------------------------------------


def test_empower_boosts_only_the_shot_after_a_guard(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    plain = _shoot(room, p)

    cards.apply_card(p, "empower")
    assert _shoot(room, p) == pytest.approx(plain), "가드하기 전에는 그냥 평타다"

    p.inputs.block = True
    sim.update_player(room, p)
    p.inputs.block = False
    assert p.empower_ready

    assert _shoot(room, p) == pytest.approx(plain * C.EMPOWER_MULT)
    assert not p.empower_ready
    assert _shoot(room, p) == pytest.approx(plain), "그다음 발은 다시 평타"


# --------------------------------------------------------------------------
# OVERPOWER — 상대가 약할수록 강해짐
# --------------------------------------------------------------------------


def test_overpower_scales_with_the_weakest_enemy(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    enemy = _add_player(room, "b", x=600.0)
    cards.apply_card(p, "overpower")

    full = _shoot(room, p)
    enemy.hp = enemy.max_hp * 0.5
    half = _shoot(room, p)
    enemy.hp = 1.0
    dying = _shoot(room, p)

    assert half > full
    assert dying > half
    assert dying == pytest.approx(full * (1 + C.OVERPOWER_MAX_BONUS), rel=0.02)


# --------------------------------------------------------------------------
# DEMONIC PACT — 내 체력을 태울수록 강해짐
# --------------------------------------------------------------------------


def test_demonic_pact_burns_hp_and_pays_it_back_in_damage(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "demonic_pact")

    full = _shoot(room, p)
    assert p.hp < p.max_hp, "쏘면 체력을 태운다"

    p.hp = p.max_hp * 0.25
    assert _shoot(room, p) > full, "체력이 낮을수록 위력이 올라야 카드값을 한다"


# --------------------------------------------------------------------------
# STEADY SHOT — 거리에 따른 위력 변동이 줄어듦
# --------------------------------------------------------------------------


def test_steady_shot_flattens_the_damage_falloff(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "steady_shot")
    bullet = bullets.spawn_bullet(room, p, 0.0)

    bullet.x = bullet.start_x  # 코앞
    close = bullet_falloff(bullet)
    bullet.x = bullet.start_x + C.DAMAGE_FALLOFF_RANGE  # 멀리
    far = bullet_falloff(bullet)

    assert close < C.DAMAGE_CLOSE_MULT, "가까이서는 덜 세지고"
    assert far > C.DAMAGE_FAR_MULT, "멀리서는 덜 약해진다"
    assert bullet.life > C.BASE_BULLET_LIFE, "더 오래 날아간다"


# --------------------------------------------------------------------------
# DAZZLE — 적중 시 짧게 기절
# --------------------------------------------------------------------------


def test_dazzle_stuns_the_target_on_hit(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    target = _add_player(room, "b", x=600.0)
    cards.apply_card(p, "dazzle")

    bullet = bullets.spawn_bullet(room, p, 0.0)
    # 한 틱 이동한 뒤 정확히 몸통 한복판에 닿도록 둔다.
    bullet.x, bullet.y = target.cx - bullet.vx, target.cy
    room.bullets.append(bullet)
    bullets.update_bullets(room)

    assert target.dazzle_timer >= C.DAZZLE_HIT_TICKS - 1

    # 기절 중에는 움직이지도 가드하지도 못한다.
    target.inputs.left = True
    target.inputs.block = True
    target.vx = 0.0
    sim.update_player(room, target)
    assert target.vx == 0.0
    assert not target.blocking


# --------------------------------------------------------------------------
# TASTE OF BLOOD — 피해를 주면 잠깐 빨라짐
# --------------------------------------------------------------------------


def test_taste_of_blood_speeds_you_up_after_a_hit(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    target = _add_player(room, "b", x=600.0)
    cards.apply_card(p, "taste_of_blood")

    bullet = bullets.spawn_bullet(room, p, 0.0)
    # 한 틱 이동한 뒤 정확히 몸통 한복판에 닿도록 둔다.
    bullet.x, bullet.y = target.cx - bullet.vx, target.cy
    room.bullets.append(bullet)
    bullets.update_bullets(room)
    assert p.blood_timer > 0

    p.inputs.right = True
    for _ in range(40):
        sim.update_player(room, p)
    boosted = p.vx

    p.blood_timer = 0
    for _ in range(40):
        sim.update_player(room, p)

    assert boosted > p.vx, "피 맛을 본 동안 더 빨라야 한다"
    assert boosted == pytest.approx(p.speed * C.BLOOD_SPEED_MULT, rel=0.05)


# --------------------------------------------------------------------------
# 카드 선택 중복
# --------------------------------------------------------------------------


def test_picker_never_offers_a_card_you_already_own(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    for cid in ("poison", "tank", "homing", "leech", "bouncy", "huge"):
        cards.apply_card(p, cid)

    for _ in range(50):
        offered = engine._pick_card_ids(C.CARD_CHOICES, p)
        assert len(offered) == C.CARD_CHOICES
        assert len(set(offered)) == C.CARD_CHOICES, "선택지끼리도 겹치면 안 된다"
        assert not set(offered) & set(p.cards)


def test_picker_still_fills_five_slots_when_almost_everything_is_owned(
    manager: RoomManager,
) -> None:
    """다 모았을 때 선택창이 비어 라운드가 멈추면 안 된다."""
    room = _playing_room(manager)
    p = _add_player(room)
    p.cards.extend(c.id for c in cards.CARDS[:-2])

    offered = engine._pick_card_ids(C.CARD_CHOICES, p)

    assert len(offered) == C.CARD_CHOICES
    assert len(set(offered)) == C.CARD_CHOICES


# --------------------------------------------------------------------------
# 회복 장판은 아군 전용
# --------------------------------------------------------------------------


def test_heal_zones_do_not_heal_the_enemy(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    enemy = _add_player(room, "b", x=p.x)  # 같은 자리에 겹쳐 세운다
    enemy.y = p.y
    cards.apply_card(p, "healing_field")
    p.hp = enemy.hp = 50.0
    p.inputs.block = True

    for _ in range(sim.GUARD_PERIOD * 4):
        sim.update_player(room, p)
        sim.update_zones(room)
        room.tick += 1

    assert p.hp > 50.0, "내 회복 장판은 나를 회복시킨다"
    assert enemy.hp == 50.0, "적은 내 회복 장판을 못 쓴다"


def test_radiance_zone_is_also_owner_only(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    enemy = _add_player(room, "b", x=p.x)
    enemy.y = p.y
    cards.apply_card(p, "radiance")
    p.hp = enemy.hp = 50.0
    p.inputs.block = True

    for _ in range(sim.GUARD_PERIOD * 4):
        sim.update_player(room, p)
        sim.update_zones(room)
        room.tick += 1

    assert p.hp > 50.0
    assert enemy.hp == 50.0


# --------------------------------------------------------------------------
# REMOTE — 쏜 뒤에도 마우스 커서를 실시간으로 따라간다
# --------------------------------------------------------------------------


def test_remote_bullet_follows_the_live_cursor(manager: RoomManager) -> None:
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "remote")

    bullets.fire(room, p)  # 오른쪽으로 발사
    bullet = room.bullets[0]
    launched = bullet.vy

    p.aim.x, p.aim.y = p.cx + 200.0, p.cy + 400.0  # 쏜 뒤에 커서를 아래로 내린다
    for _ in range(20):
        bullets.update_bullets(room)

    assert bullet.vy > launched, "커서를 내리면 탄도 따라 내려와야 한다"
    assert bullet.vy > 0


def test_remote_bullet_holds_its_last_aim_when_the_owner_dies(manager: RoomManager) -> None:
    """주인이 죽는 순간 방향이 튀지 않고 마지막 커서 위치를 향해 계속 간다."""
    room = _playing_room(manager)
    p = _add_player(room)
    cards.apply_card(p, "remote")

    bullets.fire(room, p)
    bullet = room.bullets[0]
    p.aim.x, p.aim.y = p.cx + 200.0, p.cy + 400.0
    for _ in range(10):
        bullets.update_bullets(room)
    falling = bullet.vy

    p.hp = 0.0
    p.aim.x, p.aim.y = p.cx, p.cy - 400.0  # 죽은 뒤의 커서는 무시돼야 한다
    for _ in range(10):
        bullets.update_bullets(room)

    assert bullet.vy >= falling, "주인이 죽었으면 마지막 조준을 계속 따라간다"


def test_remote_alone_does_not_home_in_on_enemies(manager: RoomManager) -> None:
    """REMOTE 는 손으로 모는 카드다. 자동 유도까지 붙으면 조종이 안 된다."""
    room = _playing_room(manager)
    p = _add_player(room)
    enemy = _add_player(room, "b", x=400.0)
    enemy.y = p.y + 300.0  # 아래쪽에 적을 둔다
    cards.apply_card(p, "remote")

    bullets.fire(room, p)
    bullet = room.bullets[0]
    p.aim.x, p.aim.y = p.cx + 400.0, p.cy  # 커서는 계속 정면
    for _ in range(15):
        bullets.update_bullets(room)

    assert bullet.vy == pytest.approx(0.0, abs=0.2), "적 쪽으로 저절로 꺾이면 안 된다"


def test_chase_turns_harder_than_homing_and_radar(manager: RoomManager) -> None:
    """세 유도 카드가 실제로 다른 세기를 갖는다(예전엔 셋 다 똑같았다)."""
    turns = {}
    for card in ("radar_shot", "homing", "chase"):
        room = _playing_room(manager)
        p = _add_player(room)
        enemy = _add_player(room, "b", x=400.0)
        enemy.y = p.y + 300.0
        cards.apply_card(p, card)
        bullets.fire(room, p)
        bullet = room.bullets[0]
        for _ in range(10):
            bullets.update_bullets(room)
        turns[card] = bullet.vy

    assert turns["radar_shot"] < turns["homing"] < turns["chase"]


# --------------------------------------------------------------------------
# 도탄 — 튕길 때마다 수명이 늘어난다
# --------------------------------------------------------------------------


def _fly_until_gone(room) -> int:
    ticks = 0
    while room.bullets and ticks < 2000:
        bullets.update_bullets(room)
        ticks += 1
    return ticks


def _straight_shot(manager: RoomManager, card: str | None):
    """천장 근처에서 옆으로 쏴서 벽만 왕복하게 한다."""
    room = _playing_room(manager)
    p = _add_player(room, y=60.0)
    p.aim.x, p.aim.y = p.cx + 600.0, p.cy
    if card:
        cards.apply_card(p, card)
    bullets.fire(room, p)
    return room, room.bullets[0]


def test_a_bounce_extends_the_bullet_life(manager: RoomManager) -> None:
    room, bullet = _straight_shot(manager, "bouncy")
    before = bullet.life

    for _ in range(400):
        bullets.update_bullets(room)
        if bullet.bounces:
            break
    assert bullet.bounces, "벽까지 못 갔다면 이 테스트가 성립하지 않는다"

    assert bullet.life > before - 60, "튕기면 수명이 되돌아와야 한다"


def test_bouncing_bullets_live_longer_than_plain_ones(manager: RoomManager) -> None:
    plain_room, _ = _straight_shot(manager, None)
    bouncy_room, _ = _straight_shot(manager, "bouncy")

    assert _fly_until_gone(bouncy_room) > _fly_until_gone(plain_room)


def test_mayhem_gets_to_use_every_bounce_it_paid_for(manager: RoomManager) -> None:
    """수명이 안 늘면 도탄 5회를 먹어도 2회쯤 쓰고 꺼진다."""
    room, bullet = _straight_shot(manager, "mayhem")
    _fly_until_gone(room)

    assert min(bullet.bounces, bullet.max_bounces) == bullet.max_bounces


# --------------------------------------------------------------------------
# 가드 반사 — 도탄 횟수를 먹지 않는다
# --------------------------------------------------------------------------


def test_a_reflected_bullet_survives_without_bounce_cards(manager: RoomManager) -> None:
    """반사가 도탄 1회를 먹으면 max_bounces=0 인 평범한 탄은 즉시 꺼진다."""
    room = _playing_room(manager)
    shooter = _add_player(room)
    guard = _add_player(room, "b", x=300.0)
    guard.aim.x, guard.aim.y = 0.0, guard.cy
    guard.inputs.block = True
    guard.blocking = True
    shooter.aim.x, shooter.aim.y = guard.cx, guard.cy  # 몸통 한복판을 겨눈다

    bullets.fire(room, shooter)
    bullet = room.bullets[0]
    for _ in range(400):
        bullets.update_bullets(room)
        if bullet.owner != shooter.id:
            break
    assert bullet.owner == guard.id, "가드가 되받아치는 상황이어야 한다"

    assert bullet.active, "되받아친 탄이 그 자리에서 꺼지면 가드 반사가 의미가 없다"
    assert bullet.bounces == 0, "반사는 도탄이 아니다"

    for _ in range(20):
        bullets.update_bullets(room)
    assert shooter.hp < shooter.max_hp, "반사한 탄이 쏜 사람에게 되돌아가야 한다"
