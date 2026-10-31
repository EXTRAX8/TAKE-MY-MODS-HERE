# ba_meta require api 9
# ===========================================================================
# EXTRAX8 MINIGAMES - ALL IN ONE (API 9)
# 29 ميني جيم + 3 خرائط، كلها تدعم FFA و Teams
# ===========================================================================
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import bascenev1 as bs
import bascenev1lib.actor.spazbot as _spz
from bascenev1lib.actor.bomb import Blast, Bomb
from bascenev1lib.actor.flag import Flag
from bascenev1lib.actor.powerupbox import PowerupBox
from bascenev1lib.actor.scoreboard import Scoreboard
from bascenev1lib.actor.spazbot import (
    SpazBotSet,
    SpazBotDiedMessage,
    BrawlerBotLite,
    BrawlerBot,
    BrawlerBotPro,
    ChargerBot,
    TriggerBot,
    TriggerBotPro,
    BomberBot,
)
from bascenev1lib.gameutils import SharedObjects

try:
    from bascenev1lib.maps import FootballStadium as _FootballBase
    from bascenev1lib.maps import HockeyStadium as _HockeyBase
    _MAPS_OK = True
except Exception:  # noqa: BLE001
    _FootballBase = bs.Map
    _HockeyBase = bs.Map
    _MAPS_OK = False

if TYPE_CHECKING:
    from typing import Any, Sequence


# ---------------------------------------------------------------------------
# كلاسات مشتركة (لاعب وفريق موحّدان لكل الألعاب)
# ---------------------------------------------------------------------------
class Player(bs.Player['Team']):
    def __init__(self) -> None:
        self.lives = 1
        self.eliminated = False
        self.kills = 0
        self.coins = 0
        self.light: bs.Node | None = None
        # Tag games
        self.fuse_end: float | None = None
        self.immune_until = 0.0
        self.last_count = -1
        # Smash
        self.percent = 0.0
        self.pct_text: bs.Node | None = None
        # Flappy
        self.bird_alive = True
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.pipes_passed = 0
        self.last_pipe_id = -1
        self.bird_node: bs.Node | None = None
        self.bird_label: bs.Node | None = None
        # Misc games
        self.infected = False
        self.gg_level = 0
        self.seeker = False
        self.claimed = False
        self.max_speed = 0.0
        self.jumped = False
        self.snake_tail: list[tuple[float, float, float]] = []
        self.snake_lights: list[bs.Node] = []
        self.snake_len = 3
        self.cp_flag: Flag | None = None
        self.cp_count = 0
        self.next_sleep = 0.0


class Team(bs.Team[Player]):
    def __init__(self) -> None:
        self.survival_seconds: int | None = None
        self.score = 0
        self.queen_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.queen_hp = 100.0
        self.queen_dead = False
        self.queen_nodes: list[Any] = []
        self.queen_text: bs.Node | None = None
        self.goal_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.goal_nodes: list[Any] = []


def _melee_maps() -> list[str]:
    assert bs.app.classic is not None
    return bs.app.classic.getmaps('melee')


def _supports(sessiontype: type[bs.Session]) -> bool:
    return issubclass(sessiontype, bs.DualTeamSession) or issubclass(
        sessiontype, bs.FreeForAllSession
    )


def _time_setting(default: int = 0) -> bs.Setting:
    return bs.IntChoiceSetting(
        'Time Limit',
        choices=[
            ('None', 0),
            ('1 Minute', 60),
            ('2 Minutes', 120),
            ('5 Minutes', 300),
            ('10 Minutes', 600),
        ],
        default=default,
    )


def _pos(player: Player) -> Sequence[float] | None:
    actor = player.actor
    node = getattr(actor, 'node', None)
    if actor is None or not node:
        return None
    return node.position


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _hdist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2)


def _ground_points(activity: Any) -> list[tuple[float, float, float]]:
    """نقاط أرضية مضمونة (نقاط ظهور الخريطة)."""
    pts: list[tuple[float, float, float]] = []
    try:
        for p in activity.map.ffa_spawn_points:
            pts.append((float(p[0]), float(p[1]), float(p[2])))
    except Exception:  # noqa: BLE001
        pts = []
    if not pts:
        base = activity.map.get_ffa_start_position(activity.players)
        pts = [(float(base[0]), float(base[1]), float(base[2]))]
    return pts


def _far_points(
    pts: list[tuple[float, float, float]], n: int
) -> list[tuple[float, float, float]]:
    chosen = [pts[0]]
    while len(chosen) < n:
        best = max(pts, key=lambda p: min(_hdist(p, c) for c in chosen))
        if min(_hdist(best, c) for c in chosen) < 0.5:
            base = random.choice(pts)
            best = (
                base[0] + random.uniform(-3.0, 3.0),
                base[1],
                base[2] + random.uniform(-3.0, 3.0),
            )
        chosen.append(best)
    return chosen[:n]


def _rand_point(
    activity: Any,
    avoid: list[Sequence[float]] | None = None,
    min_dist: float = 0.0,
) -> tuple[float, float, float]:
    pts = _ground_points(activity)
    p = pts[0]
    for _ in range(12):
        b = random.choice(pts)
        p = (
            b[0] + random.uniform(-1.5, 1.5),
            b[1] + 0.3,
            b[2] + random.uniform(-1.5, 1.5),
        )
        if not avoid or all(_hdist(p, a) >= min_dist for a in avoid):
            break
    return p


def _blast_kill(player: Player) -> None:
    pos = _pos(player)
    if pos is None or player.actor is None:
        return
    Blast(
        position=pos,
        velocity=(0, 0, 0),
        blast_radius=1.5,
        blast_type='normal',
        source_player=None,
    ).autoretain()
    player.actor.handlemessage(bs.DieMessage())


def _make_text(
    text: str, color: tuple[float, float, float], y: float = 140.0,
    scale: float = 1.2,
) -> bs.Node:
    return bs.newnode(
        'text',
        attrs={
            'text': text,
            'h_attach': 'center',
            'v_attach': 'center',
            'h_align': 'center',
            'v_align': 'center',
            'color': color,
            'scale': scale,
            'shadow': 1.0,
            'flatness': 1.0,
            'position': (0, y),
        },
    )


def _mean(pts: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    n = float(len(pts))
    return (
        sum(p[0] for p in pts) / n,
        sum(p[1] for p in pts) / n,
        sum(p[2] for p in pts) / n,
    )


def _common_settings() -> list[bs.Setting]:
    return [
        bs.IntChoiceSetting(
            'Time Limit',
            choices=[
                ('None', 0),
                ('1 Minute', 60),
                ('2 Minutes', 120),
                ('5 Minutes', 300),
                ('10 Minutes', 600),
            ],
            default=0,
        ),
        bs.BoolSetting('Epic Mode', default=False),
    ]


# ---------------------------------------------------------------------------
# قاعدة ألعاب البقاء
# ---------------------------------------------------------------------------
class _SurvivalGame(bs.TeamGameActivity[Player, Team]):
    scoreconfig = bs.ScoreConfig(
        label='Survived',
        scoretype=bs.ScoreType.SECONDS,
        none_is_winner=True,
    )
    allow_mid_activity_joins = False

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    @staticmethod
    def _survival_settings(
        default_lives: int = 3,
        default_time: int = 0,
        default_powerups: bool = False,
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Lives Per Player',
                choices=[('1 Life', 1), ('3 Lives', 3), ('5 Lives', 5)],
                default=default_lives,
            ),
            _time_setting(default_time),
            bs.BoolSetting('Powerups', default=default_powerups),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._lives = int(settings.get('Lives Per Player', 1))
        self._time_limit = float(settings.get('Time Limit', 0))
        self._powerups = bool(settings.get('Powerups', False))
        self._epic_mode = bool(settings.get('Epic Mode', False))
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.SURVIVAL
        )
        self._start_time = 0.0
        self._initial_players = 0
        self._ended = False
        self._done = False

    def on_player_join(self, player: Player) -> None:
        player.lives = self._lives
        super().on_player_join(player)

    def on_begin(self) -> None:
        super().on_begin()
        self._start_time = bs.time()
        self._initial_players = len(self.players)
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()

    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        self._eliminate(player)

    def _on_player_died(self, player: Player) -> None:
        player.lives -= 1
        if player.lives > 0:
            self.respawn_player(player)
        else:
            self._eliminate(player)

    def _on_eliminated(self, player: Player) -> None:
        """هوك للألعاب الفرعية."""

    def _eliminate(self, player: Player) -> None:
        if not player.eliminated:
            player.eliminated = True
            self._on_eliminated(player)
        self._check_end()

    def _should_end(self, alive: int) -> bool:
        return alive <= 1 and (self._initial_players > 1 or alive == 0)

    def _check_end(self) -> None:
        if self._ended or not self.has_begun():
            return
        alive = 0
        for team in self.teams:
            if any(not p.eliminated for p in team.players):
                alive += 1
            elif team.survival_seconds is None:
                team.survival_seconds = int(bs.time() - self._start_time)
        if self._should_end(alive):
            self._ended = True
            bs.timer(1.0, bs.WeakCall(self.end_game))

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                self._on_player_died(player)
            return None
        return super().handlemessage(msg)

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.survival_seconds)
        self.end(results=results)


def _add_light(player: Player, color: tuple[float, float, float]) -> None:
    node = getattr(player.actor, 'node', None)
    if not node or player.light:
        return
    light = bs.newnode(
        'light',
        owner=node,
        attrs={'color': color, 'radius': 0.25, 'intensity': 1.5},
    )
    node.connectattr('position', light, 'position')
    player.light = light


# ===========================================================================
# الخرائط (Soccer Field / Basketball Court / Volleyball Arena)
# مبنية على ملاعب اللعبة الرسمية وتظهر لألعاب الرياضة فقط
# ===========================================================================
# ba_meta export bascenev1.GameMap
class SoccerFieldMap(_FootballBase):
    name = 'Soccer Field BY EXTRAX8'

    @classmethod
    def get_play_types(cls) -> list[str]:
        return ['extrax8_sports'] if _MAPS_OK else []


# ba_meta export bascenev1.GameMap
class BasketballCourtMap(_HockeyBase):
    name = 'Basketball Court BY EXTRAX8'

    @classmethod
    def get_play_types(cls) -> list[str]:
        return ['extrax8_sports'] if _MAPS_OK else []


# ba_meta export bascenev1.GameMap
class VolleyballArenaMap(_FootballBase):
    name = 'Volleyball Arena BY EXTRAX8'

    @classmethod
    def get_play_types(cls) -> list[str]:
        return ['extrax8_sports'] if _MAPS_OK else []


