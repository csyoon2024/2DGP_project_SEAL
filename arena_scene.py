import os
import random

import pico2d

from seal_gauge import SealGauge
from pico2d import (
    draw_circle as pico_draw_circle,
    draw_line as pico_draw_line,
    draw_rectangle as pico_draw_rectangle,
)
from boss import BossAttack, BossController, PATTERNS, PHASE_PATTERNS


WIDTH = 1280
HEIGHT = 720

COLORS = {
    "background": (17, 22, 23),
    "wall": (27, 35, 35),
    "wall_light": (43, 53, 49),
    "floor": (31, 39, 38),
    "floor_line": (52, 62, 57),
    "rear_lane": (37, 61, 58),
    "rear_edge": (101, 151, 129),
    "front_lane": (54, 68, 58),
    "front_edge": (177, 190, 130),
    "accent": (235, 119, 86),
    "accent_light": (255, 195, 126),
    "actor_dark": (18, 24, 25),
    "actor": (225, 112, 78),
    "actor_light": (247, 211, 165),
    "shadow": (20, 27, 26),
}

LANES = {
    "platform_2": {
        "left": 0,
        "right": WIDTH,
        "bottom": 0,
        "top": 120,
        "center_y": 60,
        "scale": 1.0,
    },
    "platform_1": {
        "left": WIDTH // 20,
        "right": WIDTH - WIDTH // 20,
        "bottom": 195,
        "top": 285,
        "center_y": 240,
        "scale": 0.71,
    },
}

PLAYER_SPEED = 320
PLAYER_LOGICAL_WIDTH = 900
PLAYER_X_MIN = 25
PLAYER_X_MAX = PLAYER_LOGICAL_WIDTH - PLAYER_X_MIN
LANE_SWITCH_DURATION = 0.25
LANE_SWITCH_COOLDOWN = 0.6
DODGE_DURATION = 0.35
DODGE_DISTANCE = 160
DODGE_INVULNERABLE_DURATION = 0.2
DODGE_COOLDOWN = 0.5
BOSS_LOGICAL_X = PLAYER_LOGICAL_WIDTH / 2
BOSS_HITBOX_HALF_WIDTH = 35
BASIC_ATTACK_DURATION = 0.25
BASIC_ATTACK_REACH = 120
HEAVY_ATTACK_DURATION = 0.70
PLAYER_MAX_HEALTH = 3
DEBUG_GAUGE_STEP = 0.05


def set_draw_color(name):
    global active_color
    active_color = COLORS[name]


def draw_filled_circle(x, y, radius):
    pico_draw_circle(
        int(round(x)),
        int(round(y)),
        max(1, int(round(radius))),
        *active_color,
        filled=True,
    )


def draw_filled_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left)),
        int(round(bottom)),
        int(round(right)),
        int(round(top)),
        *active_color,
        filled=True,
    )


def draw_line(x1, y1, x2, y2):
    pico_draw_line(
        int(round(x1)),
        int(round(y1)),
        int(round(x2)),
        int(round(y2)),
        *active_color,
    )


def draw_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left)),
        int(round(bottom)),
        int(round(right)),
        int(round(top)),
        *active_color,
    )


def draw_room():
    set_draw_color("background")
    draw_filled_rectangle(0, 0, WIDTH, HEIGHT)

    set_draw_color("wall")
    draw_filled_rectangle(0, 430, WIDTH, HEIGHT)

    set_draw_color("wall_light")
    draw_line(0, 430, WIDTH, 430)
    draw_line(0, 610, WIDTH, 610)
    for panel_x in range(80, WIDTH, 160):
        draw_line(panel_x, 475, panel_x, 700)

    set_draw_color("floor")
    draw_filled_rectangle(0, 0, WIDTH, 430)

    set_draw_color("floor_line")
    for floor_y in (35, 430):
        draw_line(0, floor_y, WIDTH, floor_y)
    for floor_x in range(0, WIDTH + 1, 160):
        draw_line(floor_x, 0, floor_x, 430)

    set_draw_color("wall_light")
    draw_rectangle(112, 0, 1168, 602)
    draw_line(112, 404, 1168, 404)


