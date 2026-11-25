"""보스 사이 추격 구간 — 봉인한 직후, 봉인이 깨지기 전에 다음 방으로 달린다.

전투는 서서 조준하고 반응한다. 이 구간은 반대로 계속 움직이며 버티기만 하는 20초다.
  - 조작은 전투와 똑같다: ArenaScene을 상속해 이동·회피·레인 전환 코드를 그대로 쓴다.
    바꿔 끼우는 것은 게이지(없음), 보스(없음 → 흘러오는 위협), 공격(아무 동작 안 함), 그리기
  - 위협은 기존 보스 패턴(내려찍기·충격파·돌진·후려치기)이고 예고 표시도 전투와 같은 함수다.
    발원점은 화면 뒤쪽(카메라 쪽)이라 붉은 줄기가 아래에서 예고 자리로 뻗는다
  - 맞으면 체력 1칸. 0이 되면 이 구간의 처음으로 (보스전으로 돌아가지 않는다)
  - 20초를 버티면 결과·기술 선택 화면을 거쳐 다음 보스전
"""

import math
import random

import pico2d

import arena_scene as arena
from arena_scene import (
    HEIGHT,
    LANES,
    PLAYER_LOGICAL_WIDTH,
    PLAYER_MAX_HEALTH,
    WIDTH,
    ArenaScene,
    draw_column_marker,
    draw_lane_marker,
    draw_range_marker,
    draw_spot_marker,
    lane_point,
    project,
    logical_to_world_x,
)
from boss import PATTERNS, BossAttack, telegraph_duration
from ui_text import draw_text

# 구간 길이(초). 끝까지 버티면 성공
CHASE_DURATION = 20.0
# 위협 간격: 처음 1.2초에서 점점 줄어 마지막 5초는 0.7초
CHASE_INTERVAL_START = 1.2
CHASE_INTERVAL_END = 0.7
CHASE_INTERVAL_RAMP_END = CHASE_DURATION - 5.0
# 첫 위협까지 숨 돌릴 시간
CHASE_FIRST_THREAT = 1.0
# 흘러오는 위협 — 기존 보스 패턴. 레인은 플레이어가 있는 쪽을 노린다.
#   후려치기(폭 440, 회피 무적 무시)는 레인을 바꿔야만 피한다
CHASE_PATTERNS = {"slam": 35, "shockwave": 25, "charge": 25, "backhand": 15}
# 레인 하나를 통째로(또는 거의) 덮는 위협. 둘이 동시에 살아 있으면 양쪽 레인이 다 막혀 피할 수 없어
#   한 번에 하나만 둔다 (고른 패턴이 걸리면 내려찍기·돌진 중에서 다시 고른다)
CHASE_LANE_BLOCKERS = ("shockwave", "backhand")
# 예고 시간 페이즈 배율 — 전투 1페이즈와 같은 값(1.15)이라 같은 패턴은 같은 빠르기로 온다
CHASE_TELEGRAPH_PHASE = 1
# 성공 후 문 너머로 하얗게 사라지는 시간
CHASE_EXIT_FADE = 0.8
# 바닥이 흘러가는 빠르기 (깊이 역수 단위/초) — 원근 바닥 줄과 벽 기둥이 카메라 쪽으로 지나간다
CHASE_FLOW_SPEED = 1.6
CHASE_FLOW_SPACING = 0.09
CHASE_PILLAR_SPACING = 0.55
# 뒤에서 번지는 붉은 빛 (깨지는 봉인). 시간이 갈수록 화면 아래에서 차오른다
CHASE_RED_RGB = (210, 34, 44)