# ===========================================================================
# BOMB TAG / HOT POTATO
# ===========================================================================
class _TagGame(_SurvivalGame):
    TAG_RANGE = 1.5

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._assign_at: float | None = None
        self._tick_timer: bs.Timer | None = None
        self._ding = bs.getsound('dingSmall')
        self._tick_snd = bs.getsound('tick')

    def on_begin(self) -> None:
        super().on_begin()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    # --- هوكس تحددها كل لعبة ---
    def _wanted_tags(self, alive_count: int) -> int:
        raise NotImplementedError

    def _new_fuse_end(self, now: float) -> float:
        raise NotImplementedError

    def _fuse_end_after_transfer(self, carrier: Player, now: float) -> float:
        raise NotImplementedError

    # --- أدوات ---
    @staticmethod
    def _get_pos(player: Player) -> Sequence[float] | None:
        actor = player.actor
        node = getattr(actor, 'node', None)
        if actor is None or not node:
            return None
        return node.position

    def _alive_players(self) -> list[Player]:
        return [
            p
            for p in self.players
            if not p.eliminated and self._get_pos(p) is not None
        ]

    def _set_tag(self, player: Player, fuse_end: float) -> None:
        player.fuse_end = fuse_end
        player.last_count = -1
        if player.light:
            return
        node = getattr(player.actor, 'node', None)
        if not node:
            return
        light = bs.newnode(
            'light',
            owner=node,
            attrs={'color': (1.0, 0.25, 0.05), 'radius': 0.25,
                   'intensity': 1.5},
        )
        node.connectattr('position', light, 'position')
        bs.animate(
            light, 'intensity', {0: 1.0, 0.25: 3.0, 0.5: 1.0}, loop=True
        )
        player.light = light

    def _clear_tag(self, player: Player) -> None:
        player.fuse_end = None
        if player.light:
            player.light.delete()
        player.light = None

    def _on_eliminated(self, player: Player) -> None:
        self._clear_tag(player)

    def _explode(self, carrier: Player) -> None:
        pos = self._get_pos(carrier)
        self._clear_tag(carrier)
        if pos is None or carrier.actor is None:
            return
        Blast(
            position=pos,
            velocity=(0, 0, 0),
            blast_radius=1.5,
            blast_type='normal',
            source_player=None,
        ).autoretain()
        carrier.actor.handlemessage(bs.DieMessage())

    def _transfer(self, giver: Player, taker: Player, now: float) -> None:
        fuse_end = self._fuse_end_after_transfer(giver, now)
        self._clear_tag(giver)
        giver.immune_until = now + 1.5
        self._set_tag(taker, fuse_end)
        self._ding.play()
        pos = self._get_pos(taker)
        if pos is not None:
            bs.emitfx(
                position=pos, count=12, scale=0.8, spread=0.4,
                chunk_type='spark',
            )

    def _maintain_tags(self, now: float, alive: list[Player]) -> None:
        alive = [p for p in alive if not p.eliminated]
        tagged = [p for p in alive if p.fuse_end is not None]
        missing = self._wanted_tags(len(alive)) - len(tagged)
        if missing <= 0:
            self._assign_at = None
            return
        if self._assign_at is None:
            self._assign_at = now + 2.5
            return
        if now < self._assign_at:
            return
        self._assign_at = None
        free = [p for p in alive if p.fuse_end is None]
        random.shuffle(free)
        for p in free[:missing]:
            self._set_tag(p, self._new_fuse_end(now))
            self._ding.play()

    def _tick(self) -> None:
        if self._ended or self._done:
            return
        now = bs.time()
        alive = self._alive_players()
        carriers = [p for p in alive if p.fuse_end is not None]
        for c in carriers:
            if c.fuse_end is None or c.eliminated:
                continue
            remaining = c.fuse_end - now
            if remaining <= 0:
                self._explode(c)
                continue
            count = int(math.ceil(remaining))
            if count != c.last_count:
                c.last_count = count
                if c.actor is not None:
                    c.actor.set_score_text(  # type: ignore
                        str(count), color=(1.0, 0.3, 0.1), flash=True
                    )
                if count <= 5:
                    self._tick_snd.play()
            cpos = self._get_pos(c)
            if cpos is None:
                continue
            for o in alive:
                if (
                    o is c
                    or o.eliminated
                    or o.fuse_end is not None
                    or now < o.immune_until
                ):
                    continue
                opos = self._get_pos(o)
                if opos is None:
                    continue
                dist = math.sqrt(
                    (cpos[0] - opos[0]) ** 2
                    + (cpos[1] - opos[1]) ** 2
                    + (cpos[2] - opos[2]) ** 2
                )
                if dist < self.TAG_RANGE:
                    self._transfer(c, o, now)
                    break
        self._maintain_tags(now, alive)


# ba_meta export bascenev1.GameActivity
class BombTagGame(_TagGame):
    """عدة لاعبين يحملون قنابل؛ المس غيرك لتنقلها له."""

    name = 'Bomb Tag BY EXTRAX8'
    description = 'Touch someone to pass the bomb. Do not get blown up!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Fuse Time',
                choices=[('6 Seconds', 6), ('8 Seconds', 8),
                         ('10 Seconds', 10), ('15 Seconds', 15)],
                default=8,
            ),
        ] + _common_settings()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._fuse = float(settings['Fuse Time'])

    def _wanted_tags(self, alive_count: int) -> int:
        if alive_count < 2:
            return 0
        return max(1, alive_count // 4)

    def _new_fuse_end(self, now: float) -> float:
        return now + self._fuse

    def _fuse_end_after_transfer(self, carrier: Player, now: float) -> float:
        return now + self._fuse  # الفتيل يتجدد عند كل نقل


# ba_meta export bascenev1.GameActivity
class HotPotatoGame(_TagGame):
    """قنبلة واحدة بفتيل عشوائي؛ مرّرها قبل ما تنفجر."""

    name = 'Hot Potato BY EXTRAX8'
    description = 'Pass the hot potato before it explodes!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Max Fuse Time',
                choices=[('15 Seconds', 15), ('20 Seconds', 20),
                         ('30 Seconds', 30)],
                default=20,
            ),
        ] + _common_settings()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._max_fuse = float(settings['Max Fuse Time'])

    def _wanted_tags(self, alive_count: int) -> int:
        return 1 if alive_count >= 2 else 0

    def _new_fuse_end(self, now: float) -> float:
        return now + random.uniform(self._max_fuse * 0.5, self._max_fuse)

    def _fuse_end_after_transfer(self, carrier: Player, now: float) -> float:
        # الفتيل يكمل من نفس الوقت المتبقي
        return carrier.fuse_end if carrier.fuse_end is not None else now + 5.0


# ba_meta export bascenev1.GameActivity
class LastManStandingGame(_SurvivalGame):
    """آخر لاعب/فريق حي يفوز."""

    name = 'Last Man Standing BY EXTRAX8'
    description = 'Be the last one alive.'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._survival_settings(3, 0, True)

    def _on_player_died(self, player: Player) -> None:
        player.lives -= 1
        if player.lives > 0:
            bs.broadcastmessage(
                f'{player.getname()}: {player.lives} lives left',
                color=(1.0, 0.6, 0.2),
            )
            self.respawn_player(player)
        else:
            self._eliminate(player)


# ba_meta export bascenev1.GameActivity
class ZombieApocalypseGame(bs.TeamGameActivity[Player, Team]):
    """موجات زومبي؛ اللي يقتل أكثر يفوز (فردي أو فرق)."""

    name = 'Zombie Apocalypse BY EXTRAX8'
    description = 'Survive endless waves of zombies. Most kills wins!'
    scoreconfig = bs.ScoreConfig(label='Kills', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Lives Per Player',
                choices=[('1 Life', 1), ('3 Lives', 3), ('5 Lives', 5)],
                default=3,
            ),
        ] + _common_settings()

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return issubclass(sessiontype, bs.DualTeamSession) or issubclass(
            sessiontype, bs.FreeForAllSession
        )

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        assert bs.app.classic is not None
        return bs.app.classic.getmaps('melee')

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._lives_per_player = int(settings['Lives Per Player'])
        self._epic_mode = bool(settings['Epic Mode'])
        self._time_limit = float(settings['Time Limit'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.SURVIVAL
        )
        self._scoreboard = Scoreboard()
        self._bots = SpazBotSet()
        self._wave = 0
        self._to_spawn = 0
        self._in_flight = 0
        self._wave_active = False
        self._ended = False
        self._done = False
        self._check_timer: bs.Timer | None = None
        self._ding = bs.getsound('dingSmall')

    def on_player_join(self, player: Player) -> None:
        player.lives = self._lives_per_player
        super().on_player_join(player)

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        self.setup_standard_powerup_drops()
        self._update_scoreboard()
        self._check_timer = bs.Timer(
            1.0, bs.WeakCall(self._check_wave), repeat=True
        )
        bs.timer(3.0, bs.WeakCall(self._start_wave))

    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        player.eliminated = True
        self._check_all_dead()

    # --- الموجات ---
    def _pick_bot(self) -> type:
        pool: list[type] = [BrawlerBotLite]
        if self._wave >= 2:
            pool.append(BrawlerBot)
        if self._wave >= 3:
            pool.append(ChargerBot)
        if self._wave >= 4:
            pool += [TriggerBot, BomberBot]
        if self._wave >= 6:
            pool += [BrawlerBotPro, TriggerBotPro]
        return random.choice(pool)

    def _start_wave(self) -> None:
        if self._ended or self._done:
            return
        self._wave += 1
        count = min(3 + 2 * self._wave, 40)
        self._to_spawn = count
        self._wave_active = True
        bs.broadcastmessage(
            f'Wave {self._wave}', color=(1.0, 0.8, 0.2), top=True
        )
        for i in range(count):
            bs.timer(0.7 * i, bs.WeakCall(self._spawn_zombie))

    def _spawn_zombie(self) -> None:
        if self._ended or self._done:
            return
        self._to_spawn -= 1
        pos = self.map.get_ffa_start_position(self.players)
        pos = (
            pos[0] + random.uniform(-0.8, 0.8),
            pos[1],
            pos[2] + random.uniform(-0.8, 0.8),
        )
        self._in_flight += 1
        self._bots.spawn_bot(
            self._pick_bot(),
            pos=pos,
            spawn_time=2.0,
            on_spawn_call=bs.WeakCall(self._on_zombie_spawned),
        )

    def _on_zombie_spawned(self, bot: Any = None) -> None:
        self._in_flight = max(0, self._in_flight - 1)

    def _check_wave(self) -> None:
        if self._ended or self._done or not self._wave_active:
            return
        if (
            self._to_spawn <= 0
            and self._in_flight <= 0
            and not self._bots.have_living_bots()
        ):
            self._wave_active = False
            bs.broadcastmessage(
                f'Wave {self._wave} cleared!', color=(0.2, 1.0, 0.2)
            )
            bs.timer(4.0, bs.WeakCall(self._start_wave))

    # --- الأحداث ---
    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                player.lives -= 1
                if player.lives > 0:
                    self.respawn_player(player)
                else:
                    player.eliminated = True
                    self._check_all_dead()
            return None
        if isinstance(msg, SpazBotDiedMessage):
            killer = getattr(msg, 'killerplayer', None)
            if killer is not None and killer.exists():
                killer.kills += 1
                killer.team.score += 1
                self._ding.play()
                if killer.actor is not None:
                    killer.actor.set_score_text('+1')  # type: ignore
                self._update_scoreboard()
            return None
        return super().handlemessage(msg)

    def _check_all_dead(self) -> None:
        if self._ended or not self.has_begun():
            return
        if all(p.eliminated for p in self.players):
            self._ended = True
            bs.timer(1.5, bs.WeakCall(self.end_game))

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(team, team.score, None)

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self._bots.final_celebrate()
        self.end(results=results)


# ===========================================================================
# SUPER SMASH / FLAPPY SPAZ
# ===========================================================================
_HP_MAX = 100000.0


# ba_meta export bascenev1.GameActivity
class SuperSmashGame(bs.TeamGameActivity[Player, Team]):
    """كل ضربة ترفع نسبة الضرر وتزيد قوة الطرد؛ اطرد خصومك خارج الخريطة."""

    name = 'Super Smash BY EXTRAX8'
    description = 'Knock everyone off the map! More damage = farther launch.'
    scoreconfig = bs.ScoreConfig(
        label='Survived',
        scoretype=bs.ScoreType.SECONDS,
        none_is_winner=True,
    )
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Stocks Per Player',
                choices=[('1 Stock', 1), ('3 Stocks', 3), ('5 Stocks', 5)],
                default=3,
            ),
            bs.FloatChoiceSetting(
                'Knockback',
                choices=[('Low', 0.6), ('Normal', 1.0), ('High', 1.6),
                         ('Insane', 2.5)],
                default=1.0,
            ),
            bs.IntChoiceSetting(
                'Time Limit',
                choices=[('None', 0), ('2 Minutes', 120), ('5 Minutes', 300),
                         ('10 Minutes', 600)],
                default=0,
            ),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return issubclass(sessiontype, bs.DualTeamSession) or issubclass(
            sessiontype, bs.FreeForAllSession
        )

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        # خرائط فيها حواف (لازم تقدر تطرد اللاعب خارجها)
        preferred = ['Big G', 'Roundabout', 'Monkey Face', 'Zigzag',
                     'Step Right Up', 'Tower D', 'Lake Frigid',
                     'Happy Thoughts', 'Doom Shroom']
        maps = _melee_maps()
        picked = [m for m in maps if m in preferred]
        return picked if picked else maps

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._stocks = int(settings['Stocks Per Player'])
        self._knockback = float(settings['Knockback'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.TO_THE_DEATH
        )
        self._start_time = 0.0
        self._initial_players = 0
        self._ended = False
        self._done = False
        self._tick_timer: bs.Timer | None = None

    def on_player_join(self, player: Player) -> None:
        player.lives = self._stocks
        super().on_player_join(player)

    def on_begin(self) -> None:
        super().on_begin()
        self._start_time = bs.time()
        self._initial_players = len(self.players)
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        self._tick_timer = bs.Timer(0.05, bs.WeakCall(self._tick), repeat=True)

    # --- إنشاء اللاعب ---
    def spawn_player(self, player: Player) -> Any:
        spaz = super().spawn_player(player)
        player.percent = 0.0
        node = getattr(spaz, 'node', None)
        if spaz is None or not node:
            return spaz
        spaz.hitpoints_max = _HP_MAX
        spaz.hitpoints = _HP_MAX
        text = bs.newnode(
            'text',
            owner=node,
            attrs={
                'text': '0%',
                'in_world': True,
                'shadow': 1.0,
                'flatness': 1.0,
                'color': (1.0, 1.0, 1.0),
                'scale': 0.02,
                'h_align': 'center',
            },
        )
        mathnode = bs.newnode(
            'math',
            owner=node,
            attrs={'input1': (0, 1.5, 0), 'operation': 'add'},
        )
        node.connectattr('torso_position', mathnode, 'input2')
        mathnode.connectattr('output', text, 'position')
        player.pct_text = text
        return spaz

    # --- المنطق الرئيسي: قراءة الضرر وتحويله لنسبة + طرد ---
    def _tick(self) -> None:
        if self._done:
            return
        for player in self.players:
            if player.eliminated:
                continue
            spaz = player.actor
            node = getattr(spaz, 'node', None)
            if spaz is None or not node:
                continue
            damage = _HP_MAX - float(spaz.hitpoints)
            if damage > 0.5:
                spaz.hitpoints = _HP_MAX
                gained = damage / 30.0
                player.percent += gained
                self._launch(node, gained, player.percent)
            self._update_percent_text(player)

    def _launch(self, node: bs.Node, gained: float, percent: float) -> None:
        vel = node.velocity
        speed = math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2)
        if speed < 0.5:
            return
        d = (vel[0] / speed, vel[1] / speed, vel[2] / speed)
        mag = 40.0 * gained * self._knockback * (1.0 + percent / 60.0)
        pos = node.position
        node.handlemessage(
            'impulse', pos[0], pos[1], pos[2],
            d[0], d[1], d[2],
            mag, 0.0, 1.0, 0,
            d[0], d[1], d[2],
        )

    @staticmethod
    def _update_percent_text(player: Player) -> None:
        text = player.pct_text
        if not text:
            return
        pct = player.percent
        text.text = f'{int(pct)}%'
        shade = max(0.1, 1.0 - pct / 150.0)
        text.color = (1.0, shade, shade)

    # --- الأرواح والإقصاء ---
    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                player.lives -= 1
                if player.lives > 0:
                    bs.broadcastmessage(
                        f'{player.getname()}: {player.lives} stocks left',
                        color=(1.0, 0.6, 0.2),
                    )
                    self.respawn_player(player)
                else:
                    self._eliminate(player)
            return None
        return super().handlemessage(msg)

    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        self._eliminate(player)

    def _eliminate(self, player: Player) -> None:
        player.eliminated = True
        self._check_end()

    def _check_end(self) -> None:
        if self._ended or not self.has_begun():
            return
        alive = 0
        for team in self.teams:
            if any(not p.eliminated for p in team.players):
                alive += 1
            elif team.survival_seconds is None:
                team.survival_seconds = int(bs.time() - self._start_time)
        if alive <= 1 and (self._initial_players > 1 or alive == 0):
            self._ended = True
            bs.timer(1.0, bs.WeakCall(self.end_game))

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.survival_seconds)
        self.end(results=results)