def draw_lane(lane, fill_color, edge_color, tick_count):
    left = lane["left"]
    right = lane["right"]
    bottom = lane["bottom"]
    top = lane["top"]
    center_y = lane["center_y"]

    set_draw_color(fill_color)
    draw_filled_rectangle(left, bottom, right, top)

    set_draw_color(edge_color)
    draw_rectangle(left, bottom, right, top)
    draw_line(left, center_y, right, center_y)

    tick_step = (right - left) / tick_count
    for tick in range(1, tick_count):
        tick_x = left + tick * tick_step
        draw_line(tick_x, bottom + 12, tick_x, top - 12)

    marker_radius = max(3, int(5 * lane["scale"]))
    for marker_x in (left + 18, right - 18):
        draw_filled_circle(marker_x, center_y, marker_radius)


def draw_perspective_rails():
    platform_2 = LANES["platform_2"]
    platform_1 = LANES["platform_1"]

    set_draw_color("wall_light")
    draw_line(
        platform_2["left"],
        platform_2["bottom"],
        platform_1["left"],
        platform_1["bottom"],
    )
    draw_line(
        platform_2["right"],
        platform_2["bottom"],
        platform_1["right"],
        platform_1["bottom"],
    )

    set_draw_color("floor_line")
    draw_line(
        platform_2["left"],
        platform_2["top"],
        platform_1["left"],
        platform_1["top"],
    )
    draw_line(
        platform_2["right"],
        platform_2["top"],
        platform_1["right"],
        platform_1["top"],
    )


def draw_boss_marker(hit=False):
    set_draw_color("actor_dark")
    draw_filled_circle(640, 480, 38)
    set_draw_color("accent_light" if hit else "accent")
    draw_filled_circle(640, 480, 28)
    set_draw_color("actor_dark")
    draw_filled_circle(640, 480, 20)
    set_draw_color("accent_light")
    draw_line(640, 449, 640, 511)
    draw_line(609, 480, 671, 480)
    draw_filled_circle(640, 480, 5)


def draw_boss_placeholder(awakened=False, hit=False, defeated=False):
    scale = BossController.AWAKENING_SIZE_SCALE if awakened else 1.0
    foot_y = 400 if awakened else 480
    body_half_width = 42 * scale
    body_bottom = foot_y + 34 * scale
    body_top = foot_y + 142 * scale
    head_y = foot_y + 166 * scale

    set_draw_color("shadow")
    draw_filled_rectangle(640 - 55 * scale, 470, 640 + 55 * scale, 482)

    body_color = "actor_light" if hit else ("wall_light" if defeated else "accent")
    set_draw_color("actor_dark")
    draw_filled_rectangle(
        640 - body_half_width - 8 * scale,
        body_bottom - 8 * scale,
        640 + body_half_width + 8 * scale,
        body_top + 8 * scale,
    )
    draw_filled_circle(640, head_y, 34 * scale)

    set_draw_color(body_color)
    draw_filled_rectangle(
        640 - body_half_width,
        body_bottom,
        640 + body_half_width,
        body_top,
    )
    draw_filled_circle(640, head_y, 27 * scale)

    set_draw_color("actor_dark")
    draw_line(640 - 30 * scale, head_y + 18 * scale, 640 - 48 * scale, head_y + 48 * scale)
    draw_line(640 + 30 * scale, head_y + 18 * scale, 640 + 48 * scale, head_y + 48 * scale)
    draw_line(640 - body_half_width, body_top - 8 * scale, 640 - 72 * scale, foot_y + 88 * scale)
    draw_line(640 + body_half_width, body_top - 8 * scale, 640 + 72 * scale, foot_y + 88 * scale)
    draw_line(640 - 20 * scale, body_bottom, 640 - 28 * scale, foot_y)
    draw_line(640 + 20 * scale, body_bottom, 640 + 28 * scale, foot_y)

    set_draw_color("accent_light")
    draw_filled_circle(640 - 10 * scale, head_y, 4 * scale)
    draw_filled_circle(640 + 10 * scale, head_y, 4 * scale)