class ChaseScene(ArenaScene):
    def __init__(self, scene_manager=None, run_state=None, record=None,
                 entry_health=PLAYER_MAX_HEALTH):
        super().__init__(scene_manager, run_state, boss_id=1)
        self.record = record
        # 이 구간을 시작할 때의 체력 (전투에서 남은 만큼). 다시 시작하면 이 값으로 돌아간다
        self.entry_health = max(1, min(entry_health, PLAYER_MAX_HEALTH))
        self.threat_rng = random.Random()
        self.chase_restarts = 0
        self.reset_chase()

    # --- 구간 상태 -----------------------------------------------------------
    def reset_chase(self):
        self.chase_elapsed = 0.0
        self.spawn_timer = CHASE_FIRST_THREAT
        self.threats = []
        self.chase_done = False
        self.exit_elapsed = 0.0
        self.player_health = self.entry_health
        self.player_lane = "platform_2"
        self.player_logical_x = PLAYER_LOGICAL_WIDTH / 2
        self.pressed_keys.clear()
        self.dodge_direction = 0
        self.dodge_elapsed = 0.0
        self.dodge_cooldown = 0.0
        self.invulnerability_timer = 0.0
        self.attack_type = None
        self.lane_transition_target = None
        self.lane_transition_elapsed = 0.0
        self.lane_switch_cooldown = 0.0
        self.momentum = 0

    def remaining(self):
        return max(0.0, CHASE_DURATION - self.chase_elapsed)

    def spawn_interval(self):
        t = min(self.chase_elapsed / CHASE_INTERVAL_RAMP_END, 1.0)
        return CHASE_INTERVAL_START + (CHASE_INTERVAL_END - CHASE_INTERVAL_START) * t

    # --- 전투에서 바꿔 끼우는 것 ------------------------------------------------
    def start_attack(self, attack_type):
        """공격 버튼은 아무 동작도 하지 않는다 (게이지도 보스도 없다)."""

    def update_gauge(self, fixed_delta):
        """게이지 없음."""

    def debug_skip(self):
        if not self.chase_done:
            self.chase_elapsed = CHASE_DURATION

    def update_player_animation(self, moved):
        # 계속 앞으로 달리는 중이므로 좌우로 안 움직여도 달리기 동작을 유지한다.
        # 레인 전환 도약은 전투와 같은 동작
        if self.lane_transition_target is not None:
            super().update_player_animation(moved)
            return
        if self.player_animation != "run":
            self.run_skip_intro = self.player_animation != "idle"
            self.set_player_animation("run")

    def update_encounter(self, fixed_delta):
        if self.chase_done:
            self.exit_elapsed += fixed_delta
            if self.exit_elapsed >= CHASE_EXIT_FADE:
                self.finish_chase()
            return

        self.chase_elapsed += fixed_delta
        self.spawn_timer -= fixed_delta
        if self.spawn_timer <= 1e-9:
            self.spawn_threat()
            self.spawn_timer += self.spawn_interval()

        alive = []
        for threat in self.threats:
            threat["elapsed"] += fixed_delta
            if not threat["landed"] and threat["elapsed"] >= threat["telegraph"]:
                threat["landed"] = True
                self.land_threat(threat)
            if threat["elapsed"] < threat["telegraph"] + threat["duration"]:
                alive.append(threat)
        self.threats = alive

        if self.player_health <= 0:
            # 이 구간의 처음으로 — 보스전으로는 돌아가지 않는다
            self.chase_restarts += 1
            self.reset_chase()
        elif self.chase_elapsed >= CHASE_DURATION:
            self.chase_done = True
            self.threats = []

    # --- 위협 ------------------------------------------------------------------
    def spawn_threat(self):
        names = list(CHASE_PATTERNS)
        weights = [CHASE_PATTERNS[name] for name in names]
        pattern = self.threat_rng.choices(names, weights=weights, k=1)[0]
        blocker_alive = any(
            t["pattern"] in CHASE_LANE_BLOCKERS and not t["landed"] for t in self.threats
        )
        if pattern in CHASE_LANE_BLOCKERS and blocker_alive:
            pattern = self.threat_rng.choice(("slam", "charge"))
        info = PATTERNS[pattern]
        lane = self.lane_transition_target or self.player_lane
        self.threats.append(
            {
                "pattern": pattern,
                "kind": info["kind"],
                "marker": info["marker"],
                "lane": lane,
                "x": self.player_logical_x,
                "width": info["hitbox_width"],
                "telegraph": telegraph_duration(pattern, CHASE_TELEGRAPH_PHASE),
                "duration": info["duration"],
                "elapsed": 0.0,
                "landed": False,
            }
        )

    def land_threat(self, threat):
        shake_strength, shake_duration = PATTERNS[threat["pattern"]]["shake"]
        self.trigger_screen_shake(shake_strength, shake_duration)
        self.trigger_impact_flash(*lane_point(threat["lane"], threat["x"]))
        # 판정은 전투와 같은 함수 (후려치기는 회피 무적이 안 통하는 것까지 같다)
        self.resolve_boss_attack(
            BossAttack(
                pattern=threat["pattern"],
                kind=threat["kind"],
                target_lane=threat["lane"],
                target_x=threat["x"],
                hitbox_width=threat["width"],
            )
        )

    def threat_visible(self, threat):
        """전투와 같은 깜빡임 (예고 시간에 맞춰 줄인 간격)."""
        intervals = PATTERNS[threat["pattern"]]["telegraph_blink"]
        ratio = threat["telegraph"] / PATTERNS[threat["pattern"]]["telegraph"]
        elapsed = threat["elapsed"]
        for index, interval in enumerate(intervals):
            interval *= ratio
            if elapsed < interval:
                return index == len(intervals) - 1 or index % 2 == 1
            elapsed -= interval
        return True

    def threat_range(self, threat):
        half = (threat["width"] or 0) * 0.5
        return max(0, threat["x"] - half), min(PLAYER_LOGICAL_WIDTH, threat["x"] + half)

    # --- 끝 ------------------------------------------------------------------
    def finish_chase(self):
        if self.battle_finished:
            return
        self.battle_finished = True
        if self.scene_manager is None or self.run_state is None or self.record is None:
            self.quit_requested = True
            return
        from interlude_scene import InterludeScene

        self.scene_manager.change_scene(
            InterludeScene(self.scene_manager, self.run_state, self.record)
        )

    # --- 그리기 ----------------------------------------------------------------
    def draw(self):
        self.apply_view_zoom()
        if self.screen_shake_timer > 0 and self.screen_shake_duration > 0:
            shake_scale = self.screen_shake_timer / self.screen_shake_duration
            sign = -1 if self.screen_shake_frame % 2 else 1
            arena.DRAW_OFFSET_X = round(self.screen_shake_strength * shake_scale * sign)
            arena.DRAW_OFFSET_Y = round(self.screen_shake_strength * 0.35 * shake_scale * -sign)
        else:
            arena.DRAW_OFFSET_X = arena.DRAW_OFFSET_Y = 0

        flow = self.chase_elapsed * CHASE_FLOW_SPEED
        arena.draw_void()
        arena.draw_room(with_floor=False)
        self.draw_flowing_pillars(flow)
        arena.draw_back_fog()
        self.draw_exit_door()
        arena.draw_lane("platform_1", "front_lane", "front_edge", 8)
        arena.draw_lane("platform_2", "rear_lane", "rear_edge", 10)
        self.draw_floor_flow(flow)
        self.draw_red_light()
        for threat in self.threats:
            if not threat["landed"]:
                self.draw_threat(threat)
        self.draw_impact_flash()

        lane = LANES[self.player_lane]
        player_scale = lane["scale"]
        player_elevation = lane["elevation"]
        if self.lane_transition_target is not None:
            target = LANES[self.lane_transition_target]
            progress = min(self.lane_transition_elapsed / arena.LANE_SWITCH_DURATION, 1.0)
            player_scale += (target["scale"] - player_scale) * progress
            player_elevation += (target["elevation"] - player_elevation) * progress
        screen_x, player_y = project(
            logical_to_world_x(self.player_logical_x), player_scale, player_elevation
        )
        self.draw_player(screen_x, player_y, player_scale * arena.view_zoom)
        self.draw_player_health()
        arena.DRAW_OFFSET_X = arena.DRAW_OFFSET_Y = 0
        self.draw_chase_hud()
        if self.chase_done:
            # 문 너머로 — 하얗게 사라진다
            alpha = round(255 * min(self.exit_elapsed / CHASE_EXIT_FADE, 1.0))
            white = (255, 244, 224, alpha)
            arena.draw_polygon(((0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT)), [white] * 4)

    def draw_flowing_pillars(self, flow):
        """벽 기둥이 카메라 쪽으로 지나간다 — 깊이 역수(1/s) 공간에서 같은 간격으로 흘린다."""
        near_u, far_u = 1.0 / 1.05, 1.0 / 0.42
        span = far_u - near_u
        offset = (flow % CHASE_PILLAR_SPACING)
        depths = []
        u = far_u - offset
        while u > near_u:
            depths.append(1.0 / u)
            u -= CHASE_PILLAR_SPACING
        saved = arena.PILLAR_DEPTHS
        arena.PILLAR_DEPTHS = tuple(sorted(depths))
        try:
            arena.draw_pillars(with_floor=False)
        finally:
            arena.PILLAR_DEPTHS = saved

    def draw_floor_flow(self, flow):
        """레인 윗면을 가로지르는 줄이 앞으로 흘러와 속도감을 준다."""
        for lane_name, rgb in (("platform_1", (255, 150, 100)), ("platform_2", (110, 180, 255))):
            lane = LANES[lane_name]
            near_u, far_u = 1.0 / lane["near"], 1.0 / lane["far"]
            u = far_u - (flow % CHASE_FLOW_SPACING)
            left, right = logical_to_world_x(0), logical_to_world_x(PLAYER_LOGICAL_WIDTH)
            while u > near_u:
                depth = 1.0 / u
                t = (u - near_u) / (far_u - near_u)  # 멀수록 흐리게
                arena.set_draw_rgb(*rgb, round(150 * (1.0 - t)))
                arena.draw_line(
                    *project(left, depth, lane["elevation"]),
                    *project(right, depth, lane["elevation"]),
                )
                u -= CHASE_FLOW_SPACING

    def draw_exit_door(self):
        """앞쪽(소실점) 다음 방의 문 — 남은 거리만큼 커진다."""
        progress = min(self.chase_elapsed / CHASE_DURATION, 1.0)
        cx = arena.wall_center_x()
        cy = arena.VANISHING_Y - arena.CAMERA_HEIGHT * arena.BACK_WALL_DEPTH
        half_w = (18 + 70 * progress) * arena.view_zoom
        height = (40 + 170 * progress) * arena.view_zoom
        x0, y0 = arena.zoom_point(cx, cy)
        arena.draw_radial_glow(x0, y0 + height * 0.5, half_w * 3.0, height * 0.9,
                               (255, 236, 200), round(40 + 90 * progress))
        light = (255, 240, 214, 230)
        arena.draw_polygon(
            ((x0 - half_w, y0), (x0 + half_w, y0), (x0 + half_w, y0 + height), (x0 - half_w, y0 + height)),
            [light] * 4,
        )

    def draw_red_light(self):
        """뒤(화면 아래, 카메라 쪽)에서 번지는 붉은 빛 — 시간이 갈수록 차오른다."""
        progress = min(self.chase_elapsed / CHASE_DURATION, 1.0)
        pulse = 0.5 + 0.5 * math.sin(self.chase_elapsed * 6.0)
        top = 60 + 230 * progress + 14 * pulse
        r, g, b = CHASE_RED_RGB
        bottom = (r, g, b, round(120 + 80 * progress))
        clear = (r, g, b, 0)
        arena.draw_polygon(((0, 0), (WIDTH, 0), (WIDTH, top), (0, top)), [bottom, bottom, clear, clear])

    def draw_threat(self, threat):
        visible = self.threat_visible(threat)
        progress = min(threat["elapsed"] / threat["telegraph"], 1.0)
        marker = threat["marker"]
        # 발원점: 화면 뒤쪽(아래)에서 예고 자리로 뻗는 붉은 줄기
        tx, ty = lane_point(threat["lane"], threat["x"])
        r, g, b = CHASE_RED_RGB
        arena.draw_polygon(
            ((tx - 26, 0), (tx + 26, 0), (tx + 3, ty), (tx - 3, ty)),
            [(r, g, b, round(40 + 110 * progress))] * 2 + [(r, g, b, 0)] * 2,
        )
        if marker == "lane":
            draw_lane_marker(threat["lane"], visible)
        elif marker == "sweep":
            draw_range_marker(threat["lane"], *self.threat_range(threat), visible)
        elif marker == "column":
            draw_column_marker(*self.threat_range(threat), visible)
        else:
            draw_spot_marker(threat["lane"], threat["x"], visible, progress)

    def draw_chase_hud(self):
        """상단: 남은 거리 막대 (게이지 자리). 다시 시작한 횟수."""
        progress = min(self.chase_elapsed / CHASE_DURATION, 1.0)
        left, right, bottom, top = 360, 920, 656, 672
        arena.set_draw_rgb(10, 12, 16, 220)
        arena.draw_filled_rectangle(left, bottom, right, top)
        arena.set_draw_rgb(255, 236, 200, 255)
        arena.draw_filled_rectangle(left, bottom, left + (right - left) * progress, top)
        arena.set_draw_rgb(120, 126, 140, 255)
        arena.draw_rectangle(left, bottom, right, top)
        draw_text(WIDTH / 2, 692, "봉인이 깨지기 전에 다음 방으로", 18, (240, 230, 215), align="center")
        draw_text(right + 12, 664, f"{self.remaining():4.1f}s", 16, (240, 230, 215))
        if self.chase_restarts:
            draw_text(left, 636, f"다시 시작 {self.chase_restarts}회", 15, (200, 120, 120))