# ===========================================================================
# FLAPPY SPAZ  (لعبة 2D على الشاشة؛ بدون فيزياء، كل شيء محسوب بالكود)
# ===========================================================================
_HALF_W = 330.0     # نصف عرض منطقة اللعب (وحدات الشاشة)
_HALF_H = 170.0     # نصف ارتفاع منطقة اللعب
_PIPE_W = 60.0
_BIRD = 22.0
_GRAVITY = 700.0
_FLAP_V = 270.0
_PIPE_SPACING = 230.0
_START_DELAY = 1.5


# ba_meta export bascenev1.GameActivity
class FlappySpazGame(bs.TeamGameActivity[Player, Team]):
    """اضغط قفز/لكم لترفرف وتمر من بين الأنابيب."""

    name = 'Flappy Spaz BY EXTRAX8'
    description = 'Press JUMP or PUNCH to flap. Pass the pipes, do not crash!'
    scoreconfig = bs.ScoreConfig(label='Pipes', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Pipe Gap',
                choices=[('Easy', 170), ('Normal', 140), ('Hard', 115)],
                default=140,
            ),
            bs.FloatChoiceSetting(
                'Screen Scale',
                choices=[('Small', 0.7), ('Normal', 1.0), ('Large', 1.3)],
                default=1.0,
            ),
            bs.IntChoiceSetting(
                'Time Limit',
                choices=[('None', 0), ('1 Minute', 60), ('2 Minutes', 120),
                         ('5 Minutes', 300)],
                default=0,
            ),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return issubclass(sessiontype, bs.DualTeamSession) or issubclass(
            sessiontype, bs.FreeForAllSession
        )

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._gap = float(settings['Pipe Gap'])
        self._ui = float(settings['Screen Scale'])
        self._time_limit = float(settings['Time Limit'])
        self.default_music = bs.MusicType.SURVIVAL
        self._scoreboard = Scoreboard()
        self._pipes: list[dict[str, Any]] = []
        self._tick_timer: bs.Timer | None = None
        self._last_time = 0.0
        self._elapsed = 0.0
        self._next_pipe_id = 0
        self._ended = False
        self._done = False
        self._ding = bs.getsound('dingSmall')
        self._hit_sound = self._try_sound(['explosion01', 'hiss'])

    # --- أدوات مساعدة ---
    @staticmethod
    def _try_sound(names: list[str]) -> Any:
        for n in names:
            try:
                return bs.getsound(n)
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    def _try_texture(names: list[str]) -> Any:
        for n in names:
            try:
                return bs.gettexture(n)
            except Exception:  # noqa: BLE001
                continue
        return None

    def _make_rect(
        self,
        color: tuple[float, float, float],
        fill: bool = False,
    ) -> bs.Node:
        attrs: dict[str, Any] = {
            'attach': 'center',
            'opacity': 1.0,
            'position': (0, 0),
            'scale': (10, 10),
        }
        tex = self._try_texture(['white', 'bar', 'nub'])
        if tex is not None:
            attrs['texture'] = tex
        if fill:
            attrs['fill_screen'] = True
        node = bs.newnode('image', attrs=attrs)
        # اسم صفة اللون يختلف حسب النسخة، نجرب الاثنين
        for attr in ('color', 'tint_color'):
            try:
                setattr(node, attr, color)
            except Exception:  # noqa: BLE001
                pass
        return node

    def _make_text(self, text: str, color: tuple[float, float, float]) -> bs.Node:
        return bs.newnode(
            'text',
            attrs={
                'text': text,
                'h_attach': 'center',
                'v_attach': 'center',
                'h_align': 'center',
                'v_align': 'center',
                'color': color,
                'scale': 0.5,
                'shadow': 1.0,
                'flatness': 1.0,
                'position': (0, 0),
            },
        )

    # --- بدء اللعبة ---
    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def spawn_player(self, player: Player) -> Any:
        # ما نحتاج شخصية حقيقية؛ اللعبة كلها على الشاشة
        return None

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)

        # الخلفية
        self._make_rect((0.35, 0.70, 0.95), fill=True)

        # الأنابيب
        gy = 0.0
        for i in range(5):
            gy = self._next_gap_center(gy)
            pipe = {
                'x': _HALF_W + 60.0 + i * _PIPE_SPACING,
                'gy': gy,
                'id': self._next_pipe_id,
                'top': self._make_rect((0.2, 0.75, 0.2)),
                'bottom': self._make_rect((0.2, 0.75, 0.2)),
            }
            self._next_pipe_id += 1
            self._pipes.append(pipe)
            self._place_pipe(pipe)

        # الطيور
        for i, player in enumerate(self.players):
            player.x = -170.0 + (i % 8) * 18.0
            player.y = 0.0
            player.vy = 0.0
            player.bird_alive = True
            player.bird_node = self._make_rect(tuple(player.color))  # type: ignore
            player.bird_node.scale = (_BIRD * self._ui, _BIRD * self._ui)
            player.bird_label = self._make_text(
                player.getname(icon=False), tuple(player.color)  # type: ignore
            )
            player.assigninput(
                (
                    bs.InputType.JUMP_PRESS,
                    bs.InputType.PUNCH_PRESS,
                    bs.InputType.BOMB_PRESS,
                    bs.InputType.PICK_UP_PRESS,
                ),
                bs.WeakCall(self._flap, player),
            )
            self._place_bird(player)

        self._update_scoreboard()
        bs.broadcastmessage(
            'Press JUMP / PUNCH to flap!', color=(1.0, 1.0, 0.4), top=True
        )
        self._last_time = bs.time()
        self._tick_timer = bs.Timer(
            0.016, bs.WeakCall(self._tick), repeat=True
        )

    def _next_gap_center(self, prev: float) -> float:
        lo = -_HALF_H + self._gap / 2 + 30.0
        hi = _HALF_H - self._gap / 2 - 30.0
        return max(lo, min(hi, prev + random.uniform(-90.0, 90.0)))

    # --- رسم ---
    def _place_pipe(self, pipe: dict[str, Any]) -> None:
        s = self._ui
        gy = pipe['gy']
        x = pipe['x']
        top_lo = gy + self._gap / 2
        top_hi = 600.0
        bot_hi = gy - self._gap / 2
        bot_lo = -600.0
        pipe['top'].position = (x * s, (top_lo + top_hi) / 2 * s)
        pipe['top'].scale = (_PIPE_W * s, (top_hi - top_lo) * s)
        pipe['bottom'].position = (x * s, (bot_hi + bot_lo) / 2 * s)
        pipe['bottom'].scale = (_PIPE_W * s, (bot_hi - bot_lo) * s)

    def _place_bird(self, player: Player) -> None:
        s = self._ui
        if player.bird_node:
            player.bird_node.position = (player.x * s, player.y * s)
        if player.bird_label:
            player.bird_label.position = (player.x * s, (player.y + 24.0) * s)

    # --- الإدخال ---
    def _flap(self, player: Player) -> None:
        if self._done or not player.bird_alive:
            return
        player.vy = _FLAP_V

    # --- حلقة اللعبة ---
    def _tick(self) -> None:
        if self._done:
            return
        now = bs.time()
        dt = min(now - self._last_time, 0.05)
        self._last_time = now
        if dt <= 0.0:
            return
        self._elapsed += dt
        running = self._elapsed >= _START_DELAY

        # الأنابيب
        if running:
            speed = min(140.0 + self._elapsed * 2.0, 260.0)
            for pipe in self._pipes:
                pipe['x'] -= speed * dt
            for pipe in self._pipes:
                if pipe['x'] < -(_HALF_W + 80.0):
                    far = max(p['x'] for p in self._pipes)
                    pipe['x'] = far + _PIPE_SPACING
                    pipe['gy'] = self._next_gap_center(pipe['gy'])
                    pipe['id'] = self._next_pipe_id
                    self._next_pipe_id += 1
            for pipe in self._pipes:
                self._place_pipe(pipe)

        # الطيور
        scored = False
        half = _BIRD / 2
        for player in self.players:
            if not player.bird_alive:
                continue
            if running:
                player.vy -= _GRAVITY * dt
                player.y += player.vy * dt
            if player.y > _HALF_H - half:
                player.y = _HALF_H - half
                player.vy = min(player.vy, 0.0)
            if player.y < -_HALF_H + half:
                self._kill_bird(player)
                continue
            for pipe in self._pipes:
                dx = abs(player.x - pipe['x'])
                if dx < _PIPE_W / 2 + half:
                    if (
                        player.y + half > pipe['gy'] + self._gap / 2
                        or player.y - half < pipe['gy'] - self._gap / 2
                    ):
                        self._kill_bird(player)
                        break
                if (
                    pipe['id'] > player.last_pipe_id
                    and pipe['x'] + _PIPE_W / 2 < player.x - half
                ):
                    player.last_pipe_id = pipe['id']
                    player.pipes_passed += 1
                    scored = True
                    self._ding.play()
            if player.bird_alive:
                self._place_bird(player)

        if scored:
            self._update_scoreboard()
        self._check_end()

    def _kill_bird(self, player: Player) -> None:
        player.bird_alive = False
        if self._hit_sound is not None:
            self._hit_sound.play()
        if player.bird_node:
            player.bird_node.opacity = 0.0
        if player.bird_label:
            player.bird_label.text = ''

    # --- النتيجة ---
    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        player.bird_alive = False
        if player.bird_node:
            player.bird_node.opacity = 0.0
        if player.bird_label:
            player.bird_label.text = ''
        self._check_end()

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            team.score = sum(p.pipes_passed for p in team.players)
            self._scoreboard.set_team_value(team, team.score, None)

    def _check_end(self) -> None:
        if self._ended or not self.has_begun():
            return
        if not any(p.bird_alive for p in self.players):
            self._ended = True
            bs.timer(1.5, bs.WeakCall(self.end_game))

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        self._update_scoreboard()
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ===========================================================================
# ألعاب المطر / Infection / Collector / Boxing / Gun Game
# ===========================================================================
class _RainGame(_SurvivalGame):
    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._survival_settings(3, 0, False) + [
            bs.FloatChoiceSetting(
                'Intensity',
                choices=[('Low', 1.6), ('Normal', 1.1), ('High', 0.7),
                         ('Insane', 0.4)],
                default=1.1,
            ),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._interval = float(settings.get('Intensity', 1.1))
        self._rain_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        bs.timer(3.0, bs.WeakCall(self._start_rain))

    def _start_rain(self) -> None:
        if self._done:
            return
        self._rain_timer = bs.Timer(
            self._interval, bs.WeakCall(self._rain_tick), repeat=True
        )

    def _rain_tick(self) -> None:
        if self._done or self._ended:
            return
        targets: list[Sequence[float]] = []
        for p in self.players:
            if p.eliminated:
                continue
            pos = _pos(p)
            if pos is not None:
                targets.append(pos)
        if not targets:
            return
        count = 1 + int((bs.time() - self._start_time) / 25.0)
        for _ in range(min(count, 6)):
            self._spawn_hazard(random.choice(targets))

    def _spawn_hazard(self, target: Sequence[float]) -> None:
        raise NotImplementedError


# ba_meta export bascenev1.GameActivity
class AvalancheGame(_RainGame):
    name = 'Avalanche BY EXTRAX8'
    description = 'Bombs rain from the sky. Survive!'

    def _spawn_hazard(self, target: Sequence[float]) -> None:
        pos = (
            target[0] + random.uniform(-3.0, 3.0),
            target[1] + 12.0,
            target[2] + random.uniform(-3.0, 3.0),
        )
        Bomb(
            position=pos,
            velocity=(0.0, -3.0, 0.0),
            bomb_type=random.choice(['normal', 'normal', 'ice', 'sticky']),
        ).autoretain()


# ba_meta export bascenev1.GameActivity
class MeteorShowerGame(_RainGame):
    name = 'Meteor Shower BY EXTRAX8'
    description = 'Meteors crash down from the sky. Keep moving!'

    def _spawn_hazard(self, target: Sequence[float]) -> None:
        vel = (random.uniform(-10.0, 10.0), -8.0, random.uniform(-4.0, 4.0))
        pos = (
            target[0] - vel[0] * 1.2 + random.uniform(-2.0, 2.0),
            target[1] + 14.0,
            target[2] - vel[2] * 1.2 + random.uniform(-2.0, 2.0),
        )
        Bomb(
            position=pos,
            velocity=vel,
            bomb_type='impact',
            blast_radius=2.2,
        ).autoretain()


# ba_meta export bascenev1.GameActivity
class DodgeTheBallGame(_RainGame):
    name = 'Dodge the Ball BY EXTRAX8'
    description = 'Balls are fired at you from every side. Dodge them!'

    def _spawn_hazard(self, target: Sequence[float]) -> None:
        angle = random.uniform(0.0, 2.0 * math.pi)
        dx, dz = math.cos(angle), math.sin(angle)
        pos = (target[0] + dx * 12.0, target[1] + 1.5, target[2] + dz * 12.0)
        speed = 13.0
        vel = (-dx * speed, 3.0, -dz * speed)
        Bomb(
            position=pos,
            velocity=vel,
            bomb_type='impact',
            blast_radius=1.8,
        ).autoretain()


# ba_meta export bascenev1.GameActivity
class BotShowerGame(_RainGame):
    name = 'Bot Shower BY EXTRAX8'
    description = 'Bots fall from the sky and attack. Survive!'

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._bots = SpazBotSet()

    def _spawn_hazard(self, target: Sequence[float]) -> None:
        if len(self._bots.get_living_bots()) >= 10:
            return
        pos = (
            target[0] + random.uniform(-3.0, 3.0),
            target[1] + 6.0,
            target[2] + random.uniform(-3.0, 3.0),
        )
        self._bots.spawn_bot(
            random.choice([BrawlerBotLite, BrawlerBot]),
            pos=pos,
            spawn_time=0.5,
        )

    def end_game(self) -> None:
        if not self._done:
            self._bots.final_celebrate()
        super().end_game()


# ba_meta export bascenev1.GameActivity
class InfectionGame(_SurvivalGame):
    """المصابون يطاردون الناجين؛ المس ناجياً لتصيبه."""

    name = 'Infection BY EXTRAX8'
    description = 'Infected players hunt survivors. Touch to infect!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Initial Infected',
                choices=[('1', 1), ('2', 2), ('3', 3)],
                default=1,
            ),
            _time_setting(120),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._initial_infected = int(settings.get('Initial Infected', 1))
        self._tick_timer: bs.Timer | None = None
        self._ding = bs.getsound('dingSmall')

    def on_begin(self) -> None:
        super().on_begin()
        bs.timer(3.0, bs.WeakCall(self._pick_infected))
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _should_end(self, alive: int) -> bool:
        return alive == 0

    def _pick_infected(self) -> None:
        if self._done:
            return
        candidates = [
            p for p in self.players
            if not p.infected and _pos(p) is not None
        ]
        if len(candidates) < 2:
            return
        n = min(self._initial_infected, len(candidates) - 1)
        for p in random.sample(candidates, n):
            self._infect(p)

    def _apply_look(self, player: Player) -> None:
        node = getattr(player.actor, 'node', None)
        if not node:
            return
        try:
            node.color = (0.2, 0.9, 0.2)
            node.highlight = (0.4, 1.0, 0.4)
        except Exception:  # noqa: BLE001
            pass
        if not player.light:
            light = bs.newnode(
                'light',
                owner=node,
                attrs={'color': (0.2, 1.0, 0.2), 'radius': 0.25,
                       'intensity': 1.5},
            )
            node.connectattr('position', light, 'position')
            player.light = light

    def _infect(self, player: Player) -> None:
        if player.infected:
            return
        player.infected = True
        self._apply_look(player)
        self._eliminate(player)

    def spawn_player(self, player: Player) -> Any:
        spaz = super().spawn_player(player)
        if player.infected:
            self._apply_look(player)
        return spaz

    def _on_player_died(self, player: Player) -> None:
        if not player.infected:
            self._infect(player)
        self.respawn_player(player)

    def _tick(self) -> None:
        if self._done:
            return
        infected = []
        healthy = []
        for p in self.players:
            pos = _pos(p)
            if pos is None:
                continue
            (infected if p.infected else healthy).append((p, pos))
        for _, ipos in infected:
            for h, hpos in healthy:
                if h.infected:
                    continue
                dist = math.sqrt(
                    (ipos[0] - hpos[0]) ** 2
                    + (ipos[1] - hpos[1]) ** 2
                    + (ipos[2] - hpos[2]) ** 2
                )
                if dist < 1.4:
                    self._infect(h)
                    self._ding.play()
                    bs.emitfx(
                        position=hpos, count=15, scale=0.9, spread=0.5,
                        chunk_type='spark',
                    )