def draw_player_placeholder(screen_x, foot_y, scale):
    head_radius = 12 * scale
    body_half_width = 13 * scale
    body_bottom = foot_y + 17 * scale
    body_top = foot_y + 56 * scale
    shoulder_y = foot_y + 49 * scale

    set_draw_color("shadow")
    draw_filled_circle(screen_x - 17 * scale, foot_y + 3 * scale, 4 * scale)
    draw_filled_rectangle(
        screen_x - 17 * scale,
        foot_y - scale,
        screen_x + 17 * scale,
        foot_y + 7 * scale,
    )
    draw_filled_circle(screen_x + 17 * scale, foot_y + 3 * scale, 4 * scale)

    set_draw_color("actor_dark")
    draw_filled_circle(screen_x, foot_y + 70 * scale, 15 * scale)
    draw_filled_rectangle(
        screen_x - body_half_width - 3 * scale,
        body_bottom - 3 * scale,
        screen_x + body_half_width + 3 * scale,
        body_top + 3 * scale,
    )

    set_draw_color("actor")
    draw_filled_circle(screen_x, foot_y + 70 * scale, head_radius)
    draw_filled_rectangle(
        screen_x - body_half_width,
        body_bottom,
        screen_x + body_half_width,
        body_top,
    )
    draw_line(
        screen_x - body_half_width,
        shoulder_y,
        screen_x - 22 * scale,
        foot_y + 31 * scale,
    )
    draw_line(
        screen_x + body_half_width,
        shoulder_y,
        screen_x + 22 * scale,
        foot_y + 31 * scale,
    )

    set_draw_color("actor_light")
    draw_filled_circle(screen_x, foot_y + 70 * scale, 5 * scale)
    draw_line(
        screen_x - 7 * scale,
        foot_y + 18 * scale,
        screen_x - 10 * scale,
        foot_y + 2 * scale,
    )
    draw_line(
        screen_x + 7 * scale,
        foot_y + 18 * scale,
        screen_x + 10 * scale,
        foot_y + 2 * scale,
    )


