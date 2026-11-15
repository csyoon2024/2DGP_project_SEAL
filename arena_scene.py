import os
import math
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
DRAW_OFFSET_X = 0
DRAW_OFFSET_Y = 0

COLORS = {
    "background": (12, 14, 20),
    "wall": (18, 21, 31),
    "wall_light": (42, 48, 65),
    "floor": (30, 36, 54),
    "floor_line": (54, 62, 82),
    "rear_lane": (22, 34, 46),
    "rear_edge": (74, 158, 255),
    "front_lane": (58, 35, 24),
    "front_edge": (255, 107, 53),
    "accent": (224, 28, 44),
    "accent_light": (255, 107, 53),
    "flash": (255, 244, 224),
    "actor_dark": (10, 12, 16),
    "actor": (10, 12, 16),
    "actor_light": (74, 158, 255),
    "shadow": (12, 14, 20),
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


def set_draw_color(name, alpha=255):
    global active_color
    active_color = (*COLORS[name], alpha)


def set_draw_rgb(red, green, blue, alpha=255):
    global active_color
    active_color = (int(red), int(green), int(blue), int(alpha))


def draw_filled_circle(x, y, radius):
    pico_draw_circle(
        int(round(x + DRAW_OFFSET_X)),
        int(round(y + DRAW_OFFSET_Y)),
        max(1, int(round(radius))),
        *active_color,
        filled=True,
    )


def draw_filled_ellipse(center_x, center_y, radius_x, radius_y):
    radius_x = max(1, int(round(radius_x)))
    radius_y = max(1, int(round(radius_y)))
    for y_offset in range(-radius_y, radius_y + 1):
        normalized_y = y_offset / radius_y
        half_width = radius_x * math.sqrt(max(0.0, 1.0 - normalized_y**2))
        draw_line(
            center_x - half_width,
            center_y + y_offset,
            center_x + half_width,
            center_y + y_offset,
        )


def draw_filled_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left + DRAW_OFFSET_X)),
        int(round(bottom + DRAW_OFFSET_Y)),
        int(round(right + DRAW_OFFSET_X)),
        int(round(top + DRAW_OFFSET_Y)),
        *active_color,
        filled=True,
    )


def draw_line(x1, y1, x2, y2):
    pico_draw_line(
        int(round(x1 + DRAW_OFFSET_X)),
        int(round(y1 + DRAW_OFFSET_Y)),
        int(round(x2 + DRAW_OFFSET_X)),
        int(round(y2 + DRAW_OFFSET_Y)),
        *active_color,
    )


def draw_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left + DRAW_OFFSET_X)),
        int(round(bottom + DRAW_OFFSET_Y)),
        int(round(right + DRAW_OFFSET_X)),
        int(round(top + DRAW_OFFSET_Y)),
        *active_color,
    )


def draw_room():
    horizon_y = 430
    vanishing_x = WIDTH * 0.5
    band_count = 36
    top_color = (10, 12, 19)
    bottom_color = (25, 30, 43)

    for band_index in range(band_count):
        bottom = HEIGHT * band_index / band_count
        top = HEIGHT * (band_index + 1) / band_count
        blend = band_index / (band_count - 1)
        color = tuple(
            top_color[channel] * blend + bottom_color[channel] * (1 - blend)
            for channel in range(3)
        )
        set_draw_rgb(*color)
        draw_filled_rectangle(0, bottom, WIDTH, top)

    floor_bands = 32
    floor_bottom_color = (33, 39, 54)
    floor_horizon_color = (17, 21, 31)
    for band_index in range(floor_bands):
        depth_bottom = band_index / floor_bands
        depth_top = (band_index + 1) / floor_bands
        y_bottom = horizon_y * depth_bottom
        y_top = horizon_y * depth_top
        bottom_half_width = WIDTH * 0.5 - (WIDTH * 0.5 - 16) * depth_bottom
        top_half_width = WIDTH * 0.5 - (WIDTH * 0.5 - 16) * depth_top
        blend = (depth_bottom + depth_top) * 0.5
        color = tuple(
            floor_bottom_color[channel] * (1 - blend)
            + floor_horizon_color[channel] * blend
            for channel in range(3)
        )
        set_draw_rgb(*color)
        draw_filled_rectangle(
            vanishing_x - bottom_half_width,
            y_bottom,
            vanishing_x + bottom_half_width,
            y_top,
        )

    set_draw_color("floor_line", 78)
    draw_line(0, 0, vanishing_x, horizon_y)
    draw_line(WIDTH, 0, vanishing_x, horizon_y)
    for floor_x in range(0, WIDTH + 1, 160):
        draw_line(floor_x, 0, vanishing_x, horizon_y)

    for row_index in range(1, 15):
        normalized = row_index / 15
        depth = 1 - (1 - normalized) ** 1.8
        row_y = horizon_y * depth
        half_width = WIDTH * 0.5 - (WIDTH * 0.5 - 16) * depth
        draw_line(vanishing_x - half_width, row_y, vanishing_x + half_width, row_y)

    set_draw_color("wall_light", 34)
    draw_filled_rectangle(0, 398, WIDTH, 458)
    set_draw_color("wall_light", 110)
    draw_line(0, horizon_y, WIDTH, horizon_y)


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