# ba_meta export bascenev1.GameActivity
class CollectorGame(bs.TeamGameActivity[Player, Team]):
    """اجمع الأعلام الذهبية؛ الأكثر جمعاً يفوز."""

    name = 'Collector BY EXTRAX8'
    description = 'Grab the golden flags. Most flags wins!'
    scoreconfig = bs.ScoreConfig(label='Flags', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Flags To Win',
                choices=[('None', 0), ('10', 10), ('20', 20), ('30', 30)],
                default=20,
            ),
            bs.IntChoiceSetting(
                'Flags On Field',
                choices=[('3', 3), ('5', 5), ('8', 8)],
                default=5,
            ),
            _time_setting(120),
            bs.BoolSetting('Powerups', default=True),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._target = int(settings['Flags To Win'])
        self._field = int(settings['Flags On Field'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.FLAG_CATCHER
        )
        self._scoreboard = Scoreboard()
        self._coins: list[Flag] = []
        self._tick_timer: bs.Timer | None = None
        self._done = False
        self._ding = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        for _ in range(self._field):
            self._spawn_coin()
        self._update_scoreboard()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _spawn_coin(self) -> None:
        if self._done:
            return
        pos = self.map.get_ffa_start_position(self.players)
        pos = (
            pos[0] + random.uniform(-2.0, 2.0),
            pos[1] + 0.3,
            pos[2] + random.uniform(-2.0, 2.0),
        )
        self._coins.append(
            Flag(position=pos, touchable=False, color=(1.0, 0.85, 0.1))
        )

    def _tick(self) -> None:
        if self._done:
            return
        for flag in list(self._coins):
            node = flag.node
            if not node:
                self._coins.remove(flag)
                bs.timer(0.6, bs.WeakCall(self._spawn_coin))
                continue
            fpos = node.position
            for player in self.players:
                ppos = _pos(player)
                if ppos is None:
                    continue
                dx = ppos[0] - fpos[0]
                dz = ppos[2] - fpos[2]
                if math.sqrt(dx * dx + dz * dz) < 1.4 and abs(
                    ppos[1] - fpos[1]
                ) < 2.5:
                    self._collect(player, flag)
                    break

    def _collect(self, player: Player, flag: Flag) -> None:
        if flag not in self._coins:
            return
        self._coins.remove(flag)
        flag.handlemessage(bs.DieMessage())
        player.coins += 1
        player.team.score += 1
        self._ding.play()
        if player.actor is not None:
            player.actor.set_score_text('+1')  # type: ignore
        self._update_scoreboard()
        bs.timer(0.6, bs.WeakCall(self._spawn_coin))
        if self._target > 0 and player.team.score >= self._target:
            self.end_game()

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                self.respawn_player(player)
            return None
        return super().handlemessage(msg)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._target if self._target > 0 else None
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ba_meta export bascenev1.GameActivity
class BoxingGame(bs.TeamGameActivity[Player, Team]):
    """قفازات فقط، بدون قنابل؛ اطرح خصومك أرضاً لتسجل نقطة."""

    name = 'Boxing BY EXTRAX8'
    description = 'Gloves only, no bombs. Knock out enemies to score!'
    scoreconfig = bs.ScoreConfig(label='KOs', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntSetting('Kills to Win Per Player', min_value=1,
                          default=5, increment=1),
            _time_setting(0),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._scoreboard = Scoreboard()
        self._score_to_win: int | None = None
        self._kills_per_player = int(settings['Kills to Win Per Player'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.TO_THE_DEATH
        )
        self._done = False
        self._dingsound = bs.getsound('dingSmall')

    def get_instance_description(self) -> str | Sequence:
        return 'Get ${ARG1} knockouts.', self._score_to_win

    def get_instance_description_short(self) -> str | Sequence:
        return 'get ${ARG1} knockouts', self._score_to_win

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        self._score_to_win = self._kills_per_player * max(
            1, max(len(t.players) for t in self.teams)
        )
        self._update_scoreboard()

    def spawn_player(self, player: Player) -> Any:
        spaz = super().spawn_player(player)
        node = getattr(spaz, 'node', None)
        if spaz is not None and node:
            spaz.connect_controls_to_player(
                enable_bomb=False, enable_pickup=False
            )
            spaz.equip_boxing_gloves()
        return spaz

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is None:
                return None
            self.respawn_player(player)
            killer = msg.getkillerplayer(Player)
            if killer is None or killer is player:
                return None
            if killer.team is player.team:
                killer.team.score -= 1
            else:
                killer.team.score += 1
                self._dingsound.play()
                if killer.actor is not None:
                    killer.actor.set_score_text(  # type: ignore
                        str(killer.team.score)
                    )
            self._update_scoreboard()
            assert self._score_to_win is not None
            if any(t.score >= self._score_to_win for t in self.teams):
                self.end_game()
            return None
        return super().handlemessage(msg)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._score_to_win
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


_LADDER = ['normal', 'ice', 'sticky', 'impact', 'punch']


# ba_meta export bascenev1.GameActivity
class GunGameGame(bs.TeamGameActivity[Player, Team]):
    """كل قتلة تغيّر سلاحك للأقوى؛ أول من يكمل السلم يفوز."""

    name = 'Gun Game BY EXTRAX8'
    description = 'Every kill upgrades your weapon. Finish the ladder to win!'
    scoreconfig = bs.ScoreConfig(label='Level', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            _time_setting(0),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._scoreboard = Scoreboard()
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.TO_THE_DEATH
        )
        self._done = False
        self._dingsound = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        self._update_scoreboard()

    def _apply_weapon(self, player: Player, spaz: Any = None) -> None:
        spaz = spaz if spaz is not None else player.actor
        node = getattr(spaz, 'node', None)
        if spaz is None or not node:
            return
        kind = _LADDER[min(player.gg_level, len(_LADDER) - 1)]
        if kind == 'punch':
            spaz.connect_controls_to_player(enable_bomb=False)
            spaz.equip_boxing_gloves()
        else:
            spaz.bomb_type = kind
            spaz.bomb_type_default = kind

    def spawn_player(self, player: Player) -> Any:
        spaz = super().spawn_player(player)
        self._apply_weapon(player, spaz)
        return spaz

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is None:
                return None
            self.respawn_player(player)
            killer = msg.getkillerplayer(Player)
            if killer is None or killer is player:
                player.gg_level = max(0, player.gg_level - 1)
            elif killer.team is not player.team:
                killer.gg_level += 1
                self._dingsound.play()
                if killer.gg_level >= len(_LADDER):
                    killer.team.score += 100  # فوز مضمون
                    self._update_scoreboard()
                    self.end_game()
                    return None
                self._apply_weapon(killer)
                if killer.actor is not None:
                    killer.actor.set_score_text(  # type: ignore
                        f'Level {killer.gg_level + 1}'
                    )
            self._update_scoreboard()
            return None
        return super().handlemessage(msg)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            bonus = 100 if team.score >= 100 else 0
            team.score = bonus + sum(p.gg_level for p in team.players)
            self._scoreboard.set_team_value(team, team.score, None)

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ===========================================================================
# 1) HIDE AND SEEK
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class HideAndSeekGame(_SurvivalGame):
    name = 'Hide and Seek BY EXTRAX8'
    description = 'Seekers hunt the hiders. Hiders: survive until time is up!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Seekers',
                choices=[('1', 1), ('2', 2), ('3', 3)],
                default=1,
            ),
            bs.IntChoiceSetting(
                'Hide Time',
                choices=[('10 Seconds', 10), ('20 Seconds', 20),
                         ('30 Seconds', 30)],
                default=20,
            ),
            _time_setting(300),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._seeker_count = int(settings['Seekers'])
        self._hide_time = float(settings['Hide Time'])
        self._frozen = False
        self._tick_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        self._pick_seekers()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _should_end(self, alive: int) -> bool:
        return alive == 0

    def _pick_seekers(self) -> None:
        cands = [p for p in self.players if _pos(p) is not None]
        if len(cands) < 2:
            return
        n = min(self._seeker_count, len(cands) - 1)
        chosen = random.sample(cands, n)
        self._frozen = True
        for p in chosen:
            p.seeker = True
            _add_light(p, (1.0, 0.2, 0.1))
            self._freeze(p)
            self._eliminate(p)
        bs.broadcastmessage(
            f'Seekers are blind for {int(self._hide_time)} seconds. Hide!',
            color=(1.0, 1.0, 0.2),
            top=True,
        )
        bs.timer(self._hide_time, bs.WeakCall(self._release))

    @staticmethod
    def _freeze(player: Player) -> None:
        actor = player.actor
        if actor is not None and getattr(actor, 'node', None):
            actor.disconnect_controls_from_player()  # type: ignore

    def _release(self) -> None:
        self._frozen = False
        for p in self.players:
            if p.seeker and p.actor is not None and getattr(
                p.actor, 'node', None
            ):
                p.actor.connect_controls_to_player()  # type: ignore
        bs.broadcastmessage('Seekers released!', color=(1.0, 0.3, 0.3),
                            top=True)

    def spawn_player(self, player: Player) -> Any:
        spaz = super().spawn_player(player)
        if player.seeker:
            _add_light(player, (1.0, 0.2, 0.1))
            if self._frozen:
                self._freeze(player)
        return spaz

    def _on_player_died(self, player: Player) -> None:
        if player.seeker:
            self.respawn_player(player)
        else:
            self._eliminate(player)

    def _tick(self) -> None:
        if self._done or self._frozen:
            return
        seekers = []
        hiders = []
        for p in self.players:
            pos = _pos(p)
            if pos is None:
                continue
            if p.seeker:
                seekers.append(pos)
            elif not p.eliminated:
                hiders.append((p, pos))
        for spos in seekers:
            for h, hpos in hiders:
                if not h.eliminated and _dist(spos, hpos) < 1.4:
                    _blast_kill(h)


# ===========================================================================
# 2) SNAKE
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class SnakeGame(bs.TeamGameActivity[Player, Team]):
    name = 'Snake BY EXTRAX8'
    description = 'Collect flags to grow your tail. Crash into a tail and die!'
    scoreconfig = bs.ScoreConfig(label='Score', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Score To Win',
                choices=[('None', 0), ('15', 15), ('30', 30), ('50', 50)],
                default=30,
            ),
            _time_setting(120),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._target = int(settings['Score To Win'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.RUN_AWAY
        )
        self._scoreboard = Scoreboard()
        self._coins: list[Flag] = []
        self._tick_timer: bs.Timer | None = None
        self._done = False
        self._ding = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        for _ in range(5):
            self._spawn_coin()
        self._update_scoreboard()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _spawn_coin(self) -> None:
        if self._done:
            return
        self._coins.append(
            Flag(position=_rand_point(self), touchable=False,
                 color=(1.0, 0.85, 0.1))
        )

    @staticmethod
    def _clear_tail(player: Player) -> None:
        player.snake_tail = []
        while player.snake_lights:
            player.snake_lights.pop().delete()

    def _sync_lights(self, player: Player) -> None:
        tail = player.snake_tail
        lights = player.snake_lights
        while len(lights) < len(tail):
            lights.append(
                bs.newnode(
                    'light',
                    attrs={'color': tuple(player.color), 'radius': 0.25,
                           'intensity': 0.8, 'position': tail[len(lights)]},
                )
            )
        while len(lights) > len(tail):
            lights.pop().delete()
        for light, pt in zip(lights, tail):
            light.position = (pt[0], pt[1] + 0.2, pt[2])

    def _hit_tail(self, player: Player, pos: Sequence[float]) -> Player | None:
        for q in self.players:
            start = 5 if q is player else 1
            for pt in q.snake_tail[start:]:
                if _hdist(pos, pt) < 0.7 and abs(pos[1] - pt[1]) < 1.5:
                    return q
        return None

    def _tick(self) -> None:
        if self._done:
            return
        alive: list[tuple[Player, Sequence[float]]] = []
        for p in self.players:
            pos = _pos(p)
            if pos is None:
                if p.snake_tail or p.snake_lights:
                    self._clear_tail(p)
                continue
            alive.append((p, pos))
            if not p.snake_tail or _hdist(pos, p.snake_tail[0]) > 0.8:
                p.snake_tail.insert(0, (pos[0], pos[1], pos[2]))
                del p.snake_tail[p.snake_len:]
                self._sync_lights(p)

        for p, pos in alive:
            owner = self._hit_tail(p, pos)
            if owner is not None:
                if owner is not p:
                    owner.team.score += 2
                    self._update_scoreboard()
                if p.actor is not None:
                    p.actor.handlemessage(bs.DieMessage())
                continue
            for flag in list(self._coins):
                node = flag.node
                if not node:
                    self._coins.remove(flag)
                    bs.timer(0.6, bs.WeakCall(self._spawn_coin))
                    continue
                fpos = node.position
                if _hdist(pos, fpos) < 1.4 and abs(pos[1] - fpos[1]) < 2.5:
                    self._coins.remove(flag)
                    flag.handlemessage(bs.DieMessage())
                    p.snake_len = min(p.snake_len + 2, 16)
                    p.team.score += 1
                    self._ding.play()
                    self._update_scoreboard()
                    bs.timer(0.6, bs.WeakCall(self._spawn_coin))
                    if self._target > 0 and p.team.score >= self._target:
                        self.end_game()
                    break

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                player.snake_len = 3
                self._clear_tail(player)
                self.respawn_player(player)
            return None
        return super().handlemessage(msg)

    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        self._clear_tail(player)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._target if self._target > 0 else None
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        for p in self.players:
            self._clear_tail(p)
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ===========================================================================
# 3) SLEEP RACE
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class SleepRaceGame(bs.TeamGameActivity[Player, Team]):
    name = 'Sleep Race BY EXTRAX8'
    description = 'Race to your colored flags - but you randomly fall asleep!'
    scoreconfig = bs.ScoreConfig(label='Flags', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Flags To Win',
                choices=[('5', 5), ('10', 10), ('15', 15)],
                default=10,
            ),
            bs.FloatChoiceSetting(
                'Sleepiness',
                choices=[('Low', 20.0), ('Normal', 12.0), ('High', 7.0)],
                default=12.0,
            ),
            _time_setting(0),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._flags_per_player = int(settings['Flags To Win'])
        self._interval = float(settings['Sleepiness'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.RACE
        )
        self._scoreboard = Scoreboard()
        self._score_to_win = 0
        self._tick_timer: bs.Timer | None = None
        self._done = False
        self._ding = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        self._score_to_win = self._flags_per_player * max(
            1, max(len(t.players) for t in self.teams)
        )
        now = bs.time()
        for p in self.players:
            p.next_sleep = now + random.uniform(0.5, 1.2) * self._interval
            self._spawn_flag(p)
        self._update_scoreboard()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _spawn_flag(self, player: Player) -> None:
        if self._done:
            return
        ppos = _pos(player)
        avoid = [ppos] if ppos is not None else None
        pos = _rand_point(self, avoid=avoid, min_dist=6.0)
        player.cp_flag = Flag(
            position=pos, touchable=False, color=tuple(player.color)
        )

    def _wake(self, player: Player) -> None:
        actor = player.actor
        if actor is not None and getattr(actor, 'node', None):
            actor.handlemessage(bs.ThawMessage())

    def _tick(self) -> None:
        if self._done:
            return
        now = bs.time()
        for p in self.players:
            pos = _pos(p)
            if pos is None:
                continue
            flag = p.cp_flag
            if flag is not None:
                node = flag.node
                if not node:
                    p.cp_flag = None
                    bs.timer(0.3, bs.WeakCall(self._spawn_flag, p))
                else:
                    fpos = node.position
                    if _hdist(pos, fpos) < 1.5 and abs(pos[1] - fpos[1]) < 2.5:
                        flag.handlemessage(bs.DieMessage())
                        p.cp_flag = None
                        p.cp_count += 1
                        p.team.score += 1
                        self._ding.play()
                        self._update_scoreboard()
                        bs.timer(0.3, bs.WeakCall(self._spawn_flag, p))
                        if p.team.score >= self._score_to_win:
                            self.end_game()
                            return
            if now >= p.next_sleep and p.actor is not None:
                p.next_sleep = now + random.uniform(0.6, 1.4) * self._interval
                p.actor.handlemessage(bs.FreezeMessage())
                p.actor.set_score_text('Zzz...')  # type: ignore
                bs.timer(2.0, bs.WeakCall(self._wake, p))

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                self.respawn_player(player)
            return None
        return super().handlemessage(msg)

    def on_player_leave(self, player: Player) -> None:
        super().on_player_leave(player)
        if player.cp_flag is not None:
            player.cp_flag.handlemessage(bs.DieMessage())
            player.cp_flag = None

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._score_to_win
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ===========================================================================
# 4) SIMON SAYS
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class SimonSaysGame(_SurvivalGame):
    name = 'Simon Says BY EXTRAX8'
    description = 'Do what Simon says - and ONLY when Simon says!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.FloatChoiceSetting(
                'Difficulty',
                choices=[('Easy', 4.5), ('Normal', 3.5), ('Hard', 2.8)],
                default=3.5,
            ),
            _time_setting(0),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._base_window = float(settings['Difficulty'])
        self._round = 0
        self._open = False
        self._cmd = 'still'
        self._simon = True
        self._track_from = 0.0
        self._text: bs.Node | None = None
        self._tick_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        self._text = _make_text('Get ready...', (1.0, 1.0, 0.3))
        bs.timer(4.0, bs.WeakCall(self._start_round))
        self._tick_timer = bs.Timer(0.05, bs.WeakCall(self._track), repeat=True)

    def _set_text(self, text: str, color: tuple[float, float, float]) -> None:
        if self._text:
            self._text.text = text
            self._text.color = color

    def _start_round(self) -> None:
        if self._done or self._ended:
            return
        self._round += 1
        self._cmd = random.choice(['still', 'move', 'jump'])
        self._simon = random.random() < 0.65
        label = {'still': 'STAND STILL', 'move': 'KEEP MOVING',
                 'jump': 'JUMP'}[self._cmd]
        if self._simon:
            self._set_text(f'Simon says: {label}!', (0.3, 1.0, 0.3))
        else:
            self._set_text(f'{label}!', (1.0, 0.4, 0.3))
        for p in self.players:
            p.max_speed = 0.0
            p.jumped = False
        now = bs.time()
        self._track_from = now + 0.8
        self._open = True
        window = max(2.2, self._base_window - 0.1 * self._round)
        bs.timer(window, bs.WeakCall(self._evaluate))

    def _track(self) -> None:
        if not self._open or bs.time() < self._track_from:
            return
        for p in self.players:
            if p.eliminated:
                continue
            node = getattr(p.actor, 'node', None)
            if not node:
                continue
            vel = node.velocity
            speed = math.sqrt(vel[0] ** 2 + vel[2] ** 2)
            p.max_speed = max(p.max_speed, speed)
            if vel[1] > 3.5:
                p.jumped = True

    def _evaluate(self) -> None:
        self._open = False
        if self._done or self._ended:
            return
        for p in self.players:
            if p.eliminated or _pos(p) is None:
                continue
            if self._cmd == 'still':
                performed = p.max_speed < 1.2
            elif self._cmd == 'move':
                performed = p.max_speed > 2.5
            else:
                performed = p.jumped
            correct = performed if self._simon else not performed
            if not correct:
                _blast_kill(p)
        self._set_text('...', (1.0, 1.0, 1.0))
        bs.timer(1.8, bs.WeakCall(self._start_round))


# ===========================================================================
# 5/6) PAD GAMES: COLOR MATCH + MEMORY GAME
# ===========================================================================
class _PadGame(_SurvivalGame):
    COLORS = [
        ('RED', (1.0, 0.15, 0.15)),
        ('GREEN', (0.15, 1.0, 0.15)),
        ('BLUE', (0.25, 0.45, 1.0)),
        ('YELLOW', (1.0, 1.0, 0.15)),
    ]

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.FloatChoiceSetting(
                'Difficulty',
                choices=[('Easy', 5.0), ('Normal', 4.0), ('Hard', 3.0)],
                default=4.0,
            ),
            _time_setting(0),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._base_time = float(settings['Difficulty'])
        self._pads: list[dict[str, Any]] = []
        self._text: bs.Node | None = None
        self._round = 0
        self._answer = 0

    def on_begin(self) -> None:
        super().on_begin()
        pts = _far_points(_ground_points(self), 4)
        for (name, color), pt in zip(self.COLORS, pts):
            flag = Flag(
                position=(pt[0], pt[1] + 0.3, pt[2]),
                touchable=False,
                color=color,
            )
            light = bs.newnode(
                'light',
                attrs={'color': color, 'radius': 1.6, 'intensity': 1.0,
                       'position': (pt[0], pt[1] + 0.4, pt[2])},
            )
            self._pads.append(
                {'pos': pt, 'name': name, 'color': color, 'flag': flag,
                 'light': light}
            )
        self._text = _make_text('Get ready...', (1.0, 1.0, 0.3))
        bs.timer(4.0, bs.WeakCall(self._start_round))

    def _set_text(self, text: str, color: tuple[float, float, float]) -> None:
        if self._text:
            self._text.text = text
            self._text.color = color

    def _flash(self, idx: int) -> None:
        light = self._pads[idx]['light']
        if light:
            bs.animate(
                light, 'intensity', {0: 1.0, 0.2: 5.0, 0.6: 1.0}
            )

    def _pad_at(self, pos: Sequence[float]) -> int | None:
        best = None
        best_d = 2.4
        for i, pad in enumerate(self._pads):
            d = _hdist(pos, pad['pos'])
            if d < best_d:
                best, best_d = i, d
        return best

    def _judge(self) -> None:
        for p in self.players:
            if p.eliminated:
                continue
            pos = _pos(p)
            if pos is None:
                continue
            if self._pad_at(pos) != self._answer:
                _blast_kill(p)

    def _finish_round(self) -> None:
        if self._done or self._ended:
            return
        self._judge()
        self._set_text('...', (1.0, 1.0, 1.0))
        bs.timer(2.0, bs.WeakCall(self._start_round))

    def _start_round(self) -> None:
        raise NotImplementedError


# ba_meta export bascenev1.GameActivity
class ColorMatchGame(_PadGame):
    name = 'Color Match BY EXTRAX8'
    description = 'Run to the colored pad that is called. Others explode!'

    def _start_round(self) -> None:
        if self._done or self._ended:
            return
        self._round += 1
        self._answer = random.randrange(len(self._pads))
        name, color = self.COLORS[self._answer]
        self._set_text(f'STAND ON {name}!', color)
        self._flash(self._answer)
        t = max(1.4, self._base_time - 0.12 * self._round)
        bs.timer(t, bs.WeakCall(self._finish_round))


# ba_meta export bascenev1.GameActivity
class MemoryGameGame(_PadGame):
    name = 'Memory Game BY EXTRAX8'
    description = 'Memorize the pad sequence, then stand on the one asked!'

    def _start_round(self) -> None:
        if self._done or self._ended:
            return
        self._round += 1
        length = min(2 + self._round // 2, 6)
        seq = [random.randrange(len(self._pads)) for _ in range(length)]
        self._set_text('WATCH THE PADS!', (1.0, 1.0, 1.0))
        for k, idx in enumerate(seq):
            bs.timer(1.0 + k * 1.0, bs.WeakCall(self._show_step, idx))
        bs.timer(1.0 + length * 1.0 + 0.5, bs.WeakCall(self._ask, seq))

    def _show_step(self, idx: int) -> None:
        name, color = self.COLORS[idx]
        self._set_text(name, color)
        self._flash(idx)

    def _ask(self, seq: list[int]) -> None:
        if self._done or self._ended:
            return
        i = random.randrange(len(seq))
        self._answer = seq[i]
        self._set_text(f'WHICH PAD WAS #{i + 1}?', (1.0, 1.0, 0.3))
        bs.timer(self._base_time, bs.WeakCall(self._finish_round))


# ===========================================================================
# 7) MUSICAL FLAGS
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class MusicalFlagsGame(_SurvivalGame):
    name = 'Musical Flags BY EXTRAX8'
    description = 'When the music stops, grab a flag. One player too many!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.FloatChoiceSetting(
                'Grab Time',
                choices=[('Easy', 6.0), ('Normal', 4.0), ('Hard', 3.0)],
                default=4.0,
            ),
            _time_setting(0),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._grab_time = float(settings['Grab Time'])
        self._entries: list[dict[str, Any]] = []
        self._claim_open = False
        self._round = 0
        self._text: bs.Node | None = None
        self._tick_timer: bs.Timer | None = None
        self._ding = bs.getsound('dingSmall')

    def on_begin(self) -> None:
        super().on_begin()
        self._text = _make_text('Get ready...', (1.0, 1.0, 0.3))
        bs.timer(4.0, bs.WeakCall(self._start_round))
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)

    def _set_text(self, text: str, color: tuple[float, float, float]) -> None:
        if self._text:
            self._text.text = text
            self._text.color = color

    def _start_round(self) -> None:
        if self._done or self._ended:
            return
        self._round += 1
        for p in self.players:
            p.claimed = False
        self._set_text('MUSIC PLAYING... keep moving!', (0.5, 1.0, 1.0))
        bs.timer(random.uniform(4.0, 9.0), bs.WeakCall(self._music_stop))

    def _music_stop(self) -> None:
        if self._done or self._ended:
            return
        alive = [p for p in self.players if not p.eliminated
                 and _pos(p) is not None]
        count = max(1, len(alive) - 1)
        used: list[Sequence[float]] = []
        for _ in range(count):
            pos = _rand_point(self, avoid=used, min_dist=2.5)
            used.append(pos)
            self._entries.append(
                {'flag': Flag(position=pos, touchable=False,
                              color=(1.0, 1.0, 1.0)),
                 'taken': False}
            )
        self._claim_open = True
        self._set_text('GRAB A FLAG!', (1.0, 0.3, 0.3))
        bs.timer(
            max(2.5, self._grab_time - 0.1 * self._round),
            bs.WeakCall(self._end_round),
        )

    def _tick(self) -> None:
        if not self._claim_open or self._done:
            return
        for p in self.players:
            if p.eliminated or p.claimed:
                continue
            pos = _pos(p)
            if pos is None:
                continue
            for entry in self._entries:
                if entry['taken']:
                    continue
                node = entry['flag'].node
                if node and _hdist(pos, node.position) < 1.4:
                    entry['taken'] = True
                    p.claimed = True
                    entry['flag'].handlemessage(bs.DieMessage())
                    self._ding.play()
                    if p.actor is not None:
                        p.actor.set_score_text('SAFE')  # type: ignore
                    break

    def _end_round(self) -> None:
        self._claim_open = False
        if self._done or self._ended:
            return
        for p in self.players:
            if not p.eliminated and not p.claimed and _pos(p) is not None:
                _blast_kill(p)
        for entry in self._entries:
            if entry['flag'].node:
                entry['flag'].handlemessage(bs.DieMessage())
        self._entries = []
        self._set_text('...', (1.0, 1.0, 1.0))
        bs.timer(2.5, bs.WeakCall(self._start_round))


# ===========================================================================
# 8) EGG GAME
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class EggGame(bs.TeamGameActivity[Player, Team]):
    name = 'Egg Game BY EXTRAX8'
    description = 'Hold the golden egg to score. Touch the holder to steal it!'
    scoreconfig = bs.ScoreConfig(label='Egg Time', scoretype=bs.ScoreType.POINTS)
    allow_mid_activity_joins = False

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Points To Win',
                choices=[('None', 0), ('30', 30), ('60', 60), ('100', 100)],
                default=60,
            ),
            _time_setting(300),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        return _melee_maps()

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._target = int(settings['Points To Win'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.KEEP_AWAY
        )
        self._scoreboard = Scoreboard()
        self._egg: Flag | None = None
        self._holder: Player | None = None
        self._light: bs.Node | None = None
        self._steal_lock = 0.0
        self._tick_timer: bs.Timer | None = None
        self._score_timer: bs.Timer | None = None
        self._done = False
        self._ding = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        self._spawn_egg()
        self._update_scoreboard()
        self._tick_timer = bs.Timer(0.1, bs.WeakCall(self._tick), repeat=True)
        self._score_timer = bs.Timer(
            1.0, bs.WeakCall(self._score_tick), repeat=True
        )

    def _spawn_egg(self) -> None:
        if self._done:
            return
        self._egg = Flag(
            position=_rand_point(self), touchable=False,
            color=(1.0, 0.9, 0.4),
        )

    def _clear_light(self) -> None:
        if self._light:
            self._light.delete()
        self._light = None

    def _set_holder(self, player: Player) -> None:
        self._clear_light()
        self._holder = player
        self._steal_lock = bs.time() + 2.5
        node = getattr(player.actor, 'node', None)
        if node:
            light = bs.newnode(
                'light',
                owner=node,
                attrs={'color': (1.0, 0.9, 0.2), 'radius': 0.3,
                       'intensity': 2.0},
            )
            node.connectattr('position', light, 'position')
            self._light = light
            player.actor.set_score_text('EGG!')  # type: ignore
        self._ding.play()

    def _tick(self) -> None:
        if self._done:
            return
        now = bs.time()
        holder = self._holder
        if holder is not None:
            hpos = _pos(holder)
            if hpos is None:
                self._holder = None
                self._clear_light()
                self._spawn_egg()
                return
            if now < self._steal_lock:
                return
            for p in self.players:
                if p is holder:
                    continue
                pos = _pos(p)
                if pos is not None and _dist(pos, hpos) < 1.3:
                    self._set_holder(p)
                    return
            return
        egg = self._egg
        if egg is None or not egg.node:
            self._egg = None
            self._spawn_egg()
            return
        epos = egg.node.position
        for p in self.players:
            pos = _pos(p)
            if pos is not None and _hdist(pos, epos) < 1.5 and abs(
                pos[1] - epos[1]
            ) < 2.5:
                egg.handlemessage(bs.DieMessage())
                self._egg = None
                self._set_holder(p)
                return

    def _score_tick(self) -> None:
        if self._done or self._holder is None:
            return
        team = self._holder.team
        team.score += 1
        self._update_scoreboard()
        if self._target > 0 and team.score >= self._target:
            self.end_game()

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                self.respawn_player(player)
            return None
        return super().handlemessage(msg)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._target if self._target > 0 else None
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ===========================================================================
# 9) CASTLE QUEEN
# ===========================================================================
# ba_meta export bascenev1.GameActivity
class CastleQueenGame(_SurvivalGame):
    name = 'Castle Queen BY EXTRAX8'
    description = 'Destroy the enemy queens and protect your own!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Queen Health',
                choices=[('Low', 60), ('Normal', 100), ('High', 160)],
                default=100,
            ),
            _time_setting(0),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._hp_max = float(settings['Queen Health'])
        self._tick_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        pts = _far_points(_ground_points(self), len(self.teams))
        for team, pt in zip(self.teams, pts):
            color = tuple(team.color)
            team.queen_pos = pt
            team.queen_hp = self._hp_max
            team.queen_dead = False
            flag = Flag(
                position=(pt[0], pt[1] + 0.3, pt[2]),
                touchable=False,
                color=color,
            )
            light = bs.newnode(
                'light',
                attrs={'color': color, 'radius': 1.2, 'intensity': 1.2,
                       'position': (pt[0], pt[1] + 0.5, pt[2])},
            )
            team.queen_text = bs.newnode(
                'text',
                attrs={
                    'text': str(int(self._hp_max)),
                    'in_world': True,
                    'shadow': 1.0,
                    'flatness': 1.0,
                    'color': color,
                    'scale': 0.03,
                    'h_align': 'center',
                    'position': (pt[0], pt[1] + 2.4, pt[2]),
                },
            )
            team.queen_nodes = [flag, light]
        self._tick_timer = bs.Timer(0.25, bs.WeakCall(self._tick), repeat=True)

    def _on_player_died(self, player: Player) -> None:
        if player.team.queen_dead:
            self._eliminate(player)
        else:
            self.respawn_player(player)

    def _tick(self) -> None:
        if self._done or self._ended:
            return
        dt = 0.25
        for team in self.teams:
            if team.queen_dead:
                continue
            attackers = 0
            defenders = 0
            for p in self.players:
                if p.eliminated:
                    continue
                pos = _pos(p)
                if pos is None or _hdist(pos, team.queen_pos) >= 2.4:
                    continue
                if p.team is team:
                    defenders += 1
                else:
                    attackers += 1
            net = attackers - defenders
            if net > 0:
                team.queen_hp -= 8.0 * net * dt
            elif defenders > 0 and net <= 0:
                team.queen_hp = min(self._hp_max, team.queen_hp + 3.0 * dt)
            if team.queen_text:
                team.queen_text.text = str(max(0, int(team.queen_hp)))
            if team.queen_hp <= 0:
                self._destroy_queen(team)

    def _destroy_queen(self, team: Team) -> None:
        team.queen_dead = True
        Blast(
            position=(team.queen_pos[0], team.queen_pos[1] + 0.5,
                      team.queen_pos[2]),
            velocity=(0, 0, 0),
            blast_radius=2.5,
            blast_type='normal',
            source_player=None,
        ).autoretain()
        for node in team.queen_nodes:
            if isinstance(node, Flag):
                node.handlemessage(bs.DieMessage())
            elif node:
                node.delete()
        team.queen_nodes = []
        if team.queen_text:
            team.queen_text.delete()
        bs.broadcastmessage('A queen has fallen!', color=(1.0, 0.4, 0.2),
                            top=True)
        for p in list(team.players):
            self._eliminate(p)
            _blast_kill(p)


# ===========================================================================
# SOCCER / BASKETBALL / VOLLEYBALL
# ===========================================================================
class Ball(bs.Actor):
    """كرة فيزيائية تتحرك بالضرب."""

    def __init__(
        self, position: Sequence[float], lift: float = 0.0
    ) -> None:
        super().__init__()
        shared = SharedObjects.get()
        self._lift = lift
        self.node = bs.newnode(
            'prop',
            delegate=self,
            attrs={
                'mesh': bs.getmesh('bomb'),
                'color_texture': bs.gettexture('bombColor'),
                'body': 'sphere',
                'body_scale': 1.3,
                'mesh_scale': 1.3,
                'reflection': 'soft',
                'reflection_scale': [0.3],
                'shadow_size': 0.6,
                'is_area_of_interest': True,
                'position': tuple(position),
                'materials': [shared.object_material],
            },
        )
        light = bs.newnode(
            'light',
            owner=self.node,
            attrs={'color': (1.0, 1.0, 1.0), 'radius': 0.3,
                   'intensity': 1.0},
        )
        self.node.connectattr('position', light, 'position')

    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.DieMessage):
            if self.node:
                self.node.delete()
        elif isinstance(msg, bs.OutOfBoundsMessage):
            self.handlemessage(bs.DieMessage())
        elif isinstance(msg, bs.HitMessage):
            if self.node and msg.force_direction is not None:
                fd = msg.force_direction
                self.node.handlemessage(
                    'impulse',
                    msg.pos[0], msg.pos[1], msg.pos[2],
                    msg.velocity[0], msg.velocity[1], msg.velocity[2],
                    1.0 * msg.magnitude, 1.0 * msg.velocity_magnitude,
                    msg.radius, 0,
                    fd[0], fd[1] + self._lift, fd[2],
                )
        else:
            return super().handlemessage(msg)
        return None