class ArenaScene:
    def __init__(self):
        self.player_lane = "platform_1"
        self.player_logical_x = 240
        self.pressed_keys = set()
        self.lane_switch_cooldown = 0.0
        self.lane_transition_target = None
        self.lane_transition_elapsed = 0.0
        self.facing_direction = 1
        self.dodge_direction = 0
        self.dodge_elapsed = 0.0
        self.dodge_cooldown = 0.0
        self.invulnerability_timer = 0.0
        self.attack_type = None
        self.attack_elapsed = 0.0
        self.attack_hit_registered = False
        self.successful_hits = 0
        self.boss_hit_timer = 0.0
        self.player_health = PLAYER_MAX_HEALTH
        self.seal_gauge = SealGauge()
        self.boss = BossController()
        self.boss_phase = 1
        self.boss_defeated = False
        self.debug_panel_visible = False
        self.debug_hitboxes_visible = False
        self.debug_invulnerability_enabled = False
        self.debug_phase = 1
        self.debug_phase_jump_request = None
        self.debug_seal_gauge = 0.5
        self.debug_forced_pattern = None
        self.debug_pattern_seed_fixed = False
        self.debug_pattern_seed = 1
        self.debug_pattern_rng = random.Random()
        self.debug_font = None

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_event(self, event):
        if event.type == pico2d.SDL_KEYDOWN:
            self.pressed_keys.add(event.key)
            if event.key == pico2d.SDLK_F1:
                self.debug_panel_visible = not self.debug_panel_visible
            elif event.key == pico2d.SDLK_F2:
                self.debug_hitboxes_visible = not self.debug_hitboxes_visible
            elif event.key == pico2d.SDLK_F3:
                self.debug_invulnerability_enabled = (
                    not self.debug_invulnerability_enabled
                )
            elif event.key == pico2d.SDLK_F4:
                self.reset_player()
            elif event.key == pico2d.SDLK_F5:
                self.debug_phase = 2 if self.debug_phase == 1 else 1
                self.debug_phase_jump_request = self.debug_phase
            elif event.key == pico2d.SDLK_LEFTBRACKET:
                self.seal_gauge.set_debug_value(
                    self.seal_gauge.value - DEBUG_GAUGE_STEP
                )
            elif event.key == pico2d.SDLK_RIGHTBRACKET:
                self.seal_gauge.set_debug_value(
                    self.seal_gauge.value + DEBUG_GAUGE_STEP
                )
            elif event.key == pico2d.SDLK_F6:
                available_patterns = tuple(PHASE_PATTERNS[self.boss_phase])
                pattern_index = (
                    available_patterns.index(self.debug_forced_pattern) + 1
                    if self.debug_forced_pattern in available_patterns
                    else 0
                )
                self.debug_forced_pattern = available_patterns[
                    pattern_index % len(available_patterns)
                ]
            elif event.key == pico2d.SDLK_F7:
                self.debug_pattern_seed_fixed = not self.debug_pattern_seed_fixed
                self.debug_pattern_rng = random.Random(
                    self.debug_pattern_seed if self.debug_pattern_seed_fixed else None
                )
            elif event.key == pico2d.SDLK_h and self.debug_panel_visible:
                self.receive_player_hit()
            elif event.key == pico2d.SDLK_SPACE:
                self.start_dodge()
            elif event.key in (pico2d.SDLK_LSHIFT, pico2d.SDLK_RSHIFT):
                target_lane = (
                    "platform_2"
                    if self.player_lane == "platform_1"
                    else "platform_1"
                )
                self.start_lane_transition(target_lane)
            elif event.key == pico2d.SDLK_j:
                self.start_attack("basic")
            elif event.key == pico2d.SDLK_k:
                self.start_attack("heavy")
        elif event.type == pico2d.SDL_KEYUP:
            self.pressed_keys.discard(event.key)

    def start_lane_transition(self, target_lane):
        if self.dodge_direction != 0 or self.attack_type is not None:
            return
        if self.lane_transition_target is not None:
            return
        if self.lane_switch_cooldown > 0 or target_lane == self.player_lane:
            return

        self.lane_transition_target = target_lane
        self.lane_transition_elapsed = 0.0
        self.lane_switch_cooldown = LANE_SWITCH_COOLDOWN

    def reset_player(self):
        self.player_lane = "platform_1"
        self.player_logical_x = 240
        self.pressed_keys.clear()
        self.lane_switch_cooldown = 0.0
        self.lane_transition_target = None
        self.lane_transition_elapsed = 0.0
        self.dodge_direction = 0
        self.dodge_elapsed = 0.0
        self.dodge_cooldown = 0.0
        self.invulnerability_timer = 0.0
        self.attack_type = None
        self.attack_elapsed = 0.0
        self.attack_hit_registered = False
        self.successful_hits = 0
        self.boss_hit_timer = 0.0
        self.player_health = PLAYER_MAX_HEALTH
        self.seal_gauge = SealGauge()
        self.boss_phase = 1
        self.debug_phase = 1
        self.debug_phase_jump_request = None
        self.debug_forced_pattern = None
        self.boss_defeated = False
        self.boss.reset_for_phase(1)
        self.boss.set_awakened(False)

    def receive_player_hit(self):
        if self.debug_invulnerability_enabled or self.invulnerability_timer > 0:
            return False
        if self.player_health <= 0:
            return False
        self.player_health -= 1
        hit_loss = (
            SealGauge.AWAKENED_HIT_LOSS
            if self.boss.awakened
            else SealGauge.BOSS_HIT_LOSS
        )
        self.seal_gauge.player_hit(hit_loss)
        return True

    def consume_debug_phase_jump(self):
        phase = self.debug_phase_jump_request
        self.debug_phase_jump_request = None
        return phase

    def consume_debug_forced_pattern(self):
        pattern = self.debug_forced_pattern
        self.debug_forced_pattern = None
        return pattern

    def start_dodge(self):
        if self.dodge_direction != 0 or self.dodge_cooldown > 0:
            return
        if self.lane_transition_target is not None or self.attack_type is not None:
            return

        move_right = any(
            key in self.pressed_keys for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_d)
        )
        move_left = any(
            key in self.pressed_keys for key in (pico2d.SDLK_LEFT, pico2d.SDLK_a)
        )
        move_direction = int(move_right) - int(move_left)
        self.dodge_direction = move_direction or self.facing_direction
        self.dodge_elapsed = 0.0
        self.dodge_cooldown = DODGE_COOLDOWN
        self.invulnerability_timer = DODGE_INVULNERABLE_DURATION

    def start_attack(self, attack_type):
        if self.player_lane != "platform_1":
            return
        if self.attack_type is not None or self.dodge_direction != 0:
            return
        if self.lane_transition_target is not None:
            return

        self.attack_type = attack_type
        self.attack_elapsed = 0.0
        self.attack_hit_registered = False

    def resolve_attack_hit(self):
        if self.player_lane != "platform_1":
            return False

        if self.facing_direction > 0:
            attack_left = self.player_logical_x
            attack_right = self.player_logical_x + BASIC_ATTACK_REACH
        else:
            attack_left = self.player_logical_x - BASIC_ATTACK_REACH
            attack_right = self.player_logical_x

        boss_left = BOSS_LOGICAL_X - BOSS_HITBOX_HALF_WIDTH
        boss_right = BOSS_LOGICAL_X + BOSS_HITBOX_HALF_WIDTH
        return attack_left <= boss_right and attack_right >= boss_left

    def update(self, fixed_delta):
        if self.boss_defeated:
            return

        attack_locked = self.attack_type is not None
        move_right = any(
            key in self.pressed_keys for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_d)
        )
        move_left = any(
            key in self.pressed_keys for key in (pico2d.SDLK_LEFT, pico2d.SDLK_a)
        )
        move_direction = int(move_right) - int(move_left)
        if move_direction != 0:
            self.facing_direction = move_direction

        self.dodge_cooldown = max(0.0, self.dodge_cooldown - fixed_delta)
        self.invulnerability_timer = max(
            0.0,
            self.invulnerability_timer - fixed_delta,
        )
        self.boss_hit_timer = max(0.0, self.boss_hit_timer - fixed_delta)
        self.seal_gauge.update(fixed_delta)
        self.boss.set_awakened(self.seal_gauge.boss_awakened)

        if attack_locked:
            attack_duration = (
                BASIC_ATTACK_DURATION
                if self.attack_type == "basic"
                else HEAVY_ATTACK_DURATION
            )
            self.attack_elapsed += fixed_delta
            if (
                not self.attack_hit_registered
                and self.attack_elapsed >= attack_duration * 0.5
            ):
                if self.resolve_attack_hit():
                    self.successful_hits += 1
                    self.boss_hit_timer = 0.12
                    self.seal_gauge.player_attack_hit(self.attack_type)
                self.attack_hit_registered = True
            if self.attack_elapsed >= attack_duration - 1e-9:
                self.attack_type = None
                self.attack_elapsed = 0.0
                self.attack_hit_registered = False
        elif self.dodge_direction != 0:
            dodge_step = DODGE_DISTANCE * fixed_delta / DODGE_DURATION
            self.player_logical_x += self.dodge_direction * dodge_step
            self.dodge_elapsed += fixed_delta
            if self.dodge_elapsed >= DODGE_DURATION - 1e-9:
                self.dodge_direction = 0
                self.dodge_elapsed = 0.0
        else:
            self.player_logical_x += move_direction * PLAYER_SPEED * fixed_delta
        self.player_logical_x = max(
            PLAYER_X_MIN,
            min(self.player_logical_x, PLAYER_X_MAX),
        )

        self.lane_switch_cooldown = max(
            0.0,
            self.lane_switch_cooldown - fixed_delta,
        )
        if self.lane_transition_target is not None:
            self.lane_transition_elapsed += fixed_delta
            if self.lane_transition_elapsed >= LANE_SWITCH_DURATION - 1e-9:
                self.player_lane = self.lane_transition_target
                self.lane_transition_target = None
                self.lane_transition_elapsed = 0.0

        phase_jump = self.consume_debug_phase_jump()
        if phase_jump is not None:
            self.boss_phase = phase_jump
            self.debug_phase = phase_jump
            self.boss.reset_for_phase(phase_jump)
            self.boss.set_awakened(self.seal_gauge.boss_awakened)

        forced_pattern = None
        if self.boss.state == "rest" and self.boss.timer <= fixed_delta:
            forced_pattern = self.consume_debug_forced_pattern()
        boss_attacks = self.boss.update(
            fixed_delta,
            self.boss_phase,
            self.player_lane,
            self.player_logical_x,
            self.debug_pattern_rng,
            forced_pattern,
        )
        for boss_attack in boss_attacks:
            self.resolve_boss_attack(boss_attack)

        if self.player_health <= 0 or self.seal_gauge.boss_won:
            self.restart_current_phase()
        elif self.seal_gauge.player_won:
            if self.boss_phase == 1:
                self.boss_phase = 2
                self.debug_phase = 2
                self.seal_gauge.set_debug_value(0.5)
                self.boss.reset_for_phase(2)
                self.boss.begin_awakening_demo()
            else:
                self.boss_defeated = True

    def restart_current_phase(self):
        phase = self.boss_phase
        self.player_health = PLAYER_MAX_HEALTH
        self.player_lane = "platform_1"
        self.player_logical_x = 240
        self.pressed_keys.clear()
        self.dodge_direction = 0
        self.dodge_elapsed = 0.0
        self.dodge_cooldown = 0.0
        self.invulnerability_timer = 0.0
        self.attack_type = None
        self.attack_elapsed = 0.0
        self.attack_hit_registered = False
        self.lane_transition_target = None
        self.lane_transition_elapsed = 0.0
        self.lane_switch_cooldown = 0.0
        self.seal_gauge.set_debug_value(0.5)
        self.boss.reset_for_phase(phase)
        self.boss.set_awakened(False)

    def resolve_boss_attack(self, attack):
        if self.debug_invulnerability_enabled or self.invulnerability_timer > 0:
            return False
        if self.player_health <= 0:
            return False

        if attack.kind == "lane":
            overlaps = self.player_lane == attack.target_lane
        else:
            lane_matches = (
                attack.kind == "piercing"
                or self.player_lane == attack.target_lane
            )
            target_x = attack.target_x if attack.target_x is not None else BOSS_LOGICAL_X
            hitbox_scale = (
                BossController.AWAKENING_HITBOX_SCALE
                if self.boss.awakened
                else 1.0
            )
            hitbox_half_width = (attack.hitbox_width or 0) * hitbox_scale * 0.5
            overlaps = lane_matches and abs(self.player_logical_x - target_x) <= (
                hitbox_half_width + 25
            )

        if overlaps:
            return self.receive_player_hit()
        return False

    def draw(self):
        draw_room()
        draw_perspective_rails()
        draw_lane(LANES["platform_2"], "rear_lane", "rear_edge", 10)
        draw_lane(LANES["platform_1"], "front_lane", "front_edge", 8)
        draw_boss_placeholder(
            self.boss.awakened,
            self.boss_hit_timer > 0,
            self.boss_defeated,
        )
        self.draw_boss_status()
        self.draw_seal_gauge()
        self.draw_boss_telegraph()

        lane = LANES[self.player_lane]
        player_y = lane["center_y"]
        player_scale = lane["scale"]

        if self.lane_transition_target is not None:
            target_lane = LANES[self.lane_transition_target]
            progress = min(
                self.lane_transition_elapsed / LANE_SWITCH_DURATION,
                1.0,
            )
            player_y += (target_lane["center_y"] - player_y) * progress
            player_scale += (target_lane["scale"] - player_scale) * progress
            lane_left = lane["left"] + (target_lane["left"] - lane["left"]) * progress
            lane_right = lane["right"] + (target_lane["right"] - lane["right"]) * progress
        else:
            lane_left = lane["left"]
            lane_right = lane["right"]

        screen_x = lane_left + self.player_logical_x * (
            lane_right - lane_left
        ) / PLAYER_LOGICAL_WIDTH
        draw_player_placeholder(screen_x, player_y, player_scale)
        self.draw_player_health()

        if self.attack_type is not None:
            set_draw_color("accent_light")
            slash_start_x = screen_x + self.facing_direction * 12 * player_scale
            slash_end_x = screen_x + self.facing_direction * 48 * player_scale
            slash_y = player_y + 38 * player_scale
            slash_count = 2 if self.attack_type == "heavy" else 1
            for slash_index in range(slash_count):
                slash_offset = slash_index * 7 * player_scale
                draw_line(
                    slash_start_x,
                    slash_y - 10 * player_scale + slash_offset,
                    slash_end_x,
                    slash_y + 12 * player_scale + slash_offset,
                )

        if self.debug_hitboxes_visible:
            set_draw_color("accent_light")
            draw_rectangle(
                screen_x - 25 * player_scale,
                player_y,
                screen_x + 25 * player_scale,
                player_y + 90 * player_scale,
            )

            if self.player_lane == "platform_1":
                platform_scale = (lane_right - lane_left) / PLAYER_LOGICAL_WIDTH
                boss_screen_x = lane_left + BOSS_LOGICAL_X * platform_scale
                boss_half_width = BOSS_HITBOX_HALF_WIDTH * platform_scale
                set_draw_color("accent")
                draw_rectangle(
                    boss_screen_x - boss_half_width,
                    435,
                    boss_screen_x + boss_half_width,
                    525,
                )

                if self.attack_type is not None:
                    if self.facing_direction > 0:
                        attack_left = self.player_logical_x
                        attack_right = self.player_logical_x + BASIC_ATTACK_REACH
                    else:
                        attack_left = self.player_logical_x - BASIC_ATTACK_REACH
                        attack_right = self.player_logical_x
                    set_draw_color("accent_light")
                    draw_rectangle(
                        lane_left + attack_left * platform_scale,
                        player_y + 20 * player_scale,
                        lane_left + attack_right * platform_scale,
                        player_y + 70 * player_scale,
                    )

        if self.debug_panel_visible:
            self.draw_debug_panel()

    def draw_debug_panel(self):
        set_draw_color("actor_dark")
        draw_filled_rectangle(20, 390, 430, 700)
        set_draw_color("rear_edge")
        draw_rectangle(20, 390, 430, 700)

        if self.debug_font is None:
            font_path = os.path.join(
                os.environ.get("WINDIR", "C:/Windows"),
                "Fonts",
                "consola.ttf",
            )
            try:
                self.debug_font = pico2d.load_font(font_path, 15)
            except (OSError, RuntimeError):
                return

        action = self.attack_type or ("dodge" if self.dodge_direction else "idle")
        status_lines = (
            "DEBUG  [F1] CLOSE",
            f"PLAYER X   {self.player_logical_x:6.1f}",
            f"PLATFORM   {self.player_lane}",
            f"ACTION     {action}",
            f"HEALTH     {self.player_health}/{PLAYER_MAX_HEALTH}",
            f"INVULN     {'ON' if self.debug_invulnerability_enabled else f'{self.invulnerability_timer:4.2f}s'}",
            f"HITS       {self.successful_hits}",
            f"PHASE      {self.debug_phase}  [F5 jump]",
            f"GAUGE      {self.seal_gauge.value:4.0%}  [[ / ] adjust]",
            f"PATTERN    {self.debug_forced_pattern or '-'}  [F6 cycle]",
            f"SEED       {'FIXED ' + str(self.debug_pattern_seed) if self.debug_pattern_seed_fixed else 'RANDOM'}  [F7]",
        )
        for line_index, text in enumerate(status_lines):
            self.debug_font.draw(
                36,
                676 - line_index * 26,
                text,
                (221, 235, 220),
            )

    def draw_seal_gauge(self):
        gauge_left = 360
        gauge_right = 920
        gauge_bottom = 650
        gauge_top = 682
        gauge_inner_left = gauge_left + 2
        gauge_inner_right = gauge_right - 2
        gauge_width = gauge_inner_right - gauge_inner_left
        player_edge = gauge_inner_left + gauge_width * (1.0 - self.seal_gauge.value)

        set_draw_color("actor_dark")
        draw_filled_rectangle(gauge_left, gauge_bottom, gauge_right, gauge_top)
        if player_edge > gauge_inner_left:
            set_draw_color("rear_edge")
            draw_filled_rectangle(
                gauge_inner_left,
                gauge_bottom + 2,
                player_edge,
                gauge_top - 2,
            )
        if player_edge < gauge_inner_right:
            set_draw_color("accent")
            draw_filled_rectangle(
                player_edge,
                gauge_bottom + 2,
                gauge_inner_right,
                gauge_top - 2,
            )
        set_draw_color("actor_light")
        for gauge_threshold in (0.60, 0.85):
            threshold_x = gauge_inner_left + gauge_width * (1.0 - gauge_threshold)
            draw_line(threshold_x, gauge_bottom, threshold_x, gauge_top)
        draw_rectangle(gauge_left, gauge_bottom, gauge_right, gauge_top)

    def draw_boss_telegraph(self):
        if self.boss.state != "telegraph" or self.boss.current_pattern is None:
            return

        pattern = PATTERNS[self.boss.current_pattern]
        if pattern["kind"] == "lane":
            target_lane = LANES[self.boss.target_lane]
            set_draw_color("accent_light")
            draw_rectangle(
                target_lane["left"],
                target_lane["bottom"],
                target_lane["right"],
                target_lane["top"],
            )
            return

        if self.boss.current_pattern in ("slam", "double_slam"):
            target_lane = LANES["platform_1"]
            target_x = BOSS_LOGICAL_X
        elif pattern["kind"] == "piercing":
            target_lane = LANES["platform_1"]
            target_x = BOSS_LOGICAL_X
        else:
            target_lane = LANES[self.boss.target_lane]
            target_x = self.boss.target_x or BOSS_LOGICAL_X

        platform_scale = (
            target_lane["right"] - target_lane["left"]
        ) / PLAYER_LOGICAL_WIDTH
        screen_x = target_lane["left"] + target_x * (
            target_lane["right"] - target_lane["left"]
        ) / PLAYER_LOGICAL_WIDTH
        radius = max(8, int((pattern["hitbox_width"] or 80) * 0.5 * platform_scale))
        set_draw_color("accent_light")
        draw_filled_circle(screen_x, target_lane["center_y"], radius)

        if pattern["kind"] == "piercing":
            rear_lane = LANES["platform_2"]
            rear_x = rear_lane["left"] + target_x * (
                rear_lane["right"] - rear_lane["left"]
            ) / PLAYER_LOGICAL_WIDTH
            draw_filled_circle(rear_x, rear_lane["center_y"], radius)

    def draw_player_health(self):
        for health_index in range(PLAYER_MAX_HEALTH):
            color = "accent_light" if health_index < self.player_health else "wall_light"
            set_draw_color(color)
            health_x = WIDTH - 38 - health_index * 30
            draw_filled_circle(health_x, HEIGHT - 34, 10)

    def draw_boss_status(self):
        if self.debug_font is None:
            font_path = os.path.join(
                os.environ.get("WINDIR", "C:/Windows"),
                "Fonts",
                "consola.ttf",
            )
            try:
                self.debug_font = pico2d.load_font(font_path, 15)
            except (OSError, RuntimeError):
                return
        if self.boss_defeated:
            status = "BOSS DEFEATED"
        else:
            state = "AWAKENED" if self.boss.awakened else "NORMAL"
            pattern = self.boss.current_pattern or "WAIT"
            status = f"BOSS PHASE {self.boss_phase}  {state}  {pattern.upper()}"
        self.debug_font.draw(24, HEIGHT - 40, status, (240, 230, 215))
        status = "BOSS DEFEATED" if self.boss_defeated else f"BOSS  PHASE {self.boss_phase}"
        self.debug_font.draw(24, HEIGHT - 40, status, (240, 230, 215))