def draw_boss_placeholder(
    awakened=False,
    hit=False,
    defeated=False,
    pose="idle",
    forward_progress=0.0,
    center_x=640,
):
    awakening_scale = BossController.AWAKENING_SIZE_SCALE if awakened else 1.0
    lunge_scale = 1.0 + (1.05 / 0.78 - 1.0) * forward_progress
    scale = max(awakening_scale, lunge_scale)
    foot_y = min(440 if awakened else 480, 480 - 60 * forward_progress)
    body_half_width = 42 * scale
    body_bottom = foot_y + 34 * scale
    body_top = foot_y + 142 * scale
    head_y = foot_y + 166 * scale

    set_draw_color("shadow")
    draw_filled_rectangle(
        center_x - 55 * scale,
        470,
        center_x + 55 * scale,
        482,
    )

    body_color = "flash" if hit else ("wall_light" if defeated else "actor_dark")
    set_draw_color("actor_dark")
    draw_filled_rectangle(
        center_x - body_half_width - 8 * scale,
        body_bottom - 8 * scale,
        center_x + body_half_width + 8 * scale,
        body_top + 8 * scale,
    )
    draw_filled_circle(center_x, head_y, 34 * scale)

    set_draw_color(body_color)
    draw_filled_rectangle(
        center_x - body_half_width,
        body_bottom,
        center_x + body_half_width,
        body_top,
    )
    draw_filled_circle(center_x, head_y, 27 * scale)

    set_draw_color("actor_dark")
    horn_start_y = min(head_y + 18 * scale, HEIGHT - 1)
    horn_end_y = min(head_y + 48 * scale, HEIGHT - 1)
    draw_line(center_x - 30 * scale, horn_start_y, center_x - 48 * scale, horn_end_y)
    draw_line(center_x + 30 * scale, horn_start_y, center_x + 48 * scale, horn_end_y)
    draw_line(center_x - 20 * scale, body_bottom, center_x - 28 * scale, foot_y)
    draw_line(center_x + 20 * scale, body_bottom, center_x + 28 * scale, foot_y)

    shoulder_y = body_top - 12 * scale

    def draw_arm(side, elbow_x, elbow_y, hand_x, hand_y):
        shoulder_x = center_x + side * body_half_width
        elbow_screen_x = center_x + side * elbow_x * scale
        hand_screen_x = center_x + side * hand_x * scale
        draw_line(shoulder_x, shoulder_y, elbow_screen_x, elbow_y)
        draw_line(elbow_screen_x, elbow_y, hand_screen_x, hand_y)
        draw_filled_circle(hand_screen_x, hand_y, 9 * scale)

    if pose == "slam":
        draw_arm(-1, 58, min(foot_y + 177 * scale, HEIGHT - 45), 64, min(foot_y + 220 * scale, HEIGHT - 12))
        draw_arm(1, 58, foot_y + 105 * scale, 75, foot_y + 78 * scale)
    elif pose == "slam_double":
        raised_elbow_y = min(foot_y + 177 * scale, HEIGHT - 45)
        raised_hand_y = min(foot_y + 220 * scale, HEIGHT - 12)
        draw_arm(-1, 58, raised_elbow_y, 64, raised_hand_y)
        draw_arm(1, 58, raised_elbow_y, 64, raised_hand_y)
    elif pose == "shockwave":
        draw_arm(-1, 75, foot_y + 142 * scale, 112, foot_y + 142 * scale)
        draw_arm(1, 75, foot_y + 142 * scale, 112, foot_y + 142 * scale)
    elif pose == "charge":
        draw_arm(-1, 54, foot_y + 125 * scale, 26, foot_y + 104 * scale)
        draw_arm(1, 54, foot_y + 125 * scale, 26, foot_y + 104 * scale)
    elif pose == "homing":
        draw_arm(-1, 56, foot_y + 116 * scale, 38, foot_y + 84 * scale)
        draw_arm(1, 76, foot_y + 144 * scale, 126, foot_y + 150 * scale)
    elif pose in ("slam_impact", "shockwave_impact"):
        draw_arm(-1, 68, foot_y + 76 * scale, 90, foot_y + 12 * scale)
        draw_arm(1, 68, foot_y + 76 * scale, 90, foot_y + 12 * scale)
    else:
        draw_arm(-1, 56, foot_y + 108 * scale, 78, foot_y + 82 * scale)
        draw_arm(1, 56, foot_y + 108 * scale, 78, foot_y + 82 * scale)

    set_draw_color("accent")
    draw_line(center_x - 22 * scale, body_top - 36 * scale, center_x + 22 * scale, body_top - 36 * scale)
    draw_line(center_x - 24 * scale, body_top - 46 * scale, center_x + 24 * scale, body_top - 46 * scale)
    set_draw_color("accent_light" if awakened else "accent")
    draw_filled_circle(center_x - 10 * scale, head_y, 4 * scale)
    draw_filled_circle(center_x + 10 * scale, head_y, 4 * scale)


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
        self.player_logical_x = 310
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
        self.screen_shake_timer = 0.0
        self.screen_shake_duration = 0.0
        self.screen_shake_strength = 0.0
        self.screen_shake_frame = 0
        self.impact_flash_timer = 0.0
        self.impact_flash_position = (640, 360)
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
        self.player_logical_x = 310
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
        lane = LANES[self.player_lane]
        player_screen_x = lane["left"] + self.player_logical_x * (
            lane["right"] - lane["left"]
        ) / PLAYER_LOGICAL_WIDTH
        self.trigger_impact_flash(player_screen_x, lane["center_y"])
        self.trigger_screen_shake(8, 0.15)
        return True

    def trigger_screen_shake(self, strength, duration):
        if strength >= self.screen_shake_strength or self.screen_shake_timer <= 0:
            self.screen_shake_strength = strength
            self.screen_shake_duration = duration
            self.screen_shake_timer = duration
            self.screen_shake_frame = 0

    def trigger_impact_flash(self, x, y):
        self.impact_flash_position = (x, y)
        self.impact_flash_timer = 0.08

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

        boss_left = self.boss.position_x - BOSS_HITBOX_HALF_WIDTH
        boss_right = self.boss.position_x + BOSS_HITBOX_HALF_WIDTH
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
        self.screen_shake_timer = max(0.0, self.screen_shake_timer - fixed_delta)
        self.impact_flash_timer = max(0.0, self.impact_flash_timer - fixed_delta)
        self.screen_shake_frame += 1
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
                    self.boss_hit_timer = 0.06
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
            shake_strength, shake_duration = PATTERNS[boss_attack.pattern]["shake"]
            if boss_attack.pattern == "slam_double":
                shake_strength = 6 if boss_attack.hit_index == 0 else 8
            impact_lane = LANES[boss_attack.target_lane or self.player_lane]
            impact_x = boss_attack.target_x
            if impact_x is None:
                impact_screen_x = WIDTH / 2
            else:
                impact_screen_x = impact_lane["left"] + impact_x * (
                    impact_lane["right"] - impact_lane["left"]
                ) / PLAYER_LOGICAL_WIDTH
            self.trigger_screen_shake(shake_strength, shake_duration)
            self.trigger_impact_flash(impact_screen_x, impact_lane["center_y"])
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
        self.player_logical_x = 310
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

        if attack.kind == "wide":
            overlaps = self.player_lane == attack.target_lane
        else:
            lane_matches = (
                attack.kind == "pierce"
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
        global DRAW_OFFSET_X, DRAW_OFFSET_Y
        if self.screen_shake_timer > 0 and self.screen_shake_duration > 0:
            shake_scale = self.screen_shake_timer / self.screen_shake_duration
            shake_sign = -1 if self.screen_shake_frame % 2 else 1
            DRAW_OFFSET_X = round(
                self.screen_shake_strength * shake_scale * shake_sign
            )
            DRAW_OFFSET_Y = round(
                self.screen_shake_strength * 0.35 * shake_scale * -shake_sign
            )
        else:
            DRAW_OFFSET_X = 0
            DRAW_OFFSET_Y = 0

        draw_room()
        draw_perspective_rails()
        draw_lane(LANES["platform_2"], "rear_lane", "rear_edge", 10)
        draw_lane(LANES["platform_1"], "front_lane", "front_edge", 8)

        boss_pose = "idle"
        if self.boss.current_pattern is not None:
            boss_pose = PATTERNS[self.boss.current_pattern]["pose"]
            if self.boss.state in ("active", "recovery"):
                if self.boss.current_pattern in ("slam", "slam_double"):
                    boss_pose = "slam_impact"
                elif self.boss.current_pattern == "shockwave":
                    boss_pose = "shockwave_impact"

        boss_lane = LANES["platform_1"]
        boss_screen_x = boss_lane["left"] + self.boss.position_x * (
            boss_lane["right"] - boss_lane["left"]
        ) / PLAYER_LOGICAL_WIDTH
        draw_boss_placeholder(
            self.boss.awakened,
            self.boss_hit_timer > 0,
            self.boss_defeated,
            boss_pose,
            self.boss.forward_progress,
            boss_screen_x,
        )
        self.draw_boss_status()
        self.draw_seal_gauge()
        self.draw_boss_telegraph()
        self.draw_homing_projectile()
        self.draw_active_boss_effects()
        self.draw_impact_flash()

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
            attack_duration = (
                BASIC_ATTACK_DURATION
                if self.attack_type == "basic"
                else HEAVY_ATTACK_DURATION
            )
            reach_progress = min(self.attack_elapsed / (attack_duration * 0.45), 1.0)
            platform_scale = (lane_right - lane_left) / PLAYER_LOGICAL_WIDTH
            slash_start_x = screen_x + self.facing_direction * 8 * player_scale
            slash_end_x = screen_x + self.facing_direction * (
                BASIC_ATTACK_REACH * platform_scale * reach_progress
            )
            slash_start_y = player_y + 24 * player_scale
            slash_end_y = player_y + 205 * reach_progress
            slash_offsets = (
                (-18, -9, 0, 9, 18)
                if self.attack_type == "heavy"
                else (-9, 0, 9)
            )
            for slash_offset in slash_offsets:
                scaled_offset = slash_offset * player_scale
                draw_line(
                    slash_start_x,
                    slash_start_y + scaled_offset,
                    slash_end_x,
                    slash_end_y + scaled_offset,
                )
            draw_filled_circle(slash_end_x, slash_end_y, 8 * player_scale)

        if self.debug_hitboxes_visible:
            set_draw_color("accent_light", 255 if visible else 45)
            draw_rectangle(
                screen_x - 25 * player_scale,
                player_y,
                screen_x + 25 * player_scale,
                player_y + 90 * player_scale,
            )

            if self.player_lane == "platform_1":
                platform_scale = (lane_right - lane_left) / PLAYER_LOGICAL_WIDTH
                boss_screen_x = lane_left + self.boss.position_x * platform_scale
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

        DRAW_OFFSET_X = 0
        DRAW_OFFSET_Y = 0

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
        visible = self.boss.telegraph_is_visible()
        elapsed = self.boss.telegraph_elapsed
        progress = min(elapsed / pattern["telegraph"], 1.0)
        fill_alpha = 90 if visible else 0
        marker_alpha = int(60 + 140 * progress) if visible else 60

        if pattern["marker"] == "lane":
            target_lane = LANES[self.boss.target_lane]
            set_draw_color("accent", fill_alpha)
            draw_filled_rectangle(
                target_lane["left"],
                target_lane["bottom"],
                target_lane["right"],
                target_lane["top"],
            )
            set_draw_color("accent_light")
            draw_rectangle(
                target_lane["left"],
                target_lane["bottom"],
                target_lane["right"],
                target_lane["top"],
            )
            return

        if pattern["marker"] == "column":
            target_x = self.boss.target_x
            set_draw_color("accent", fill_alpha)
            for lane_name in ("platform_1", "platform_2"):
                lane = LANES[lane_name]
                scale = (lane["right"] - lane["left"]) / PLAYER_LOGICAL_WIDTH
                center_x = lane["left"] + target_x * scale
                half_width = pattern["hitbox_width"] * scale * 0.5
                draw_filled_rectangle(
                    center_x - half_width,
                    lane["bottom"],
                    center_x + half_width,
                    lane["top"],
                )
                set_draw_color("accent_light", 255 if visible else 45)
                draw_rectangle(
                    center_x - half_width,
                    lane["bottom"],
                    center_x + half_width,
                    lane["top"],
                )
                set_draw_color("accent", fill_alpha)
            return

        targets = [(self.boss.target_lane, self.boss.target_x)]
        if pattern["marker"] == "two_spots":
            targets.append(("platform_1", self.boss.secondary_target_x))

        for target_lane_name, target_x in targets:
            target_lane = LANES[target_lane_name]
            scale = (target_lane["right"] - target_lane["left"]) / PLAYER_LOGICAL_WIDTH
            screen_x = target_lane["left"] + target_x * scale
            growth = 1.0 - 0.5 * progress
            set_draw_color("accent", marker_alpha)
            draw_filled_ellipse(
                screen_x,
                target_lane["center_y"] + 4,
                80 * growth * scale,
                18 * growth * target_lane["scale"],
            )
            set_draw_color("accent_light", 255 if visible else 45)
            draw_rectangle(
                screen_x - 2,
                target_lane["center_y"] - 3,
                screen_x + 2,
                target_lane["center_y"] + 3,
            )

    def draw_homing_projectile(self):
        if self.boss.current_pattern != "homing" or self.boss.state != "active":
            return

        lane = LANES[self.boss.target_lane]
        lane_scale = (lane["right"] - lane["left"]) / PLAYER_LOGICAL_WIDTH
        target_x = lane["left"] + self.boss.target_x * lane_scale
        progress = min(
            self.boss.attack_elapsed / PATTERNS["homing"]["duration"],
            1.0,
        )
        boss_lane = LANES["platform_1"]
        boss_screen_x = boss_lane["left"] + self.boss.position_x * (
            boss_lane["right"] - boss_lane["left"]
        ) / PLAYER_LOGICAL_WIDTH
        projectile_x = boss_screen_x + (target_x - boss_screen_x) * progress
        projectile_y = 620 + (lane["center_y"] - 620) * progress

        set_draw_color("accent", 100)
        draw_filled_ellipse(
            target_x,
            lane["center_y"] + 4,
            80 - 40 * progress,
            16 - 8 * progress,
        )
        set_draw_color("accent_light")
        draw_filled_circle(projectile_x, projectile_y, 8 + 12 * progress)

    def draw_active_boss_effects(self):
        if self.boss.state != "active" or self.boss.current_pattern is None:
            return

        pattern_name = self.boss.current_pattern
        pattern = PATTERNS[pattern_name]
        progress = min(self.boss.attack_elapsed / pattern["duration"], 1.0)
        if pattern["marker"] == "column" and self.boss.target_x is not None:
            set_draw_color("flash", 190)
            for lane_name in ("platform_1", "platform_2"):
                lane = LANES[lane_name]
                scale = (lane["right"] - lane["left"]) / PLAYER_LOGICAL_WIDTH
                center_x = lane["left"] + self.boss.target_x * scale
                half_width = pattern["hitbox_width"] * scale * 0.5
                draw_filled_rectangle(
                    center_x - half_width,
                    lane["bottom"],
                    center_x + half_width,
                    lane["top"],
                )
        elif pattern["marker"] == "lane":
            lane = LANES[self.boss.target_lane]
            lane_center = (lane["left"] + lane["right"]) * 0.5
            wave_offset = (lane["right"] - lane["left"]) * 0.5 * progress
            half_width = max(10, (lane["right"] - lane["left"]) * 0.018)
            set_draw_color("flash", 220)
            for wave_center in (lane_center - wave_offset, lane_center + wave_offset):
                draw_filled_rectangle(
                    wave_center - half_width,
                    lane["bottom"],
                    wave_center + half_width,
                    lane["top"],
                )
        elif pattern["marker"] == "two_spots" and self.boss.next_hit_index == 1:
            lane = LANES["platform_1"]
            scale = (lane["right"] - lane["left"]) / PLAYER_LOGICAL_WIDTH
            target_x = lane["left"] + self.boss.secondary_target_x * scale
            marker_progress = min(progress / 0.65, 1.0)
            set_draw_color("accent_light", int(90 + 110 * marker_progress))
            draw_filled_ellipse(
                target_x,
                lane["center_y"] + 4,
                80 * (1.0 - 0.5 * marker_progress) * scale,
                18 * (1.0 - 0.5 * marker_progress) * lane["scale"],
            )

    def draw_impact_flash(self):
        if self.impact_flash_timer <= 0:
            return
        x, y = self.impact_flash_position
        alpha = int(220 * min(self.impact_flash_timer / 0.08, 1.0))
        radius = 30 + 30 * (1.0 - self.impact_flash_timer / 0.08)
        set_draw_color("flash", alpha)
        draw_filled_circle(x, y, radius)

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
