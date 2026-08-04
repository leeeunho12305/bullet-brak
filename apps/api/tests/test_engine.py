"""엔진/방/스냅샷 기본 동작 테스트."""

from __future__ import annotations

import pytest

from app.game import constants as C
from app.game import engine
from app.game.models import Player
from app.game.rooms import RoomManager
from app.game import serialize as serialize_mod
from app.game.serialize import room_state, snapshot
from app.services import chat as chat_service


@pytest.fixture
def manager() -> RoomManager:
    return RoomManager()


def _add_player(room, pid: str, x: float = 100.0) -> Player:
    p = Player(id=pid, nickname=pid, x=x, y=100.0)
    room.players[pid] = p
    room.scores.setdefault(pid, 0)
    room.round_wins.setdefault(pid, 0)
    return p


def _finish_round(room, winner: Player, loser: Player) -> None:
    """loser 를 즉사시키고 라운드 종료 타이머까지 소진한다."""
    loser.hp = 0.0
    engine.tick_room(room)
    assert room.phase == "round_over"
    for _ in range(C.ROUND_END_DELAY_TICKS):
        engine.tick_room(room)


# --------------------------------------------------------------------------
# 방
# --------------------------------------------------------------------------


def test_create_room_and_join(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    assert len(room.code) == 6 and room.code.isdigit()
    assert manager.get(room.code) is room
    assert room.phase == "waiting"

    _add_player(room, "a")
    assert not manager.is_full(room)
    _add_player(room, "b")
    assert manager.is_full(room)

    manager.remove(room.code)
    assert manager.get(room.code) is None


def test_create_room_codes_are_unique(manager: RoomManager) -> None:
    codes = {manager.create().code for _ in range(50)}
    assert len(codes) == 50


def test_training_room_starts_immediately(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    assert room.mode == "training" and room.phase == "playing"


# --------------------------------------------------------------------------
# 물리
# --------------------------------------------------------------------------


def test_gravity_pulls_player_down(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    p = _add_player(room, "a")
    p.y = 100.0
    engine.tick_room(room)
    assert p.vy == pytest.approx(C.GRAVITY)
    assert p.y == pytest.approx(100.0 + C.GRAVITY)


def test_player_stays_inside_horizontal_bounds(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    p = _add_player(room, "a")
    p.x = -50.0
    engine.tick_room(room)
    assert p.x == 0.0


def test_fall_death(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    p = _add_player(room, "a")
    p.y = C.HEIGHT + 200
    assert p.alive
    engine.tick_room(room)
    assert p.hp == 0.0
    assert not p.alive


# --------------------------------------------------------------------------
# 라운드 / 매치 판정
# --------------------------------------------------------------------------


def test_round_over_grants_round_win_and_coins(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    a, b = _add_player(room, "a"), _add_player(room, "b", 600.0)

    b.hp = 0.0
    engine.tick_room(room)

    assert room.phase == "round_over"
    assert room.round_wins["a"] == 1
    assert a.coins == 10
    assert room.round_end_timer == C.ROUND_END_DELAY_TICKS


def test_two_round_wins_make_one_score(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    a, b = _add_player(room, "a"), _add_player(room, "b", 600.0)

    _finish_round(room, a, b)
    assert room.phase == "playing"  # 1승만으로는 점수 없음 → 다음 라운드
    assert room.scores.get("a", 0) == 0

    _finish_round(room, a, b)
    assert room.scores["a"] == 1
    assert room.round_wins == {}
    assert room.phase == "picking"
    assert room.loser_to_pick == "b"
    assert len(room.available_cards) == C.CARD_CHOICES


def test_five_scores_finish_the_match(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    a, b = _add_player(room, "a"), _add_player(room, "b", 600.0)

    for score in range(1, C.SCORE_TO_WIN + 1):
        _finish_round(room, a, b)  # 1승
        _finish_round(room, a, b)  # 2승 → 점수
        assert room.scores["a"] == score
        if score < C.SCORE_TO_WIN:
            assert room.phase == "picking"
            engine.reset_round(room)  # 카드 선택 대신 즉시 다음 라운드

    assert room.phase == "finished"
    assert room.winner_id == "a"
    assert a.coins == 10 * 2 * C.SCORE_TO_WIN + 100


def test_pick_card_requires_picking_phase(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    _add_player(room, "a")
    assert engine.pick_card(room, "a", "stub_card_0") is False


def test_reset_match_clears_scores(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    a = _add_player(room, "a")
    room.scores["a"] = 3
    a.hp = 10.0
    engine.reset_match(room)
    assert room.scores == {}
    assert room.phase == "waiting"
    assert a.hp == C.MAX_HP


def test_training_first_wave_spawns_from_table(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    _add_player(room, "solo")
    engine.tick_room(room)
    assert room.training is not None
    assert room.training.wave == 1
    assert [b.tier for b in room.bots.values()] == list(C.TRAINING_WAVES[0])


def test_training_wave_clear_opens_card_pick(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    _add_player(room, "solo")
    engine.tick_room(room)
    for bot in room.bots.values():
        bot.hp = 0.0

    engine.tick_room(room)  # 죽은 봇 정리 + wave_clear 진입
    assert room.training is not None
    assert room.training.state == "wave_clear"
    assert room.training.kills == len(C.TRAINING_WAVES[0])

    for _ in range(C.TRAINING_WAVE_BREAK_TICKS):
        engine.tick_room(room)
    assert room.phase == "picking"
    assert room.loser_to_pick == "solo"


def test_training_card_pick_starts_next_wave(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    _add_player(room, "solo")
    engine.tick_room(room)
    for bot in room.bots.values():
        bot.hp = 0.0
    for _ in range(C.TRAINING_WAVE_BREAK_TICKS + 2):
        engine.tick_room(room)
    assert room.phase == "picking"

    assert engine.pick_card(room, "solo", room.available_cards[0]) is True
    assert room.phase == "playing"
    assert room.training is not None
    assert room.training.wave == 2
    assert [b.tier for b in room.bots.values()] == list(C.TRAINING_WAVES[1])


def test_training_death_respawns_and_keeps_wave(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    p = _add_player(room, "solo")
    engine.tick_room(room)
    p.cards.append("glass_cannon")  # 카드는 죽어도 유지돼야 한다
    p.hp = 0.0

    engine.tick_room(room)
    assert room.training is not None
    assert room.training.state == "respawning"
    assert room.training.deaths == 1
    assert room.phase == "playing"  # 훈련장은 매치가 끝나지 않는다

    for _ in range(C.TRAINING_RESPAWN_TICKS):
        engine.tick_room(room)
    assert p.alive and p.hp == p.max_hp
    assert p.cards == ["glass_cannon"]
    assert room.training.wave == 1
    assert room.training.state == "fighting"


def test_training_bots_do_not_shoot_each_other(manager: RoomManager) -> None:
    from app.game.bullets import spawn_bot_bullet, update_bullets

    room = manager.create("training", 1)
    _add_player(room, "solo", x=700.0)
    engine.tick_room(room)

    shooter, victim = list(room.bots.values())[:2]
    victim.x, victim.y = 300.0, 300.0
    shooter.x, shooter.y = 260.0, 300.0
    bullet = spawn_bot_bullet(room, shooter, 0.0)
    bullet.x, bullet.y = victim.cx, victim.cy
    room.bullets.append(bullet)
    before = victim.hp

    update_bullets(room)
    assert victim.hp == before


def test_training_stats_track_accuracy(manager: RoomManager) -> None:
    from app.game.bullets import fire

    room = manager.create("training", 1)
    p = _add_player(room, "solo")
    engine.tick_room(room)
    p.aim.x, p.aim.y = p.cx + 100.0, p.cy

    fire(room, p)
    assert room.training is not None
    assert room.training.shots == 1
    assert room.training.hits == 0


# --------------------------------------------------------------------------
# 직렬화
# --------------------------------------------------------------------------

SNAPSHOT_KEYS = {
    "type",
    "tick",
    "phase",
    "mode",
    "players",
    "bots",
    "bullets",
    "zones",
    "platforms",
    "loser_to_pick",
    "available_cards",
    "winner_id",
    "training",
}

PLAYER_KEYS = {
    "id",
    "nickname",
    "customization",
    "x",
    "y",
    "width",
    "height",
    "vx",
    "vy",
    "hp",
    "max_hp",
    "alive",
    "aim",
    "cooldown",
    "max_cooldown",
    "block_meter",
    "block_meter_max",
    "blocking",
    "charging",
    "charge",
    "score",
    "round_wins",
    "coins",
    "cards",
    "silenced",
    "poison",
    "cold",
}

# 0.5초에 한 번만 실리는 필드 (serialize.LOADOUT_INTERVAL)
LOADOUT_KEYS = {"stats", "damage_table"}


def test_snapshot_shape(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    _add_player(room, "a")
    room.scores["a"] = 2
    room.round_wins["a"] = 1
    engine.tick_room(room)

    snap = snapshot(room)
    assert set(snap) == SNAPSHOT_KEYS
    assert snap["type"] == "state"
    assert snap["tick"] == room.tick
    assert len(snap["platforms"]) == len(C.PLATFORMS)

    player = snap["players"][0]
    assert set(player) == PLAYER_KEYS  # 대전 중 대부분의 틱에는 loadout 이 빠진다
    assert player["score"] == 2 and player["round_wins"] == 1
    assert set(player["customization"]) == {"eye", "mouth", "detail", "color"}
    assert "flags" not in player and "inputs" not in player


def test_snapshot_loadout_is_periodic(manager: RoomManager) -> None:
    """stats/damage_table 은 0.5초에 한 번만 실려야 한다(대역폭)."""
    room = manager.create("pvp", 2)
    room.phase = "playing"
    _add_player(room, "a")

    room.tick = serialize_mod.LOADOUT_INTERVAL
    loaded = snapshot(room)["players"][0]
    assert set(loaded) == PLAYER_KEYS | LOADOUT_KEYS
    table = loaded["damage_table"]
    assert [row["distance"] for row in table] == list(C.DAMAGE_TABLE_DISTANCES)
    assert table[0]["damage"] > table[-1]["damage"]  # 가까울수록 강하다

    room.tick = serialize_mod.LOADOUT_INTERVAL + 1
    assert set(snapshot(room)["players"][0]) == PLAYER_KEYS

    # 대기/카드선택 중에는 트래픽이 한가하므로 매 틱 싣는다.
    room.phase = "picking"
    assert set(snapshot(room)["players"][0]) == PLAYER_KEYS | LOADOUT_KEYS


def test_snapshot_available_cards_are_card_infos(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    _add_player(room, "a")
    _add_player(room, "b", 600.0)
    room.phase = "picking"
    room.available_cards = engine._pick_card_ids(C.CARD_CHOICES)
    snap = snapshot(room)
    assert len(snap["available_cards"]) == C.CARD_CHOICES
    for info in snap["available_cards"]:
        assert set(info) == {"id", "name", "desc", "category", "color", "emoji"}


def test_room_state_shape(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    _add_player(room, "a")
    state = room_state(room)
    assert set(state) == {"code", "mode", "max_players", "phase", "players"}
    assert set(state["players"][0]) == {"id", "nickname", "customization", "coins"}


# --------------------------------------------------------------------------
# 채팅 필터
# --------------------------------------------------------------------------


def test_chat_filter_masks_bad_words(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    payload = chat_service.push(room, "닉", "야 이 바보야")
    assert payload is not None
    assert "바보" not in payload["message"]["text"]
    assert "***" in payload["message"]["text"]
    assert len(room.messages) == 1


def test_chat_empty_is_dropped(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    assert chat_service.push(room, "닉", "   ") is None
