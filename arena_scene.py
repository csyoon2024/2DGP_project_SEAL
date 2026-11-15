import os
import math
import random
from ctypes import c_int

import pico2d
import sdl2

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
BOSS_DISPLAY_SCALE = 1.5
# 보스 실루엣(뿔·치켜든 손 포함)의 상한. 게이지 바 아랫변 650보다 충분히 아래 (조건: < 620)
BOSS_CEILING_Y = 615

# ---------------------------------------------------------------------------
# 원근 카메라 — 화면의 모든 평면은 이 한 점으로 수렴한다.
#
# depth(s)는 "카메라에서 멀수록 작아지는 배율"이다. 뒷줄(카메라 쪽) 1.0,
# 앞줄(보스 쪽) 0.71. 월드 좌표 (X, 높이 E, 깊이 s)는
#   screen_x = VANISHING_X + X * s
#   screen_y = VANISHING_Y - (CAMERA_HEIGHT - E) * s
# 로 투영된다. s가 0으로 가면 모든 점이 소실점에 모인다.
# 게임플레이는 여전히 논리 x 0~900만 쓴다. 이 블록은 그리기 전용이다.
# ---------------------------------------------------------------------------
VANISHING_X = WIDTH / 2
# 660 → 583: 게이지 바(y 650~690)와 겹치지 않게 장면 전체를 아래로 내린다.
#   뒷줄 앞 모서리 = 583 - (520 - 22) * 1.10 ≈ 35 (조건: y ≥ 20)
VANISHING_Y = 583
# 580 → 520: 소실점을 내리면서 카메라도 낮춰 레인 간격을 유지한다.
#   앞줄 먼 모서리 = 583 - (520 - 36) * 0.645 ≈ 271, 두 플랫폼 세로 합계 ≈ 190px (< 720의 45%)
CAMERA_HEIGHT = 520
LANE_HALF_WIDTH = 590
ROOM_HALF_WIDTH = 760
ROOM_NEAR_DEPTH = 1.6
BACK_WALL_DEPTH = 0.40
CEILING_HEIGHT = 1100
BOSS_DEPTH = 0.50
BOSS_CHARGE_DEPTH = 0.60

# 보스 단상 — 3단. 위로 갈수록 좁고 얕아진다.
# (앞 깊이, 뒤 깊이, 아랫단 반폭, 윗면 높이, 옆면 경사폭)
PEDESTAL_TIERS = (
    (0.600, 0.440, 340, 30, 18),
    (0.565, 0.450, 270, 60, 16),
    (0.535, 0.460, 200, 90, 14),
)
PEDESTAL_TOP_ELEVATION = PEDESTAL_TIERS[-1][3]

# 좌우 벽 기둥 — 레인과 겹치지 않는 깊이(레인 사이, 단상 옆, 뒷벽 앞)에 둔다
PILLAR_DEPTHS = (0.46, 0.62, 0.86)
PILLAR_INNER_X = 660
PILLAR_OUTER_X = 750
PILLAR_THICKNESS = 0.14  # 깊이 방향 두께 (1/s 단위)

LANES = {
    "platform_2": {
        "near": 1.10,
        "far": 0.90,
        "scale": 1.0,
        "elevation": 22,
        # 보이드 위에 뜬 판의 두께. elevation(띄운 높이)과 분리한다
        "thickness": 10,
    },
    "platform_1": {
        "near": 0.78,
        "far": 0.645,
        "scale": 0.71,
        "elevation": 36,
        # 멀리 있어 화면에서 더 얇아 보이도록 뒷줄보다 조금 얇게
        "thickness": 8,
    },
}


def project(world_x, depth, elevation=0.0):
    return (
        VANISHING_X + world_x * depth,
        VANISHING_Y - (CAMERA_HEIGHT - elevation) * depth,
    )


def logical_to_world_x(logical_x):
    return (logical_x / PLAYER_LOGICAL_WIDTH - 0.5) * 2 * LANE_HALF_WIDTH


def logical_pixels(depth):
    """논리 x 1이 해당 깊이에서 화면 몇 px인지."""
    return 2 * LANE_HALF_WIDTH / PLAYER_LOGICAL_WIDTH * depth


def lane_point(lane_name, logical_x, depth=None):
    lane = LANES[lane_name]
    if depth is None:
        depth = lane["scale"]
    return project(logical_to_world_x(logical_x), depth, lane["elevation"])