# ---------------------------------------------------------------------------
# قاعدة الرياضات
# ---------------------------------------------------------------------------
class _SportsGame(bs.TeamGameActivity[Player, Team]):
    allow_mid_activity_joins = False
    scoreconfig = bs.ScoreConfig(label='Points', scoretype=bs.ScoreType.POINTS)
    LIFT = 0.0
    SERVE_H = 1.0
    POINT_VALUE = 1

    @classmethod
    def supports_session_type(cls, sessiontype: type[bs.Session]) -> bool:
        return _supports(sessiontype)

    MAP_NAME = ''

    @classmethod
    def get_supported_maps(cls, sessiontype: type[bs.Session]) -> list[str]:
        assert bs.app.classic is not None
        try:
            custom = list(bs.app.classic.getmaps('extrax8_sports'))
        except Exception:  # noqa: BLE001
            custom = []
        maps: list[str] = []
        if cls.MAP_NAME and cls.MAP_NAME in custom:
            maps.append(cls.MAP_NAME)
        for extra in ('Football Stadium', 'Hockey Stadium'):
            if extra not in maps:
                maps.append(extra)
        return maps

    @staticmethod
    def _sport_settings(
        win_choices: list[tuple[str, int]], win_default: int
    ) -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Score To Win', choices=win_choices, default=win_default
            ),
            _time_setting(300),
            bs.BoolSetting('Powerups', default=False),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._score_to_win = int(settings['Score To Win'])
        self._time_limit = float(settings['Time Limit'])
        self._powerups = bool(settings['Powerups'])
        self._epic_mode = bool(settings['Epic Mode'])
        self.slow_motion = self._epic_mode
        self.default_music = (
            bs.MusicType.EPIC if self._epic_mode else bs.MusicType.SPORTS
        )
        self._scoreboard = Scoreboard()
        self._ball: Ball | None = None
        self._ball_pt: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._last_touch: Player | None = None
        self._respawning = False
        self._tick_timer: bs.Timer | None = None
        self._done = False
        self._ding = bs.getsound('dingSmall')

    def on_team_join(self, team: Team) -> None:
        if self.has_begun():
            self._update_scoreboard()

    def on_begin(self) -> None:
        super().on_begin()
        self.setup_standard_time_limit(self._time_limit)
        if self._powerups:
            self.setup_standard_powerup_drops()
        pts = _ground_points(self)
        goals = self._pick_goals(pts)
        for team, g in zip(self.teams, goals):
            color = tuple(team.color)
            team.goal_pos = g
            team.goal_nodes = [
                Flag(position=(g[0], g[1] + 0.3, g[2]), touchable=False,
                     color=color),
                bs.newnode(
                    'light',
                    attrs={'color': color, 'radius': 2.0, 'intensity': 1.0,
                           'position': (g[0], g[1] + 0.5, g[2])},
                ),
            ]
            self._extra_goal_visual(team, g)
        mean = _mean(pts)
        cands = [p for p in pts if all(_hdist(p, g) > 0.5 for g in goals)]
        if not cands:
            cands = [mean]
        self._ball_pt = min(cands, key=lambda p: _hdist(p, mean))
        self._update_scoreboard()
        self._spawn_ball(self.SERVE_H)
        self._tick_timer = bs.Timer(0.05, bs.WeakCall(self._tick), repeat=True)

    def _pick_goals(
        self, pts: list[tuple[float, float, float]]
    ) -> list[tuple[float, float, float]]:
        if len(self.teams) == 2:
            try:
                a = self.map.get_start_position(0)
                b = self.map.get_start_position(1)
                ga = (float(a[0]), float(a[1]), float(a[2]))
                gb = (float(b[0]), float(b[1]), float(b[2]))
                if _hdist(ga, gb) > 6.0:
                    return [ga, gb]
            except Exception:  # noqa: BLE001
                pass
        return _far_points(pts, len(self.teams))

    def _extra_goal_visual(
        self, team: Team, g: tuple[float, float, float]
    ) -> None:
        """هوك للألعاب (مثل الحلقة في السلة)."""

    # --- الكرة ---
    def _spawn_ball(self, height: float = 1.0) -> None:
        if self._done:
            return
        self._respawning = False
        pt = self._ball_pt
        self._ball = Ball(
            position=(pt[0], pt[1] + height, pt[2]), lift=self.LIFT
        )
        self._last_touch = None

    def _reset_ball(self, delay: float = 1.5) -> None:
        if self._ball is not None and self._ball.node:
            self._ball.handlemessage(bs.DieMessage())
        self._ball = None
        if not self._respawning:
            self._respawning = True
            bs.timer(delay, bs.WeakCall(self._spawn_ball, self.SERVE_H))

    def _tick(self) -> None:
        if self._done:
            return
        ball = self._ball
        if ball is None or not ball.node:
            self._ball = None
            if not self._respawning:
                self._reset_ball(1.0)
            return
        bpos = ball.node.position
        best = None
        best_d = 1.9
        for p in self.players:
            pos = _pos(p)
            if pos is None:
                continue
            d = _dist(pos, bpos)
            if d < best_d:
                best, best_d = p, d
        if best is not None:
            self._last_touch = best
        self._check_score(bpos)

    def _check_score(self, bpos: Sequence[float]) -> None:
        raise NotImplementedError

    def _after_score(self, text: str) -> None:
        self._ding.play()
        bs.broadcastmessage(text, color=(1.0, 1.0, 0.3), top=True)
        self._update_scoreboard()
        self._reset_ball(1.5)
        if any(t.score >= self._score_to_win for t in self.teams):
            self.end_game()

    # --- عام ---
    def handlemessage(self, msg: Any) -> Any:
        if isinstance(msg, bs.PlayerDiedMessage):
            super().handlemessage(msg)
            player = msg.getplayer(Player)
            if player is not None:
                self.respawn_player(player)
            return None
        return super().handlemessage(msg)

    def _update_scoreboard(self) -> None:
        for team in self.teams:
            self._scoreboard.set_team_value(
                team, team.score, self._score_to_win
            )

    def end_game(self) -> None:
        if self._done:
            return
        self._done = True
        results = bs.GameResults()
        for team in self.teams:
            results.set_team_score(team, team.score)
        self.end(results=results)


