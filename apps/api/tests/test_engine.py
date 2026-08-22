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


def test_rematch_needs_both_players(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "finished"
    a = _add_player(room, "a")
    _add_player(room, "b", 600.0)
    room.scores["a"] = C.SCORE_TO_WIN
    room.winner_id = "a"
    a.cards.append("glass_cannon")

    assert engine.vote_rematch(room, "a", True) == "pending"
    assert room.phase == "finished"  # 상대를 기다린다
    assert snapshot(room)["rematch"] == ["a"]

    assert engine.vote_rematch(room, "b", True) == "start"
    assert room.phase == "playing"  # 대기실을 거치지 않는다
    assert room.scores == {}
    assert room.winner_id is None
    assert a.cards == []
    assert room.rematch_votes == set()


def test_rematch_decline_returns_to_lobby(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "finished"
    _add_player(room, "a")
    _add_player(room, "b", 600.0)
    room.scores["a"] = C.SCORE_TO_WIN

    assert engine.vote_rematch(room, "a", True) == "pending"
    assert engine.vote_rematch(room, "b", False) == "declined"
    assert room.phase == "waiting"
    assert room.rematch_votes == set()


def test_rematch_ignored_outside_finished(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    room.phase = "playing"
    _add_player(room, "a")
    assert engine.vote_rematch(room, "a", True) == "ignored"
    assert room.phase == "playing"

    room.phase = "finished"
    assert engine.vote_rematch(room, "nobody", True) == "ignored"  # 방에 없는 id
    assert room.rematch_votes == set()


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


def test_training_card_pick_offers_every_card(manager: RoomManager) -> None:
    """훈련장은 시험해 보는 곳이다 — 무작위 5장이 아니라 전부 열어 준다."""
    from app.game.cards import CARDS

    room = manager.create("training", 1)
    _add_player(room, "solo")
    engine.tick_room(room)
    for bot in room.bots.values():
        bot.hp = 0.0
    for _ in range(C.TRAINING_WAVE_BREAK_TICKS + 2):
        engine.tick_room(room)

    assert room.phase == "picking"
    assert len(room.available_cards) == len(CARDS)


def test_training_player_can_open_cards_mid_wave(manager: RoomManager) -> None:
    """웨이브를 깨지 않아도 카드를 가져올 수 있고, 그렇다고 웨이브가 넘어가지는 않는다."""
    room = manager.create("training", 1)
    _add_player(room, "solo")
    engine.tick_room(room)
    assert room.training is not None and room.training.wave == 1
    bots_before = len(room.bots)

    assert engine.open_training_cards(room) is True
    assert room.phase == "picking"
    assert room.loser_to_pick == "solo"

    assert engine.pick_card(room, "solo", "glass_cannon") is True
    assert room.phase == "playing"
    assert room.players["solo"].cards == ["glass_cannon"]
    assert room.training.wave == 1, "카드를 골랐다고 웨이브가 넘어가면 시험을 못 한다"
    assert len(room.bots) == bots_before, "싸우던 봇이 사라졌다"


def test_pvp_room_cannot_open_cards_on_demand(manager: RoomManager) -> None:
    """대전에서는 진 쪽만, 라운드가 끝났을 때만 카드를 받는다."""
    room = manager.create("pvp", 2)
    _add_player(room, "a")
    _add_player(room, "b")
    engine.start_game(room)

    assert engine.open_training_cards(room) is False
    assert room.phase == "playing"


def test_training_dead_player_cannot_open_cards(manager: RoomManager) -> None:
    room = manager.create("training", 1)
    p = _add_player(room, "solo")
    engine.tick_room(room)
    p.hp = 0.0
    engine.tick_room(room)  # respawning 진입

    assert engine.open_training_cards(room) is False


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
    "map_id",
    "players",
    "bots",
    "bullets",
    "zones",
    "loser_to_pick",
    "available_cards",
    "winner_id",
    "rematch",
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
    "stunned",
    "windup",
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
    # platforms/movers 는 조건부다(아래 test_snapshot_layout_is_periodic).
    assert set(snap) - {"platforms", "movers"} == SNAPSHOT_KEYS
    assert snap["type"] == "state"
    assert snap["tick"] == room.tick

    player = snap["players"][0]
    assert set(player) == PLAYER_KEYS  # 대전 중 대부분의 틱에는 loadout 이 빠진다
    assert player["score"] == 2 and player["round_wins"] == 1
    assert set(player["customization"]) == {"eye", "mouth", "detail", "detail2", "color", "offsets"}
    assert "flags" not in player and "inputs" not in player


def test_snapshot_layout_is_periodic(manager: RoomManager) -> None:
    """발판 전체 목록은 0.5초에 한 번만. 그 사이에는 이동발판 좌표만 실린다(대역폭)."""
    room = manager.create("pvp", 2, map_id="factory")
    room.phase = "playing"
    _add_player(room, "a")

    room.tick = serialize_mod.LAYOUT_INTERVAL
    full = snapshot(room)
    assert len(full["platforms"]) == len(room.platforms)

    room.tick = serialize_mod.LAYOUT_INTERVAL + 1
    between = snapshot(room)
    assert "platforms" not in between
    # 움직이는 발판만 인덱스와 함께 실린다.
    moving = [i for i, p in enumerate(room.platforms) if p.get("type") == "mover"]
    assert [m["i"] for m in between["movers"]] == moving

    # 대기실처럼 한가한 상태에서는 매 틱 전부 보낸다(첫 화면이 늦게 뜨면 안 된다).
    room.phase = "waiting"
    assert "platforms" in snapshot(room)


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


def test_customization_offsets_are_clamped(manager: RoomManager) -> None:
    """편집기가 보낸 파츠 위치는 슬롯/범위를 검사해서 통과시킨다."""
    room = manager.create("pvp", 2)
    p = _add_player(room, "a")
    p.customization = {
        "eye": 12,
        "mouth": 3,
        "detail": 1,
        "detail2": 5,
        "color": "#4dabf7",
        "offsets": {
            "eye": {"x": 0.1, "y": -0.05},
            "mouth": {"x": 9.0, "y": "nope"},  # 범위 밖 / 숫자 아님
            "detail": {"x": 0.0, "y": 0.0},  # 0 은 실어 보내지 않는다
            "wing": {"x": 0.2, "y": 0.2},  # 모르는 슬롯
        },
    }

    custom = room_state(room)["players"][0]["customization"]
    assert custom["detail2"] == 5
    assert custom["offsets"]["eye"] == {"x": 0.1, "y": -0.05}
    assert custom["offsets"]["mouth"] == {"x": C.MAX_PART_OFFSET, "y": 0.0}
    assert "detail" not in custom["offsets"]
    assert "wing" not in custom["offsets"]


def test_customization_message_rejects_bad_values() -> None:
    """클라가 보낸 avatar 메시지도 같은 규칙으로 정리된다."""
    from app.schemas.messages import Customization

    c = Customization.model_validate(
        {
            "eye": -3,
            "detail2": 9999,
            "color": "javascript:alert(1)",
            "offsets": {"eye": {"x": float("nan"), "y": 0.5}, "hat": {"x": 0.1, "y": 0.1}},
            "extra": "무시",
        }
    )
    assert c.eye == 0
    assert c.detail2 == C.MAX_PART_INDEX
    assert c.color == "#ff6b6b"
    assert c.offsets["eye"].x == 0.0
    assert c.offsets["eye"].y == C.MAX_PART_OFFSET
    assert "hat" not in c.offsets


def test_room_state_shape(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    _add_player(room, "a")
    state = room_state(room)
    assert set(state) == {
        "code",
        "mode",
        "ranked",
        "max_players",
        "phase",
        "map_id",
        "map",
        "custom_map",
        "players",
    }
    assert set(state["players"][0]) == {"id", "nickname", "customization", "coins"}


# --------------------------------------------------------------------------
# 채팅
# --------------------------------------------------------------------------


def test_chat_text_is_not_filtered(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    payload = chat_service.push(room, "닉", "야 이 바보야")
    assert payload is not None
    assert payload["message"]["text"] == "야 이 바보야"
    assert len(room.messages) == 1


def test_chat_empty_is_dropped(manager: RoomManager) -> None:
    room = manager.create("pvp", 2)
    assert chat_service.push(room, "닉", "   ") is None