def lane_quad(lane_name, logical_left=0, logical_right=PLAYER_LOGICAL_WIDTH):
    """레인 윗면의 사다리꼴: 앞-왼, 앞-오, 뒤-오, 뒤-왼."""
    lane = LANES[lane_name]
    left = logical_to_world_x(logical_left)
    right = logical_to_world_x(logical_right)
    return (
        project(left, lane["near"], lane["elevation"]),
        project(right, lane["near"], lane["elevation"]),
        project(right, lane["far"], lane["elevation"]),
        project(left, lane["far"], lane["elevation"]),
    )


def boss_anchor(position_x, forward_progress):
    """보스 발치(매몰선)의 화면 좌표와 깊이. 보스는 단상 꼭대기에 묻혀 있다."""
    depth = BOSS_DEPTH + (BOSS_CHARGE_DEPTH - BOSS_DEPTH) * forward_progress
    x, y = project(logical_to_world_x(position_x), depth, PEDESTAL_TOP_ELEVATION)
    return x, y, depth


def set_draw_color(name, alpha=255, saturation=1.0, blue_tint=0.0):
    global active_color
    color = COLORS[name]
    luminance = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    desaturated = tuple(
        luminance + (channel - luminance) * saturation
        for channel in color
    )
    blue_color = (30, 55, 95)
    tinted = tuple(
        channel * (1.0 - blue_tint) + blue * blue_tint
        for channel, blue in zip(desaturated, blue_color)
    )
    active_color = (*tuple(round(channel) for channel in tinted), alpha)


def set_draw_rgb(red, green, blue, alpha=255):
    global active_color
    active_color = (int(red), int(green), int(blue), int(alpha))


_pico2d_state = pico2d.open_canvas.__globals__


def draw_polygon(points, colors=None):
    """볼록 다각형을 한 번의 SDL_RenderGeometry 호출로 채운다.

    colors를 꼭짓점마다 주면 GPU가 그라데이션을 보간한다.
    """
    renderer = _pico2d_state.get("renderer")
    count = len(points)
    if renderer is None or count < 3:
        return
    vertices = (sdl2.SDL_Vertex * count)()
    for index, (x, y) in enumerate(points):
        red, green, blue, alpha = colors[index] if colors else active_color
        vertex = vertices[index]
        vertex.position.x = x + DRAW_OFFSET_X
        vertex.position.y = HEIGHT - (y + DRAW_OFFSET_Y)
        vertex.color = sdl2.SDL_Color(int(red), int(green), int(blue), int(alpha))
    index_count = (count - 2) * 3
    indices = (c_int * index_count)()
    for triangle in range(count - 2):
        indices[triangle * 3] = 0
        indices[triangle * 3 + 1] = triangle + 1
        indices[triangle * 3 + 2] = triangle + 2
    sdl2.SDL_RenderGeometry(renderer, None, vertices, count, indices, index_count)


def draw_filled_circle(x, y, radius):
    pico_draw_circle(
        int(round(x + DRAW_OFFSET_X)),
        int(round(y + DRAW_OFFSET_Y)),
        max(1, int(round(radius))),
        *active_color,
        filled=True,
    )


def draw_filled_ellipse(center_x, center_y, radius_x, radius_y, segments=28):
    points = [
        (
            center_x + radius_x * math.cos(2 * math.pi * index / segments),
            center_y + radius_y * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments)
    ]
    draw_polygon(points)


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


def draw_polyline(points, closed=True):
    count = len(points)
    for index in range(count if closed else count - 1):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        draw_line(x1, y1, x2, y2)


def draw_void():
    """배경 보이드 — 단색. 플랫폼과 단상이 그 위에 떠 있다 (BOSS1_SPEC §1.1 #0C0E14)."""
    set_draw_color("background")
    draw_filled_rectangle(0, 0, WIDTH, HEIGHT)