# ba_meta export bascenev1.GameActivity
class SoccerGame(_SportsGame):
    name = 'Soccer BY EXTRAX8'
    MAP_NAME = 'Soccer Field BY EXTRAX8'
    description = 'Hit the ball into the enemy goals. Own goals cost a point!'
    scoreconfig = bs.ScoreConfig(label='Goals', scoretype=bs.ScoreType.POINTS)

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._sport_settings(
            [('3 Goals', 3), ('5 Goals', 5), ('10 Goals', 10)], 5
        )

    def _check_score(self, bpos: Sequence[float]) -> None:
        for team in self.teams:
            g = team.goal_pos
            if _hdist(bpos, g) < 2.6 and bpos[1] < g[1] + 3.0:
                toucher = self._last_touch
                if toucher is None:
                    self._reset_ball(1.0)
                    return
                if toucher.team is team:
                    team.score -= 1
                    self._after_score('Own goal!')
                else:
                    toucher.team.score += 1
                    self._after_score('GOAL!')
                return


# ba_meta export bascenev1.GameActivity
class BasketballGame(_SportsGame):
    name = 'Basketball BY EXTRAX8'
    MAP_NAME = 'Basketball Court BY EXTRAX8'
    description = 'Punch the ball through the enemy hoop (the glowing ring)!'
    scoreconfig = bs.ScoreConfig(label='Points', scoretype=bs.ScoreType.POINTS)
    LIFT = 0.9
    POINT_VALUE = 2
    HOOP_H = 2.2

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._sport_settings(
            [('10 Points', 10), ('20 Points', 20), ('30 Points', 30)], 20
        )

    def _extra_goal_visual(
        self, team: Team, g: tuple[float, float, float]
    ) -> None:
        team.goal_nodes.append(
            bs.newnode(
                'light',
                attrs={
                    'color': tuple(team.color),
                    'radius': 0.6,
                    'intensity': 3.0,
                    'position': (g[0], g[1] + self.HOOP_H, g[2]),
                },
            )
        )

    def _check_score(self, bpos: Sequence[float]) -> None:
        for team in self.teams:
            g = team.goal_pos
            if _hdist(bpos, g) < 1.2 and abs(
                bpos[1] - (g[1] + self.HOOP_H)
            ) < 0.9:
                toucher = self._last_touch
                if toucher is not None and toucher.team is not team:
                    toucher.team.score += self.POINT_VALUE
                    self._after_score('SCORE!')
                else:
                    self._reset_ball(1.0)
                return


# ba_meta export bascenev1.GameActivity
class VolleyballGame(_SportsGame):
    name = 'Volleyball BY EXTRAX8'
    MAP_NAME = 'Volleyball Arena BY EXTRAX8'
    description = 'Keep the ball in the air! If it lands on your side, others score.'
    scoreconfig = bs.ScoreConfig(label='Points', scoretype=bs.ScoreType.POINTS)
    LIFT = 1.0
    SERVE_H = 5.0

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._sport_settings(
            [('5 Points', 5), ('10 Points', 10), ('15 Points', 15)], 10
        )

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._ground_y: float | None = None
        self._min_y = 9999.0
        self._calib_until = 0.0
        self._air = False
        self._ground_since: float | None = None
        self._net: list[bs.Node] = []

    def on_begin(self) -> None:
        super().on_begin()
        self._calib_until = bs.time() + 4.0
        if len(self.teams) == 2:
            a = self.teams[0].goal_pos
            b = self.teams[1].goal_pos
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
            dx, dz = b[0] - a[0], b[2] - a[2]
            ln = math.sqrt(dx * dx + dz * dz) or 1.0
            nx, nz = -dz / ln, dx / ln
            for k in range(-4, 5):
                self._net.append(
                    bs.newnode(
                        'light',
                        attrs={
                            'color': (1.0, 1.0, 1.0),
                            'radius': 0.35,
                            'intensity': 1.2,
                            'position': (mid[0] + nx * k * 1.6, mid[1] + 1.0,
                                         mid[2] + nz * k * 1.6),
                        },
                    )
                )

    def _check_score(self, bpos: Sequence[float]) -> None:
        now = bs.time()
        y = bpos[1]
        if self._ground_y is None:
            self._min_y = min(self._min_y, y)
            if now >= self._calib_until:
                self._ground_y = self._min_y
                self._air = False
                self._ground_since = None
                self._reset_ball(0.5)
            return
        gy = self._ground_y
        if y > gy + 1.6:
            self._air = True
            self._ground_since = None
            return
        landed = False
        if y < gy + 0.3:
            if self._air:
                landed = True
            else:
                if self._ground_since is None:
                    self._ground_since = now
                elif now - self._ground_since > 2.0:
                    landed = True
        else:
            self._ground_since = None
        if not landed:
            return
        self._air = False
        self._ground_since = None
        owner = min(self.teams, key=lambda t: _hdist(bpos, t.goal_pos))
        for team in self.teams:
            if team is not owner:
                team.score += 1
        self._after_score('Point!')