def draw_room():
    wall_y = VANISHING_Y - CAMERA_HEIGHT * BACK_WALL_DEPTH
    wall_half = ROOM_HALF_WIDTH * BACK_WALL_DEPTH

    # 뒷벽 — 위로 갈수록 어두워지는 수직 그라데이션
    draw_polygon(
        (
            (VANISHING_X - wall_half, wall_y),
            (VANISHING_X + wall_half, wall_y),
            (VANISHING_X + wall_half, HEIGHT),
            (VANISHING_X - wall_half, HEIGHT),
        ),
        ((24, 28, 40, 255), (24, 28, 40, 255), (10, 12, 18, 255), (10, 12, 18, 255)),
    )

    # 좌우 벽 — 카메라 쪽이 밝고 소실점 쪽이 어둡다
    for side in (-1, 1):
        near_floor = project(side * ROOM_HALF_WIDTH, ROOM_NEAR_DEPTH)
        far_floor = project(side * ROOM_HALF_WIDTH, BACK_WALL_DEPTH)
        far_top = project(side * ROOM_HALF_WIDTH, BACK_WALL_DEPTH, CEILING_HEIGHT)
        near_top = project(side * ROOM_HALF_WIDTH, ROOM_NEAR_DEPTH, CEILING_HEIGHT)
        draw_polygon(
            (near_floor, far_floor, far_top, near_top),
            ((30, 35, 50, 255), (18, 21, 30, 255), (10, 12, 18, 255), (14, 16, 24, 255)),
        )

    # 바닥 — 카메라 쪽 밝게, 뒷벽 쪽 어둡게
    floor = (
        project(-ROOM_HALF_WIDTH, ROOM_NEAR_DEPTH),
        project(ROOM_HALF_WIDTH, ROOM_NEAR_DEPTH),
        project(ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
        project(-ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
    )
    near_color = (36, 42, 58, 255)
    far_color = (17, 20, 30, 255)
    draw_polygon(floor, (near_color, near_color, far_color, far_color))

    # 바닥 격자 — 세로줄은 전부 소실점으로, 가로줄은 깊이 간격이 좁아진다
    set_draw_color("floor_line", 70)
    grid_step = 2 * ROOM_HALF_WIDTH / 10
    for line_index in range(11):
        world_x = -ROOM_HALF_WIDTH + grid_step * line_index
        draw_line(
            *project(world_x, ROOM_NEAR_DEPTH),
            *project(world_x, BACK_WALL_DEPTH),
        )
    near_distance = 1.0 / ROOM_NEAR_DEPTH
    far_distance = 1.0 / BACK_WALL_DEPTH
    row_count = 14
    for row_index in range(1, row_count):
        distance = near_distance + (far_distance - near_distance) * row_index / row_count
        depth = 1.0 / distance
        draw_line(
            *project(-ROOM_HALF_WIDTH, depth),
            *project(ROOM_HALF_WIDTH, depth),
        )

    # 벽과 바닥이 만나는 모서리
    set_draw_color("wall_light", 150)
    for side in (-1, 1):
        draw_line(
            *project(side * ROOM_HALF_WIDTH, ROOM_NEAR_DEPTH),
            *project(side * ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
        )
        draw_line(
            *project(side * ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
            *project(side * ROOM_HALF_WIDTH, BACK_WALL_DEPTH, CEILING_HEIGHT),
        )
    draw_line(VANISHING_X - wall_half, wall_y, VANISHING_X + wall_half, wall_y)


def draw_back_fog():
    """보스 뒤 안개 — 뒷벽 밑동과 그 앞 바닥에 깔린 뿌연 층 (최대 알파 약 0.3)."""
    fog = (70, 82, 110)
    dense = fog + (80,)
    clear = fog + (0,)
    wall_y = VANISHING_Y - CAMERA_HEIGHT * BACK_WALL_DEPTH
    wall_half = ROOM_HALF_WIDTH * BACK_WALL_DEPTH

    # 뒷벽 — 바닥에서 위로 옅어진다
    draw_polygon(
        (
            (VANISHING_X - wall_half, wall_y),
            (VANISHING_X + wall_half, wall_y),
            (VANISHING_X + wall_half, wall_y + 220),
            (VANISHING_X - wall_half, wall_y + 220),
        ),
        (dense, dense, clear, clear),
    )
    # 뒷벽 앞 바닥 — 카메라 쪽으로 옅어진다
    fog_near_depth = 0.56
    draw_polygon(
        (
            project(-ROOM_HALF_WIDTH, fog_near_depth),
            project(ROOM_HALF_WIDTH, fog_near_depth),
            project(ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
            project(-ROOM_HALF_WIDTH, BACK_WALL_DEPTH),
        ),
        (clear, clear, dense, dense),
    )
    # 보스 머리 뒤 은은한 후광 — 실루엣이 배경에서 떨어져 보이게
    halo_center = (VANISHING_X, VANISHING_Y - 90)
    segments = 24
    ring = [
        (
            halo_center[0] + 320 * math.cos(2 * math.pi * index / segments),
            halo_center[1] + 230 * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments + 1)
    ]
    draw_polygon(
        [halo_center] + ring,
        [fog + (50,)] + [clear] * (segments + 1),
    )


def draw_pillars():
    """좌우 기둥. 먼 것부터 그린다. 앞면 + 안쪽 옆면 + 바닥 그림자."""
    for depth in PILLAR_DEPTHS:
        back_depth = 1.0 / (1.0 / depth + PILLAR_THICKNESS)
        for side in (-1, 1):
            inner = side * PILLAR_INNER_X
            outer = side * PILLAR_OUTER_X
            shadow_depth = depth * 1.10

            # 바닥 그림자 — 뒤쪽 보스의 빛을 등지고 카메라 쪽으로 길게 눕는다
            draw_polygon(
                (
                    project(outer, depth),
                    project(inner, depth),
                    project(inner + side * 30, shadow_depth),
                    project(outer, shadow_depth),
                ),
                (
                    (5, 6, 10, 170),
                    (5, 6, 10, 170),
                    (5, 6, 10, 0),
                    (5, 6, 10, 0),
                ),
            )

            # 안쪽 옆면 — 화면 중앙을 향한 면. 어둡고 깊이 쪽으로 더 어둡다
            draw_polygon(
                (
                    project(inner, depth),
                    project(inner, back_depth),
                    project(inner, back_depth, CEILING_HEIGHT),
                    project(inner, depth, CEILING_HEIGHT),
                ),
                (
                    (24, 28, 40, 255),
                    (14, 16, 24, 255),
                    (8, 9, 14, 255),
                    (12, 14, 20, 255),
                ),
            )

            # 앞면 — 바닥 쪽이 밝고 위로 갈수록 어둠에 잠긴다
            front_bottom = (40, 46, 63, 255)
            front_top = (14, 16, 23, 255)
            inner_bottom = project(inner, depth)
            outer_bottom = project(outer, depth)
            inner_top = project(inner, depth, CEILING_HEIGHT)
            outer_top = project(outer, depth, CEILING_HEIGHT)
            draw_polygon(
                (inner_bottom, outer_bottom, outer_top, inner_top),
                (front_bottom, front_bottom, front_top, front_top),
            )

            # 수직 그림자 — 앞면 바깥쪽 1/3을 벽 쪽 그늘로 덮는다
            shade_edge = inner + (outer - inner) * 0.62
            draw_polygon(
                (
                    project(shade_edge, depth),
                    outer_bottom,
                    outer_top,
                    project(shade_edge, depth, CEILING_HEIGHT),
                ),
                (
                    (5, 6, 10, 0),
                    (5, 6, 10, 150),
                    (5, 6, 10, 150),
                    (5, 6, 10, 0),
                ),
            )

            # 받침돌
            plinth_height = 26
            plinth_inner = inner - side * 10
            plinth_depth = depth * 1.015
            draw_polygon(
                (
                    project(plinth_inner, plinth_depth),
                    project(outer, plinth_depth),
                    project(outer, plinth_depth, plinth_height),
                    project(plinth_inner, plinth_depth, plinth_height),
                ),
                ((30, 34, 47, 255), (22, 25, 35, 255), (44, 50, 68, 255), (54, 61, 82, 255)),
            )

            # 안쪽 모서리 빛
            set_draw_rgb(70, 80, 106, 130)
            draw_line(*inner_bottom, *inner_top)


def draw_pedestal():
    """보스 단상. 아랫단부터 그려야 윗단이 아랫단 윗면을 올바르게 가린다.

    카메라가 단상 정중앙 앞에 있으므로 수직 옆면은 보이지 않는다.
    옆면을 안쪽으로 기울여(경사) 위를 향하게 만들어 측면이 보이게 한다.
    """
    previous_elevation = 0
    for tier_index, (front, back, half_width, elevation, batter) in enumerate(
        PEDESTAL_TIERS
    ):
        top_half = half_width - batter
        light = 1.0 - 0.12 * tier_index

        def shade(rgb, factor):
            return tuple(round(channel * factor * light) for channel in rgb) + (255,)

        # 앞면 — 아랫변이 넓고 윗변이 좁은 사다리꼴
        front_bottom_left = project(-half_width, front, previous_elevation)
        front_bottom_right = project(half_width, front, previous_elevation)
        front_top_right = project(top_half, front, elevation)
        front_top_left = project(-top_half, front, elevation)
        back_top_right = project(top_half, back, elevation)
        back_top_left = project(-top_half, back, elevation)
        back_bottom_right = project(half_width, back, previous_elevation)
        back_bottom_left = project(-half_width, back, previous_elevation)

        # 옆면 — 경사가 위를 향해 카메라에 보인다. 앞면보다 어둡다
        side_near = shade((40, 46, 64), 0.85)
        side_far = shade((40, 46, 64), 0.55)
        draw_polygon(
            (front_bottom_left, front_top_left, back_top_left, back_bottom_left),
            (side_near, side_near, side_far, side_far),
        )
        draw_polygon(
            (front_bottom_right, back_bottom_right, back_top_right, front_top_right),
            (side_near, side_far, side_far, side_near),
        )

        # 윗면 — 가장 밝다
        top_near = shade((52, 59, 80), 1.0)
        top_far = shade((52, 59, 80), 0.7)
        draw_polygon(
            (front_top_left, front_top_right, back_top_right, back_top_left),
            (top_near, top_near, top_far, top_far),
        )

        # 앞면
        face_top = shade((34, 39, 55), 1.0)
        face_bottom = shade((34, 39, 55), 0.6)
        draw_polygon(
            (front_bottom_left, front_bottom_right, front_top_right, front_top_left),
            (face_bottom, face_bottom, face_top, face_top),
        )

        # 모서리 — 윗면 앞 모서리에 빛, 보스 쪽 붉은 기운
        set_draw_rgb(96, 108, 140, 150)
        draw_line(*front_top_left, *front_top_right)
        set_draw_rgb(70, 80, 106, 110)
        draw_line(*front_bottom_left, *front_top_left)
        draw_line(*front_bottom_right, *front_top_right)
        set_draw_color("accent", 40 + 25 * tier_index)
        draw_line(
            *project(-top_half * 0.6, front, elevation - 6),
            *project(top_half * 0.6, front, elevation - 6),
        )
        previous_elevation = elevation

    # 단상이 바닥에 드리우는 접지 그림자
    front, _, half_width, _, _ = PEDESTAL_TIERS[0]
    set_draw_rgb(6, 7, 11, 120)
    draw_polygon(
        (
            project(-half_width - 20, front * 1.03),
            project(half_width + 20, front * 1.03),
            project(half_width, front),
            project(-half_width, front),
        ),
        ((6, 7, 11, 0), (6, 7, 11, 0), (6, 7, 11, 140), (6, 7, 11, 140)),
    )


def draw_lane(lane_name,fill_color, edge_color, tick_count, opacity=0.85, saturation=0.7):
    lane = LANES[lane_name]
    layer_alpha = round(255 * opacity)
    near_left, near_right, far_right, far_left = lane_quad(lane_name)
    world_left = logical_to_world_x(0)
    world_right = logical_to_world_x(PLAYER_LOGICAL_WIDTH)
    # 옆면 아래 모서리 — 바닥(높이 0)이 아니라 윗면에서 두께만큼 아래
    base_elevation = lane["elevation"] - lane["thickness"]
    base_left = project(world_left, lane["near"], base_elevation)
    base_right = project(world_right, lane["near"], base_elevation)

    # 앞면(두께) — 윗면보다 어두운 같은 색, 아래로 갈수록 더 어둡다
    set_draw_color(fill_color, 255, saturation)
    fill_rgb = active_color[:3]
    set_draw_color(edge_color, 255, saturation)
    edge_rgb = active_color[:3]
    side_rgb = tuple(
        fill * 0.8 + edge * 0.2 for fill, edge in zip(fill_rgb, edge_rgb)
    )
    side_top = tuple(round(channel * 0.95) for channel in side_rgb) + (255,)
    side_bottom = tuple(round(channel * 0.6) for channel in side_rgb) + (255,)
    draw_polygon(
        (base_left, base_right, near_right, near_left),
        (side_bottom, side_bottom, side_top, side_top),
    )
    set_draw_color(edge_color, 70, saturation)
    draw_line(*base_left, *base_right)
    draw_line(*base_left, *near_left)
    draw_line(*base_right, *near_right)

    # 윗면 — 카메라 쪽이 조금 더 밝다
    set_draw_color(fill_color, layer_alpha, saturation)
    far_rgba = active_color
    near_rgba = tuple(min(255, round(channel * 1.25)) for channel in far_rgba[:3]) + (
        layer_alpha,
    )
    draw_polygon(
        (near_left, near_right, far_right, far_left),
        (near_rgba, near_rgba, far_rgba, far_rgba),
    )

    set_draw_color(edge_color, layer_alpha, saturation)
    draw_polyline((near_left, near_right, far_right, far_left))
    center_left = lane_point(lane_name, 0)
    center_right = lane_point(lane_name, PLAYER_LOGICAL_WIDTH)
    draw_line(*center_left, *center_right)

    # 분할선 — 소실점을 향해 기운다
    inset = 0.06
    near_depth = lane["near"] - (lane["near"] - lane["far"]) * inset
    far_depth = lane["far"] + (lane["near"] - lane["far"]) * inset
    for tick in range(1, tick_count):
        logical_x = PLAYER_LOGICAL_WIDTH * tick / tick_count
        draw_line(
            *lane_point(lane_name, logical_x, near_depth),
            *lane_point(lane_name, logical_x, far_depth),
        )

    marker_radius = max(3, int(5 * lane["scale"]))
    for logical_x in (18, PLAYER_LOGICAL_WIDTH - 18):
        draw_filled_circle(*lane_point(lane_name, logical_x), marker_radius)


def draw_boss_placeholder(
    awakened=False,
    hit=False,
    defeated=False,
    pose="idle",
    forward_progress=0.0,
    center_x=640,
    base_foot_y=370,
):
    awakening_scale = BossController.AWAKENING_SIZE_SCALE if awakened else 1.0
    lunge_scale = 1.0 + (1.05 / 0.78 - 1.0) * forward_progress
    # 각성은 40px, 돌진은 깊이를 따라 앞으로 끌려 나온다 (BOSS1_SPEC §2)
    foot_y = base_foot_y - (40 if awakened else 0)
    desired_scale = BOSS_DISPLAY_SCALE * max(awakening_scale, lunge_scale)
    visible_height = 214
    max_visible_scale = (BOSS_CEILING_Y - foot_y) / visible_height
    scale = min(desired_scale, max_visible_scale)
    body_half_width = 42 * scale
    body_bottom = foot_y + 34 * scale
    body_top = foot_y + 142 * scale
    head_y = foot_y + 166 * scale

    def set_boss_color(color_name):
        # 대기 원근: 채도 0.4 → 0.32 (20% 낮춤), 블루 틴트 0.45 → 0.55
        set_draw_color(color_name, round(255 * 0.6), 0.32, 0.55)

    set_boss_color("shadow")
    draw_filled_ellipse(
        center_x,
        foot_y + 2,
        96 * scale,
        16 * scale,
    )

    body_color = "flash" if hit else ("wall_light" if defeated else "actor_dark")
    set_boss_color("actor_dark")
    draw_filled_rectangle(
        center_x - body_half_width - 8 * scale,
        body_bottom - 8 * scale,
        center_x + body_half_width + 8 * scale,
        body_top + 8 * scale,
    )
    draw_filled_circle(center_x, head_y, 34 * scale)

    set_boss_color(body_color)
    draw_filled_rectangle(
        center_x - body_half_width,
        body_bottom,
        center_x + body_half_width,
        body_top,
    )
    draw_filled_circle(center_x, head_y, 27 * scale)

    set_boss_color("actor_dark")
    horn_start_y = min(head_y + 18 * scale, BOSS_CEILING_Y)
    horn_end_y = min(head_y + 48 * scale, BOSS_CEILING_Y)
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
        hand_limit = BOSS_CEILING_Y - 9 * scale
        draw_arm(-1, 58, min(foot_y + 177 * scale, hand_limit - 9 * scale), 64, min(foot_y + 220 * scale, hand_limit))
        draw_arm(1, 58, foot_y + 105 * scale, 75, foot_y + 78 * scale)
    elif pose == "slam_double":
        hand_limit = BOSS_CEILING_Y - 9 * scale
        raised_elbow_y = min(foot_y + 177 * scale, hand_limit - 9 * scale)
        raised_hand_y = min(foot_y + 220 * scale, hand_limit)
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

    set_boss_color("accent")
    draw_line(center_x - 22 * scale, body_top - 36 * scale, center_x + 22 * scale, body_top - 36 * scale)
    draw_line(center_x - 24 * scale, body_top - 46 * scale, center_x + 24 * scale, body_top - 46 * scale)
    set_boss_color("accent_light" if awakened else "accent")
    draw_filled_circle(center_x - 10 * scale, head_y, 4 * scale)
    draw_filled_circle(center_x + 10 * scale, head_y, 4 * scale)


def draw_player_placeholder(screen_x, foot_y, scale):
    head_radius = 12 * scale
    body_half_width = 13 * scale
    body_bottom = foot_y + 17 * scale
    body_top = foot_y + 56 * scale
    shoulder_y = foot_y + 49 * scale

    set_draw_color("shadow", 170, 0.7)
    draw_filled_ellipse(
        screen_x,
        foot_y + 3 * scale,
        24 * scale,
        8 * scale,
    )

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
        self.trigger_impact_flash(
            *lane_point(self.player_lane, self.player_logical_x)
        )
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
            impact_x = boss_attack.target_x
            if impact_x is None:
                impact_x = BOSS_LOGICAL_X
            self.trigger_screen_shake(shake_strength, shake_duration)
            self.trigger_impact_flash(
                *lane_point(boss_attack.target_lane or self.player_lane, impact_x)
            )
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

        draw_void()
        draw_pedestal()
        boss_pose = "idle"
        if self.boss.current_pattern is not None:
            boss_pose = PATTERNS[self.boss.current_pattern]["pose"]
            if self.boss.state in ("active", "recovery"):
                if self.boss.current_pattern in ("slam", "slam_double"):
                    boss_pose = "slam_impact"
                elif self.boss.current_pattern == "shockwave":
                    boss_pose = "shockwave_impact"

        boss_screen_x, boss_foot_y, _ = boss_anchor(
            self.boss.position_x,
            self.boss.forward_progress,
        )
        draw_boss_placeholder(
            self.boss.awakened,
            self.boss_hit_timer > 0,
            self.boss_defeated,
            boss_pose,
            self.boss.forward_progress,
            boss_screen_x,
            boss_foot_y,
        )

        draw_lane("platform_1", "front_lane", "front_edge", 8)
        draw_lane("platform_2", "rear_lane", "rear_edge", 10)

        self.draw_boss_status()
        self.draw_seal_gauge()
        self.draw_boss_telegraph()
        self.draw_homing_projectile()
        self.draw_active_boss_effects()
        self.draw_impact_flash()

        lane = LANES[self.player_lane]
        player_scale = lane["scale"]
        player_elevation = lane["elevation"]

        if self.lane_transition_target is not None:
            target_lane = LANES[self.lane_transition_target]
            progress = min(
                self.lane_transition_elapsed / LANE_SWITCH_DURATION,
                1.0,
            )
            player_scale += (target_lane["scale"] - player_scale) * progress
            player_elevation += (
                target_lane["elevation"] - player_elevation
            ) * progress

        screen_x, player_y = project(
            logical_to_world_x(self.player_logical_x),
            player_scale,
            player_elevation,
        )
        platform_scale = logical_pixels(player_scale)
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
            set_draw_color("accent_light")
            draw_rectangle(
                screen_x - 25 * player_scale,
                player_y,
                screen_x + 25 * player_scale,
                player_y + 90 * player_scale,
            )

            if self.player_lane == "platform_1":
                boss_screen_x = screen_x + (
                    self.boss.position_x - self.player_logical_x
                ) * platform_scale
                boss_half_width = BOSS_HITBOX_HALF_WIDTH * platform_scale
                set_draw_color("accent")
                draw_rectangle(
                    boss_screen_x - boss_half_width,
                    player_y,
                    boss_screen_x + boss_half_width,
                    player_y + 90 * player_scale,
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
                        screen_x + (attack_left - self.player_logical_x) * platform_scale,
                        player_y + 20 * player_scale,
                        screen_x + (attack_right - self.player_logical_x) * platform_scale,
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
            quad = lane_quad(self.boss.target_lane)
            set_draw_color("accent", fill_alpha)
            draw_polygon(quad)
            set_draw_color("accent_light")
            draw_polyline(quad)
            return

        if pattern["marker"] == "column":
            half_width = pattern["hitbox_width"] * 0.5
            left = self.boss.target_x - half_width
            right = self.boss.target_x + half_width
            for lane_name in ("platform_1", "platform_2"):
                quad = lane_quad(lane_name, left, right)
                set_draw_color("accent", fill_alpha)
                draw_polygon(quad)
                set_draw_color("accent_light", 255 if visible else 45)
                draw_polyline(quad)
            return

        targets = [(self.boss.target_lane, self.boss.target_x)]
        if pattern["marker"] == "two_spots":
            targets.append(("platform_1", self.boss.secondary_target_x))

        for target_lane_name, target_x in targets:
            target_lane = LANES[target_lane_name]
            scale = logical_pixels(target_lane["scale"])
            screen_x, screen_y = lane_point(target_lane_name, target_x)
            growth = 1.0 - 0.5 * progress
            set_draw_color("accent", marker_alpha)
            draw_filled_ellipse(
                screen_x,
                screen_y,
                80 * growth * scale,
                18 * growth * target_lane["scale"],
            )
            set_draw_color("accent_light", 255 if visible else 45)
            draw_rectangle(
                screen_x - 2,
                screen_y - 3,
                screen_x + 2,
                screen_y + 3,
            )

    def draw_homing_projectile(self):
        if self.boss.current_pattern != "homing" or self.boss.state != "active":
            return

        target_x, target_y = lane_point(self.boss.target_lane, self.boss.target_x)
        progress = min(
            self.boss.attack_elapsed / PATTERNS["homing"]["duration"],
            1.0,
        )
        boss_screen_x, boss_foot_y, _ = boss_anchor(
            self.boss.position_x,
            self.boss.forward_progress,
        )
        launch_y = boss_foot_y + 220
        projectile_x = boss_screen_x + (target_x - boss_screen_x) * progress
        projectile_y = launch_y + (target_y - launch_y) * progress

        set_draw_color("accent", 100)
        draw_filled_ellipse(
            target_x,
            target_y,
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
            # 돌진 진행선 — 보스 발치에서 카메라 쪽까지 바닥을 따라 이어지는 빛의 띠
            fade = 1.0 - 0.6 * progress
            half_width = pattern["hitbox_width"] * 0.5
            left = logical_to_world_x(self.boss.target_x - half_width)
            right = logical_to_world_x(self.boss.target_x + half_width)
            far_alpha = round(230 * fade)
            near_alpha = round(110 * fade)
            far_color = (255, 244, 224, far_alpha)
            near_color = (255, 214, 170, near_alpha)
            draw_polygon(
                (
                    project(left, LANES["platform_2"]["near"]),
                    project(right, LANES["platform_2"]["near"]),
                    project(right, BOSS_CHARGE_DEPTH),
                    project(left, BOSS_CHARGE_DEPTH),
                ),
                (near_color, near_color, far_color, far_color),
            )
            for lane_name in ("platform_1", "platform_2"):
                lane = LANES[lane_name]
                draw_polygon(
                    lane_quad(
                        lane_name,
                        self.boss.target_x - half_width,
                        self.boss.target_x + half_width,
                    ),
                    (near_color, near_color, far_color, far_color),
                )
                set_draw_color("flash", far_alpha)
                for edge in (left, right):
                    draw_line(
                        *project(edge, lane["near"], lane["elevation"]),
                        *project(edge, lane["far"], lane["elevation"]),
                    )
        elif pattern["marker"] == "lane":
            # 충격파 벽 — 레인 위에 서서 양옆으로 퍼지는 흰–주황 벽
            lane = LANES[self.boss.target_lane]
            elevation = lane["elevation"]
            wall_height = 70
            wave_offset = PLAYER_LOGICAL_WIDTH * 0.5 * progress
            half_width = 10
            base_color = (255, 244, 224, 235)
            top_color = (255, 107, 53, 0)
            side_base = (255, 190, 140, 200)
            for direction in (-1, 1):
                center = BOSS_LOGICAL_X + direction * wave_offset
                inner = logical_to_world_x(center - direction * half_width)
                outer = logical_to_world_x(center + direction * half_width)
                # 레인 깊이를 따라 선 얇은 벽의 바깥쪽 면
                draw_polygon(
                    (
                        project(outer, lane["near"], elevation),
                        project(outer, lane["far"], elevation),
                        project(outer, lane["far"], elevation + wall_height),
                        project(outer, lane["near"], elevation + wall_height),
                    ),
                    (side_base, side_base, top_color, top_color),
                )
                # 카메라를 향한 앞면
                draw_polygon(
                    (
                        project(inner, lane["near"], elevation),
                        project(outer, lane["near"], elevation),
                        project(outer, lane["near"], elevation + wall_height),
                        project(inner, lane["near"], elevation + wall_height),
                    ),
                    (base_color, base_color, top_color, top_color),
                )
                # 벽이 지나간 자리의 바닥 잔광
                trail = logical_to_world_x(center - direction * 60)
                draw_polygon(
                    (
                        project(trail, lane["near"], elevation),
                        project(outer, lane["near"], elevation),
                        project(outer, lane["far"], elevation),
                        project(trail, lane["far"], elevation),
                    ),
                    (
                        (255, 107, 53, 0),
                        (255, 200, 150, 120),
                        (255, 200, 150, 120),
                        (255, 107, 53, 0),
                    ),
                )
        elif pattern["marker"] == "two_spots" and self.boss.next_hit_index == 1:
            lane = LANES["platform_1"]
            scale = logical_pixels(lane["scale"])
            target_x, target_y = lane_point("platform_1", self.boss.secondary_target_x)
            marker_progress = min(progress / 0.65, 1.0)
            set_draw_color("accent_light", int(90 + 110 * marker_progress))
            draw_filled_ellipse(
                target_x,
                target_y,
                80 * (1.0 - 0.5 * marker_progress) * scale,
                18 * (1.0 - 0.5 * marker_progress) * lane["scale"],
            )

    def draw_impact_flash(self):
        if self.impact_flash_timer <= 0:
            return
        x, y = self.impact_flash_position
        remaining = min(self.impact_flash_timer / 0.08, 1.0)
        spread = 1.0 - remaining
        # 바닥에 납작하게 퍼지는 착탄 고리 + 위로 솟는 짧은 섬광
        set_draw_color("flash", int(200 * remaining))
        draw_filled_ellipse(x, y, 40 + 50 * spread, 10 + 12 * spread)
        draw_polygon(
            (
                (x - 14, y),
                (x + 14, y),
                (x + 4, y + 60 + 40 * spread),
                (x - 4, y + 60 + 40 * spread),
            ),
            (
                (255, 244, 224, int(220 * remaining)),
                (255, 244, 224, int(220 * remaining)),
                (255, 244, 224, 0),
                (255, 244, 224, 0),
            ),
        )

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