# ===========================================================================
# HUNGER GAMES / SKY WARS
# ===========================================================================
class _RoyaleGame(_SurvivalGame):
    LOOT = ['triple_bombs', 'ice_bombs', 'punch', 'impact_bombs',
            'sticky_bombs', 'shield', 'health', 'land_mines']

    @staticmethod
    def _royale_settings() -> list[bs.Setting]:
        return [
            bs.IntChoiceSetting(
                'Loot Amount',
                choices=[('Low', 8), ('Normal', 14), ('High', 22)],
                default=14,
            ),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._loot_n = int(settings['Loot Amount'])
        self._center: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._spawn_pts: list[tuple[float, float, float]] = []
        self._supply_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        pts = _ground_points(self)
        self._spawn_pts = pts
        mean = _mean(pts)
        self._center = min(pts, key=lambda p: _hdist(p, mean))
        for _ in range(self._loot_n):
            self._drop_box(_rand_point(self))
        self._supply_timer = bs.Timer(
            20.0, bs.WeakCall(self._supply_drop), repeat=True
        )
        self._start_zone()

    @staticmethod
    def _drop_box(pos: Sequence[float], height: float = 0.0) -> None:
        PowerupBox(
            position=(pos[0], pos[1] + height, pos[2]),
            poweruptype=random.choice(_RoyaleGame.LOOT),
            expire=False,
        ).autoretain()

    def _supply_drop(self) -> None:
        if self._done or self._ended:
            return
        for _ in range(3):
            self._drop_box(_rand_point(self), 8.0)
        bs.broadcastmessage('Supply drop incoming!', color=(0.3, 1.0, 0.3),
                            top=True)

    def _alive_positions(self) -> list[Sequence[float]]:
        out = []
        for p in self.players:
            if p.eliminated:
                continue
            pos = _pos(p)
            if pos is not None:
                out.append(pos)
        return out

    def _start_zone(self) -> None:
        raise NotImplementedError


# ba_meta export bascenev1.GameActivity
class HungerGamesGame(_RoyaleGame):
    name = 'Hunger Games BY EXTRAX8'
    description = 'Loot, fight and stay inside the shrinking storm. Last one wins!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._royale_settings() + [
            bs.IntChoiceSetting(
                'Storm Speed',
                choices=[('Slow', 220), ('Normal', 150), ('Fast', 90)],
                default=150,
            ),
            _time_setting(0),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._shrink_seconds = float(settings['Storm Speed'])
        self._r0 = 30.0
        self._radius = 30.0
        self._ring: list[bs.Node] = []
        self._storm_timer: bs.Timer | None = None
        self._warned = False

    def _start_zone(self) -> None:
        c = self._center
        self._r0 = max(_hdist(c, p) for p in self._spawn_pts) + 8.0
        self._radius = self._r0
        for i in range(20):
            self._ring.append(
                bs.newnode(
                    'light',
                    attrs={'color': (1.0, 0.2, 0.2), 'radius': 0.8,
                           'intensity': 1.5,
                           'position': (c[0], c[1] + 0.3, c[2])},
                )
            )
        self._place_ring()
        self._storm_timer = bs.Timer(
            1.0, bs.WeakCall(self._storm_tick), repeat=True
        )

    def _place_ring(self) -> None:
        c = self._center
        n = len(self._ring)
        for i, light in enumerate(self._ring):
            a = 2.0 * math.pi * i / n
            light.position = (
                c[0] + self._radius * math.cos(a),
                c[1] + 0.3,
                c[2] + self._radius * math.sin(a),
            )

    def _storm_tick(self) -> None:
        if self._done or self._ended:
            return
        elapsed = bs.time() - self._start_time
        if elapsed < 25.0:
            return
        if not self._warned:
            self._warned = True
            bs.broadcastmessage('The storm is closing in!',
                                color=(1.0, 0.3, 0.3), top=True)
        frac = min(1.0, (elapsed - 25.0) / self._shrink_seconds)
        self._radius = self._r0 + (3.0 - self._r0) * frac
        self._place_ring()
        for p in self.players:
            if p.eliminated:
                continue
            pos = _pos(p)
            spaz = p.actor
            if pos is None or spaz is None:
                continue
            if _hdist(pos, self._center) > self._radius:
                hp = spaz.hitpoints - 45.0  # type: ignore
                spaz.hitpoints = hp  # type: ignore
                try:
                    spaz.node.hurt = 1.0 - max(0.0, hp) / spaz.hitpoints_max  # type: ignore
                except Exception:  # noqa: BLE001
                    pass
                if hp <= 0:
                    spaz.handlemessage(bs.DieMessage())


# ba_meta export bascenev1.GameActivity
class SkyWarsGame(_RoyaleGame):
    name = 'Sky Wars BY EXTRAX8'
    description = 'Loot up and survive the airstrikes. Last one standing wins!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._royale_settings() + [
            bs.FloatChoiceSetting(
                'Airstrikes',
                choices=[('Low', 4.0), ('Normal', 2.5), ('High', 1.4)],
                default=2.5,
            ),
            _time_setting(0),
            bs.BoolSetting('Epic Mode', default=False),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._interval = float(settings['Airstrikes'])
        self._strike_timer: bs.Timer | None = None

    def _start_zone(self) -> None:
        bs.timer(10.0, bs.WeakCall(self._begin_strikes))

    def _begin_strikes(self) -> None:
        if self._done:
            return
        bs.broadcastmessage('Airstrikes incoming!', color=(1.0, 0.3, 0.3),
                            top=True)
        self._strike_timer = bs.Timer(
            self._interval, bs.WeakCall(self._strike), repeat=True
        )

    def _strike(self) -> None:
        if self._done or self._ended:
            return
        targets = self._alive_positions()
        if not targets:
            return
        count = 1 + int((bs.time() - self._start_time) / 30.0)
        for _ in range(min(count, 5)):
            t = random.choice(targets)
            Bomb(
                position=(
                    t[0] + random.uniform(-3.0, 3.0),
                    t[1] + 12.0,
                    t[2] + random.uniform(-3.0, 3.0),
                ),
                velocity=(0.0, -3.0, 0.0),
                bomb_type=random.choice(['normal', 'normal', 'sticky',
                                         'impact']),
            ).autoretain()


# ===========================================================================
# ULTIMATE LAST STAND
# ===========================================================================
_LOOT = ['triple_bombs', 'ice_bombs', 'punch', 'impact_bombs',
         'sticky_bombs', 'shield', 'health', 'land_mines']


def _bot_cls(name: str, fallback: type) -> type:
    return getattr(_spz, name, fallback)


# ba_meta export bascenev1.GameActivity
class UltimateLastStandGame(_SurvivalGame):
    """موجات بوتات لا تنتهي مع موجات زعماء وإمدادات؛ ابقَ أطول وقت."""

    name = 'Ultimate Last Stand BY EXTRAX8'
    description = 'Survive endless bot waves, boss waves and supply drops!'

    @classmethod
    def get_available_settings(
        cls, sessiontype: type[bs.Session]
    ) -> list[bs.Setting]:
        return cls._survival_settings(3, 0, True) + [
            bs.FloatChoiceSetting(
                'Bot Difficulty',
                choices=[('Easy', 0.7), ('Normal', 1.0), ('Hard', 1.5)],
                default=1.0,
            ),
        ]

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._difficulty = float(settings['Bot Difficulty'])
        self._bots = SpazBotSet()
        self._wave = 0
        self._to_spawn = 0
        self._in_flight = 0
        self._wave_active = False
        self._check_timer: bs.Timer | None = None

    def on_begin(self) -> None:
        super().on_begin()
        self._check_timer = bs.Timer(
            1.0, bs.WeakCall(self._check_wave), repeat=True
        )
        bs.timer(3.0, bs.WeakCall(self._start_wave))

    def _should_end(self, alive: int) -> bool:
        return alive == 0

    def _pick_bot(self, boss: bool) -> type:
        if boss:
            pool: list[type] = [
                _bot_cls('BomberBotProShielded', BomberBot),
                _bot_cls('TriggerBotProShielded', TriggerBotPro),
                _bot_cls('ChargerBotProShielded', ChargerBot),
            ]
        else:
            pool = [BrawlerBotLite]
            if self._wave >= 2:
                pool += [BrawlerBot, BomberBot]
            if self._wave >= 3:
                pool += [ChargerBot, TriggerBot]
            if self._wave >= 5:
                pool += [BrawlerBotPro, TriggerBotPro]
        return random.choice(pool)

    def _drop_box(self) -> None:
        pos = _rand_point(self)
        PowerupBox(
            position=(pos[0], pos[1] + 6.0, pos[2]),
            poweruptype=random.choice(_LOOT),
            expire=True,
        ).autoretain()

    def _start_wave(self) -> None:
        if self._done or self._ended:
            return
        self._wave += 1
        boss = self._wave % 5 == 0
        count = min(int((4 + 2 * self._wave) * self._difficulty), 40)
        if boss:
            count = max(3, count // 3)
        self._to_spawn = count
        self._wave_active = True
        bs.broadcastmessage(
            f'BOSS WAVE {self._wave}!' if boss else f'Wave {self._wave}',
            color=(1.0, 0.3, 0.3) if boss else (1.0, 0.8, 0.2),
            top=True,
        )
        for _ in range(2):
            self._drop_box()
        if self._wave % 3 == 0:
            for p in self.players:
                if not p.eliminated:
                    p.lives += 1
            bs.broadcastmessage('Bonus life for survivors!',
                                color=(0.3, 1.0, 0.3))
        for i in range(count):
            bs.timer(0.8 * i, bs.WeakCall(self._spawn_bot, boss))

    def _spawn_bot(self, boss: bool) -> None:
        if self._done or self._ended:
            return
        self._to_spawn -= 1
        pos = self.map.get_ffa_start_position(self.players)
        pos = (
            pos[0] + random.uniform(-0.8, 0.8),
            pos[1],
            pos[2] + random.uniform(-0.8, 0.8),
        )
        self._in_flight += 1
        self._bots.spawn_bot(
            self._pick_bot(boss),
            pos=pos,
            spawn_time=2.0,
            on_spawn_call=bs.WeakCall(self._on_spawned),
        )

    def _on_spawned(self, bot: Any = None) -> None:
        self._in_flight = max(0, self._in_flight - 1)

    def _check_wave(self) -> None:
        if self._done or self._ended or not self._wave_active:
            return
        if (
            self._to_spawn <= 0
            and self._in_flight <= 0
            and not self._bots.have_living_bots()
        ):
            self._wave_active = False
            bs.broadcastmessage(
                f'Wave {self._wave} cleared!', color=(0.2, 1.0, 0.2)
            )
            bs.timer(4.0, bs.WeakCall(self._start_wave))

    def end_game(self) -> None:
        if not self._done:
            self._bots.final_celebrate()
        super().end_game()
