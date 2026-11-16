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
# 사망 패널티: 부활할 때 게이지를 보스 쪽으로 이만큼 민다 (게이지는 리셋하지 않고 이어받는다).
#   이게 없으면 체력 1칸·게이지 열세일 때 일부러 죽어 체력 3칸을 받는 게 이득이 된다.
#   0.15 = 피격 1회(BOSS_HIT_LOSS)와 같은 양 — 죽기 직전보다 한 대 더 맞은 지점에서 재개
DEATH_GAUGE_PENALTY = 0.15
DEBUG_GAUGE_STEP = 0.05
# 평시 보스가 화면에서 차지하는 높이(매몰선 ~ 뿔 끝, 줌 1.0 기준). 화면 720의 약 47%.
#   예전 배율 1.5 고정(≈200px, 28%)은 앞줄에서 보기에 보스가 멀고 작아 근접 공격이 닿는
#   것이 납득되지 않았다. 매몰선(≈183)부터 위로 340px → 머리 끝 ≈ 523
BOSS_SCREEN_HEIGHT = 340
# 각성 시 크기 배율 1.4 → 1.1: 화면 절반 크기에서는 1.4배로 키울 자리가 없다 (천장에 막힘).
#   각성은 전진(BOSS_AWAKENED_DEPTH)과 붉은 역광으로 보여 주고 크기는 살짝만 키운다
BOSS_AWAKENED_SIZE_SCALE = 1.1
# 평시 ↔ 각성 연출 전환 시간. 즉시 바꾸면 보스가 한 프레임에 튀어 나와 순간이동처럼 보인다
BOSS_AWAKEN_BLEND_TIME = 0.5
# 플레이어 림 라이트 (draw_player_placeholder 참고). 보스 몸통 앞에서도 윤곽이 보이게
PLAYER_RIM_PX = 2
PLAYER_RIM_RGBA = (150, 180, 225, 200)
# 보스 실루엣(뿔·치켜든 손 포함)의 상한. 게이지 바 아랫변 650보다 충분히 아래 (조건: < 630).
#   돌진(최대 1.35배)·각성 중 커지는 몫은 여기서 잘린다
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
#   보스 매몰선 y≈330을 정하는 값이라 플랫폼 위치는 LANES의 elevation으로 맞춘다
VANISHING_Y = 583
# 580 → 520: 소실점을 내리면서 카메라도 낮춰 레인 간격을 유지한다.
#   두 플랫폼 세로 합계 ≈ 120px (< 720의 45%)
CAMERA_HEIGHT = 520
# 플랫폼 좌우 폭 (뒷줄 1180px, 앞줄 838px). 그리기 전용 — 판정은 논리 x 0~900
LANE_HALF_WIDTH = 590
ROOM_HALF_WIDTH = 760
ROOM_NEAR_DEPTH = 1.6
BACK_WALL_DEPTH = 0.40
CEILING_HEIGHT = 1100
# 0.55 → 0.63: 보스를 앞줄 바로 뒤까지 당긴다 (앞줄 먼 모서리 0.674보다 약간 뒤).
#   매몰선 = 583 - (520 + 115) * 0.63 ≈ 183 → 앞줄 먼 모서리(≈162) 바로 위.
#   앞줄에 선 플레이어(머리 ≈ 200)와 보스 몸통이 화면에서 겹쳐 근접 공격이 납득된다
BOSS_DEPTH = 0.63
# 각성 시 한 단계 더 앞으로 (매몰선 183 → 170). 앞줄 먼 모서리(0.674)를 넘지 않는다
BOSS_AWAKENED_DEPTH = 0.65
# 0.57 → 0.66 (= 맨 윗단 앞 모서리 0.662 안쪽): 예전 값은 새 BOSS_DEPTH보다 작아 돌진하면
#   오히려 뒤로 물러났다. 보스는 단상 맨 윗단을 벗어나지 않으므로 윗단 앞 끝에서 멈추고,
#   앞으로 덮쳐 오는 느낌은 돌진 배율(최대 1.35배)과 상체 기울기가 만든다
BOSS_CHARGE_DEPTH = 0.66

# 보스 단상 — 3단 계단. 카메라 쪽(아래)에서 보스 쪽(위)으로 올라간다.
# (앞 깊이, 뒤 깊이, 반폭, 윗면 높이, 옆면 경사폭)
# 보스를 앞줄 바로 뒤로 당기면서 단상도 앞줄 뒤에 붙였다 (예전 깊이 0.53~0.64, 높이 20~60).
#   윗면 높이 60 → -115: 보스 발치가 앞줄 먼 모서리 바로 위에 와야 플레이어와 겹친다.
#   아랫단 두 개의 앞면은 앞줄 뒤에 숨는다 (앞줄 먼 모서리 깊이 0.674).
# 맨 윗단 깊이 0.560~0.662: 평시(0.63)·각성(0.65)·돌진(0.66) 보스가 모두 이 안에 있다.
#   뒤 깊이를 넉넉히(0.56) 둬 윗면이 보스 좌우로 띠처럼 보이게 한다 (y ≈ 164~227)
# 반폭 전부 760(= 옆벽): 보스는 중앙에 결박되고 상체만 기운다(charge_lean_x)
PEDESTAL_TIERS = (
    (0.674, 0.540, 760, -135, 10),
    (0.668, 0.550, 760, -125, 10),
    (0.662, 0.560, 760, -115, 10),
)
PEDESTAL_TOP_ELEVATION = PEDESTAL_TIERS[-1][3]
# 돌진 중에도 보스는 맨 윗단 높이에 묻혀 있다 (예전: 맨 아랫단 20까지 내려옴)
BOSS_CHARGE_ELEVATION = PEDESTAL_TOP_ELEVATION
# -140 → -200: 단상을 -135까지 내렸으므로 밑동도 그보다 아래로 늘려 앞줄 뒤에 숨긴다
PEDESTAL_BASE_ELEVATION = -200

# 좌우 벽 기둥 — 레인과 겹치지 않는 깊이(레인 사이, 단상 옆, 뒷벽 앞)에 둔다
# 가운데 기둥 0.62 → 0.70, 앞 기둥 0.86 → 0.90: 넓힌 단상 맨 아랫단(깊이 0.53~0.64,
#   반폭 720)과 0.62 기둥이 겹쳤다. 단상 앞(0.64)보다 앞으로 옮기고 간격을 맞췄다
PILLAR_DEPTHS = (0.46, 0.70, 0.90)
PILLAR_INNER_X = 660
PILLAR_OUTER_X = 750
PILLAR_THICKNESS = 0.14  # 깊이 방향 두께 (1/s 단위)

LANES = {
    "platform_2": {
        # 1.10/0.90 → 1.05/0.95: 플랫폼 깊이(앞뒤 길이)를 줄인다. 화면상 윗면 ≈ 55px.
        #   중심 깊이 1.0(= scale)은 그대로라 캐릭터 크기·판정 비율은 같다
        "near": 1.05,
        "far": 0.95,
        "scale": 1.0,
        # 22 → -25: 화면 하단에 붙인다. 옆면 밑변 = 583 - (520 + 35) * 1.05 ≈ 0,
        #   앞 모서리 ≈ 11, 먼 모서리 ≈ 65
        "elevation": -25,
        # 보이드 위에 뜬 판의 두께. elevation(띄운 높이)과 분리한다
        "thickness": 10,
    },
    "platform_1": {
        # 0.78/0.645 → 0.746/0.674: 깊이를 줄인다. 화면상 윗면 ≈ 45px. 중심 0.71 유지
        "near": 0.746,
        "far": 0.674,
        "scale": 0.71,
        # 36 → -104: 뒷줄을 따라 내려가며 빈틈 ≈ 46px을 유지한다.
        #   옆면 밑변 = 583 - (520 + 112) * 0.746 ≈ 111, 먼 모서리 ≈ 162
        "elevation": -104,
        # 멀리 있어 화면에서 더 얇아 보이도록 뒷줄보다 조금 얇게
        "thickness": 8,
    },
}


# ---------------------------------------------------------------------------
# 레인별 카메라 줌 — 소실점(VANISHING_X, VANISHING_Y)을 중심으로 화면 전체를 확대한다.
# 뒷줄 1.00: 기본 구도. 두 플랫폼·대좌·보스가 다 들어오는 전체 화면.
# 앞줄 1.12: 보스 쪽으로 다가간 긴장감. 12%면 앞줄 양 끝(논리 0/900)이 화면 x 171~1109로
#   여전히 화면 안에 있고, 보스 머리(천장 615 → 619)도 게이지 바(650) 아래에 남는다.
#   더 키우면 앞줄 끝이 가장자리에 붙고 뒷줄이 화면 아래로 크게 잘린다.
# 0.30초: 레인 전환(0.25초)보다 조금 길게 — 몸이 먼저 도착하고 카메라가 뒤따라온다.
# UI(게이지·체력·디버그·상태 텍스트)는 project()를 쓰지 않으므로 줌에서 제외된다.
# ---------------------------------------------------------------------------
LANE_VIEW_ZOOM = {"platform_2": 1.00, "platform_1": 1.12}
VIEW_ZOOM_DURATION = 0.30
view_zoom = 1.0

# ---------------------------------------------------------------------------
# 좌우 카메라 추적 — 소실점(VANISHING_X)이 아니라 카메라의 월드 x를 옮긴다.
# 화면 이동량 = camera_x * depth 라서 가까운 것(뒷줄 1.0)은 많이, 먼 것(보스 0.55,
# 뒷벽 0.40)은 적게 흐른다. 소실점을 옮기면 깊이와 무관하게 전부 똑같이 밀려 입체감이 없다.
# CAMERA_FOLLOW 0.28: 플레이어 월드 x의 28%만 따라간다. 요청값 0.30이면 앞줄(줌 1.12)
#   끝에서 보스가 중앙에서 103px 벗어나 기준(100px 이내)을 넘는다. 0.28이면 최대 96px.
#   너무 크면 플레이어가 화면 중앙에 붙어 좌우 이동이 안 보이고, 너무 작으면 흐름이 안 보인다.
# CAMERA_FOLLOW_TIME 0.12초: 지수 감쇠 시정수. 즉시 따라가면 카메라가 아니라 플레이어에
#   붙은 것처럼 보인다. 0.12초면 이동을 멈춘 뒤 약 0.36초 안에 95% 따라붙는다.
# ---------------------------------------------------------------------------
CAMERA_FOLLOW = 0.28
CAMERA_FOLLOW_TIME = 0.12
camera_x = 0.0


def zoom_point(x, y):
    """화면 좌표 한 점에 줌을 적용한다 (소실점 중심)."""
    return (
        VANISHING_X + (x - VANISHING_X) * view_zoom,
        VANISHING_Y + (y - VANISHING_Y) * view_zoom,
    )


def zoom_y(y):
    return VANISHING_Y + (y - VANISHING_Y) * view_zoom


def project_unzoomed(world_x, depth, elevation=0.0):
    return (
        VANISHING_X + world_x * depth,
        VANISHING_Y - (CAMERA_HEIGHT - elevation) * depth,
    )


def project(world_x, depth, elevation=0.0):
    # 순서: 카메라 오프셋(월드 단계) → 투영 → 줌(화면 단계, 소실점 중심).
    # 줌을 먼저 하면 줌 중심이 플레이어를 따라다녀 어지럽다
    return zoom_point(*project_unzoomed(world_x - camera_x, depth, elevation))


def wall_center_x():
    """뒷벽(깊이 BACK_WALL_DEPTH) 위의 화면 중앙 x — 카메라 이동이 깊이만큼 반영된다."""
    return VANISHING_X - camera_x * BACK_WALL_DEPTH


def logical_to_world_x(logical_x):
    return (logical_x / PLAYER_LOGICAL_WIDTH - 0.5) * 2 * LANE_HALF_WIDTH


def logical_pixels(depth):
    """논리 x 1이 해당 깊이에서 화면 몇 px인지 (카메라 줌 포함)."""
    return 2 * LANE_HALF_WIDTH / PLAYER_LOGICAL_WIDTH * depth * view_zoom


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


def pedestal_surface_elevation(world_x, depth):
    """(world_x, depth) 바로 아래 단상 윗면 높이. 단상 밖이면 None."""
    surface = None
    for front, back, half_width, elevation, batter in PEDESTAL_TIERS:
        on_tier = back - 1e-9 <= depth <= front + 1e-9
        if on_tier and abs(world_x) <= half_width - batter + 1e-9:
            surface = elevation if surface is None else max(surface, elevation)
    return surface


def boss_burial_elevation(world_x, depth, forward_progress, footprint_half=0.0):
    """보스 매몰선의 높이.

    예전에는 항상 맨 윗단 높이(60)였다. 돌진으로 깊이가 0.57을 넘으면 발밑은
    아랫단(40, 20)인데 보스는 60에 떠 있었다. 이제 평시 60 → 돌진 끝 20으로
    내려오되, 흙더미 폭(footprint_half) 아래 가장 낮은 단상 윗면보다 절대 높지
    않게 한다. 낮은 것은 더 깊이 묻힌 것이라 괜찮고, 높은 것은 허공에 뜬 것이다.
    """
    elevation = PEDESTAL_TOP_ELEVATION + (
        BOSS_CHARGE_ELEVATION - PEDESTAL_TOP_ELEVATION
    ) * forward_progress
    for sample_x in (world_x - footprint_half, world_x, world_x + footprint_half):
        surface = pedestal_surface_elevation(sample_x, depth)
        if surface is not None:
            elevation = min(elevation, surface)
    return elevation


# 돌진 조준 기울기를 화면에 그릴 비율 (조준 오프셋의 절반만큼 상체가 기운다)
BOSS_LEAN_DRAW_RATIO = 0.5

# 매몰선 흙더미의 반폭 (보스 배율 단위). draw_boss_placeholder와 boss_anchor가 같이 쓴다
BOSS_MOUND_HALF_WIDTH = 66
BOSS_BODY_OFFSET = 34
BOSS_VISIBLE_HEIGHT = 214 - BOSS_BODY_OFFSET


def boss_home_depth(awakened):
    """돌진 전 보스 깊이. awakened는 0~1 연출 진행도(bool도 된다)."""
    return BOSS_DEPTH + (BOSS_AWAKENED_DEPTH - BOSS_DEPTH) * float(awakened)


def boss_depth_at(forward_progress, awakened=False):
    home = boss_home_depth(awakened)
    return home + (BOSS_CHARGE_DEPTH - home) * forward_progress


def boss_desired_scale(awakened, forward_progress):
    """천장 제한 전 보스 배율.

    평시 BOSS_DEPTH에서 BOSS_SCREEN_HEIGHT가 되도록 정하고, 깊이에 비례해 키운다
    (각성·돌진으로 앞으로 나오면 원근만큼 커진다). 각성은 1.1배를 더 곱한다.
    """
    awakening_scale = 1.0 + (BOSS_AWAKENED_SIZE_SCALE - 1.0) * float(awakened)
    lunge_scale = 1.0 + (1.05 / 0.78 - 1.0) * forward_progress
    base_scale = BOSS_SCREEN_HEIGHT / BOSS_VISIBLE_HEIGHT
    depth_scale = boss_depth_at(forward_progress, awakened) / BOSS_DEPTH
    return base_scale * depth_scale * max(awakening_scale, lunge_scale)


def boss_anchor(position_x, forward_progress, awakened=False):
    """보스 발치(매몰선)의 화면 좌표와 깊이. 보스는 발밑 단상 윗면에 묻혀 있다."""
    depth = boss_depth_at(forward_progress, awakened)
    world_x = logical_to_world_x(position_x)
    footprint_half = (
        BOSS_MOUND_HALF_WIDTH * boss_desired_scale(awakened, forward_progress) / depth
    )
    elevation = boss_burial_elevation(world_x, depth, forward_progress, footprint_half)
    x, y = project(world_x, depth, elevation)
    return x, y, depth


# 평시 보스 매몰선의 화면 y (≈183)
BOSS_HOME_BURIAL_Y = project_unzoomed(0, BOSS_DEPTH, PEDESTAL_TOP_ELEVATION)[1]


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


def set_clip_above(y):
    """캔버스 y 이상만 그리게 클립한다 (pico2d 좌하단 원점 → SDL 좌상단 원점)."""
    renderer = _pico2d_state.get("renderer")
    if renderer is None:
        return
    height = max(0, int(round(HEIGHT - (y + DRAW_OFFSET_Y))))
    sdl2.SDL_RenderSetClipRect(renderer, sdl2.SDL_Rect(0, 0, WIDTH, height))


def clear_clip():
    renderer = _pico2d_state.get("renderer")
    if renderer is not None:
        sdl2.SDL_RenderSetClipRect(renderer, None)


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


def draw_thick_line(x1, y1, x2, y2, start_width, end_width=None):
    """두께가 있는 선(끝으로 갈수록 가늘어질 수 있음)을 사각 폴리곤으로 그린다."""
    if end_width is None:
        end_width = start_width
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1e-6:
        return
    normal_x = -(y2 - y1) / length
    normal_y = (x2 - x1) / length
    half_start = start_width * 0.5
    half_end = end_width * 0.5
    draw_polygon(
        (
            (x1 + normal_x * half_start, y1 + normal_y * half_start),
            (x2 + normal_x * half_end, y2 + normal_y * half_end),
            (x2 - normal_x * half_end, y2 - normal_y * half_end),
            (x1 - normal_x * half_start, y1 - normal_y * half_start),
        )
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


def draw_radial_glow(center_x, center_y, radius_x, radius_y, rgb, alpha, segments=28):
    """가운데가 진하고 가장자리로 갈수록 투명해지는 타원 발광."""
    ring = [
        (
            center_x + radius_x * math.cos(2 * math.pi * index / segments),
            center_y + radius_y * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments + 1)
    ]
    draw_polygon(
        [(center_x, center_y)] + ring,
        [tuple(rgb) + (alpha,)] + [tuple(rgb) + (0,)] * (segments + 1),
    )


def draw_soft_panel(left, bottom, right, top, feather, rgb, alpha):
    """가장자리 feather px에 걸쳐 투명해지는 사각 발광 패널."""
    solid = tuple(rgb) + (alpha,)
    clear = tuple(rgb) + (0,)
    inner = ((left, bottom), (right, bottom), (right, top), (left, top))
    outer = (
        (left - feather, bottom - feather),
        (right + feather, bottom - feather),
        (right + feather, top + feather),
        (left - feather, top + feather),
    )
    draw_polygon(inner, (solid,) * 4)
    # 네 변을 사다리꼴로 감싼다. 모서리는 대각선으로 맞물린다
    for index in range(4):
        following = (index + 1) % 4
        draw_polygon(
            (inner[index], inner[following], outer[following], outer[index]),
            (solid, solid, clear, clear),
        )


# 보스 역광 — 실루엣을 배경에서 떼어 내는 뒷벽 발광.
# 평시: 어두운 청회색, 약하게. 보스(#0A0C10)와 벽(≈#181C28) 사이 명도 차를 벌릴 만큼만.
# 각성: 붉게, 알파 55 → 140 (약 2.5배). 크기를 1.4배로 키울 자리가 없어져서
#   게이지 바를 안 봐도 각성이 읽히도록 배경 쪽에서 색과 밝기로 구분한다
BOSS_BACKLIGHT = ((70, 86, 120), 55)
BOSS_AWAKENED_BACKLIGHT = ((200, 34, 44), 140)
# 패널 반폭 150 → 330, 아래 끝 뒷벽 바닥 → 단상 윗면 근처(y 190):
#   보스가 화면 절반 크기(어깨·팔 반폭 ≈ 170~230px, 매몰선 ≈ 183)로 커져 예전 패널을
#   다 가렸다. 보스보다 넓고 길게 깔아야 어깨·팔·뿔 윤곽이 산다
BOSS_BACKLIGHT_HALF_WIDTH = 330
BOSS_BACKLIGHT_BOTTOM_Y = 190


def draw_boss_backlight(awakened=0.0):
    """보스보다 먼저 그리는 뒷벽 역광 패널 + 머리 뒤 발광. awakened: 0~1 전환 진행도."""
    (calm_rgb, calm_alpha), (awake_rgb, awake_alpha) = (
        BOSS_BACKLIGHT,
        BOSS_AWAKENED_BACKLIGHT,
    )
    t = max(0.0, min(float(awakened), 1.0))
    rgb = tuple(round(a + (b - a) * t) for a, b in zip(calm_rgb, awake_rgb))
    alpha = round(calm_alpha + (awake_alpha - calm_alpha) * t)
    # 보스 깊이 화면 x — 보스와 같은 양만큼 카메라를 따라가야 역광이 보스 뒤에 머문다
    center_x = VANISHING_X - camera_x * BOSS_DEPTH
    panel_left, panel_bottom = zoom_point(
        center_x - BOSS_BACKLIGHT_HALF_WIDTH, BOSS_BACKLIGHT_BOTTOM_Y
    )
    panel_right, panel_top = zoom_point(
        center_x + BOSS_BACKLIGHT_HALF_WIDTH, HEIGHT - 100
    )
    draw_soft_panel(
        panel_left,
        panel_bottom,
        panel_right,
        panel_top,
        120 * view_zoom,
        rgb,
        alpha // 2,
    )
    # 머리·어깨 뒤에 더 진한 타원 — 윤곽선이 가장 중요한 부분을 밝힌다 (보스에 맞춰 키움)
    draw_radial_glow(
        *zoom_point(center_x, BOSS_HOME_BURIAL_Y + 0.75 * BOSS_SCREEN_HEIGHT),
        400 * view_zoom,
        260 * view_zoom,
        rgb,
        alpha,
    )


def draw_room(with_floor=True):
    """뒷벽·좌우 벽, 그리고 with_floor면 바닥과 격자까지.

    플랫폼을 보이드에 띄우는 지금은 with_floor=False로 벽만 그린다.
    """
    wall_y = VANISHING_Y - CAMERA_HEIGHT * BACK_WALL_DEPTH
    wall_half = ROOM_HALF_WIDTH * BACK_WALL_DEPTH

    # 뒷벽 — 위로 갈수록 어두워지는 수직 그라데이션
    draw_polygon(
        (
            zoom_point(wall_center_x() - wall_half, wall_y),
            zoom_point(wall_center_x() + wall_half, wall_y),
            zoom_point(wall_center_x() + wall_half, HEIGHT),
            zoom_point(wall_center_x() - wall_half, HEIGHT),
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

    if with_floor:
        draw_floor_tiles()

    # 벽과 바닥이 만나는 모서리 — 바닥이 없어도 벽의 밑동선으로 공간을 잡아 준다
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
    draw_line(
        *zoom_point(wall_center_x() - wall_half, wall_y),
        *zoom_point(wall_center_x() + wall_half, wall_y),
    )


def draw_floor_tiles():
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
            zoom_point(wall_center_x() - wall_half, wall_y),
            zoom_point(wall_center_x() + wall_half, wall_y),
            zoom_point(wall_center_x() + wall_half, wall_y + 220),
            zoom_point(wall_center_x() - wall_half, wall_y + 220),
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
    halo_center = zoom_point(wall_center_x(), VANISHING_Y - 90)
    segments = 24
    ring = [
        (
            halo_center[0] + 320 * view_zoom * math.cos(2 * math.pi * index / segments),
            halo_center[1] + 230 * view_zoom * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments + 1)
    ]
    draw_polygon(
        [halo_center] + ring,
        [fog + (50,)] + [clear] * (segments + 1),
    )


def draw_pillars(with_floor=True):
    """좌우 기둥. 먼 것부터 그린다. 앞면 + 안쪽 옆면 (+ with_floor면 바닥 그림자)."""
    for depth in PILLAR_DEPTHS:
        back_depth = 1.0 / (1.0 / depth + PILLAR_THICKNESS)
        for side in (-1, 1):
            inner = side * PILLAR_INNER_X
            outer = side * PILLAR_OUTER_X
            shadow_depth = depth * 1.10

            # 바닥 그림자 — 뒤쪽 보스의 빛을 등지고 카메라 쪽으로 길게 눕는다
            if with_floor:
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
    previous_elevation = PEDESTAL_BASE_ELEVATION
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

        # 단상 색은 전부 약 55%로 낮췄다: 단상이 보스보다 밝아 화면 위쪽에서 가장 눈에
        # 띄었다. 보이드(#0C0E14)보다 살짝 밝은 정도로 눌러 보스 역광 대비가 1순위가 되게 한다
        # 옆면 — 경사가 위를 향해 카메라에 보인다. 앞면보다 어둡다 (40,46,64 → 22,25,35)
        side_near = shade((22, 25, 35), 0.85)
        side_far = shade((22, 25, 35), 0.55)
        draw_polygon(
            (front_bottom_left, front_top_left, back_top_left, back_bottom_left),
            (side_near, side_near, side_far, side_far),
        )
        draw_polygon(
            (front_bottom_right, back_bottom_right, back_top_right, front_top_right),
            (side_near, side_far, side_far, side_near),
        )

        # 윗면 — 단상에서 가장 밝다 (52,59,80 → 29,33,44)
        top_near = shade((29, 33, 44), 1.0)
        top_far = shade((29, 33, 44), 0.7)
        draw_polygon(
            (front_top_left, front_top_right, back_top_right, back_top_left),
            (top_near, top_near, top_far, top_far),
        )

        # 앞면 (34,39,55 → 19,22,30)
        face_top = shade((19, 22, 30), 1.0)
        face_bottom = shade((19, 22, 30), 0.6)
        draw_polygon(
            (front_bottom_left, front_bottom_right, front_top_right, front_top_left),
            (face_bottom, face_bottom, face_top, face_top),
        )

        # 모서리 — 윗면 앞 모서리에 빛, 보스 쪽 붉은 기운
        # 모서리 빛도 낮춘다 (알파 150 → 70, 110 → 50) — 형태만 읽히고 시선은 끌지 않게
        set_draw_rgb(96, 108, 140, 70)
        draw_line(*front_top_left, *front_top_right)
        set_draw_rgb(70, 80, 106, 50)
        draw_line(*front_bottom_left, *front_top_left)
        draw_line(*front_bottom_right, *front_top_right)
        set_draw_color("accent", 30 + 15 * tier_index)
        draw_line(
            *project(-top_half * 0.6, front, elevation - 6),
            *project(top_half * 0.6, front, elevation - 6),
        )
        previous_elevation = elevation



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

    marker_radius = max(3, int(5 * lane["scale"] * view_zoom))
    for logical_x in (18, PLAYER_LOGICAL_WIDTH - 18):
        draw_filled_circle(*lane_point(lane_name, logical_x), marker_radius)


def draw_boss_placeholder(
    awakened=False,
    hit=False,
    defeated=False,
    pose="idle",
    forward_progress=0.0,
    center_x=640,
    burial_y=330,
    lean_offset=0.0,
):
    """보스 1 — 땅에 반쯤 묻힌 거상 상반신.

    burial_y(매몰선)는 몸통이 땅에서 나오는 높이다. 그 아래(다리·발치 그림자,
    바닥에 박힌 손)는 클립해서 그리지 않는다.
    lean_offset(화면 px)은 돌진 조준으로 상체가 기운 양이다. 매몰선에서 0, 머리에서
    lean_offset이 되도록 높이에 비례해 밀어(전단) 몸통이 매몰선에서 꺾여 보이게 한다.
    매몰선·흙더미는 center_x에 고정된다.
    """
    # 몸통 밑변(발치 + 34)이 매몰선에 오도록 발치를 매몰선 아래에 둔다.
    # 보이는 높이는 몸통 밑변 ~ 뿔 끝 = 214 - 34 = 180 단위
    body_offset = BOSS_BODY_OFFSET
    visible_height = BOSS_VISIBLE_HEIGHT
    # 매몰선은 boss_anchor가 정한 단상 윗면에 고정되고 보스는 위로만 커진다.
    # 평시 ≈ 340px(화면 47%), 각성은 앞으로 나온 원근 + 1.1배, 위는 천장(615)에서 잘린다
    # 카메라 줌: 바닥(project)과 같은 배율을 보스 크기와 천장에도 곱한다
    desired_scale = boss_desired_scale(awakened, forward_progress) * view_zoom
    ceiling_y = zoom_y(BOSS_CEILING_Y)
    max_visible_scale = (ceiling_y - burial_y) / visible_height
    scale = min(desired_scale, max_visible_scale)
    foot_y = burial_y - body_offset * scale
    set_clip_above(burial_y)
    body_half_width = 42 * scale
    body_bottom = foot_y + 34 * scale
    body_top = foot_y + 142 * scale
    head_y = foot_y + 166 * scale

    def set_boss_color(color_name):
        # 알파 0.6 → 불투명, 채도·블루 틴트 제거: 반투명 청색 보스는 벽(≈#181C28)과 명도가
        # 같아 묻혔다. 플레이어와 같은 #0A0C10 실루엣으로 떨어뜨리고 대비는 역광이 만든다
        set_draw_color(color_name)

    def lean(x, y):
        """높이에 비례한 가로 밀림 — 매몰선 0, 머리 중심 lean_offset."""
        return x + lean_offset * max(0.0, y - burial_y) / max(1.0, head_y - burial_y)

    def torso_quad(left, bottom, right, top):
        return (
            (lean(left, bottom), bottom),
            (lean(right, bottom), bottom),
            (lean(right, top), top),
            (lean(left, top), top),
        )

    head_x = lean(center_x, head_y)

    body_color = "flash" if hit else ("wall_light" if defeated else "actor_dark")
    set_boss_color("actor_dark")
    draw_polygon(
        torso_quad(
            center_x - body_half_width - 8 * scale,
            body_bottom - 8 * scale,
            center_x + body_half_width + 8 * scale,
            body_top + 8 * scale,
        )
    )
    draw_filled_circle(head_x, head_y, 34 * scale)

    set_boss_color(body_color)
    draw_polygon(
        torso_quad(
            center_x - body_half_width,
            body_bottom,
            center_x + body_half_width,
            body_top,
        )
    )
    draw_filled_circle(head_x, head_y, 27 * scale)

    set_boss_color("actor_dark")
    horn_start_y = min(head_y + 18 * scale, ceiling_y)
    horn_end_y = min(head_y + 48 * scale, ceiling_y)
    # 뿔·팔은 1px 선이면 실루엣에서 사라진다. 굵기를 줘 윤곽선의 일부로 만든다
    # 뿔은 머리에 붙어 있으므로 머리와 같은 양만큼 민다
    for side in (-1, 1):
        draw_thick_line(
            head_x + side * 26 * scale,
            horn_start_y - 6 * scale,
            head_x + side * 48 * scale,
            horn_end_y,
            7 * scale,
            2 * scale,
        )

    shoulder_y = body_top - 12 * scale

    def draw_arm(side, elbow_x, elbow_y, hand_x, hand_y):
        # 팔은 어깨 높이만큼 밀린 몸통에 붙어 함께 움직인다
        arm_shift = lean(center_x, shoulder_y) - center_x
        shoulder_x = center_x + side * body_half_width + arm_shift
        elbow_screen_x = center_x + side * elbow_x * scale + arm_shift
        hand_screen_x = center_x + side * hand_x * scale + arm_shift
        draw_thick_line(shoulder_x, shoulder_y, elbow_screen_x, elbow_y, 16 * scale, 13 * scale)
        draw_filled_circle(elbow_screen_x, elbow_y, 6.5 * scale)
        draw_thick_line(elbow_screen_x, elbow_y, hand_screen_x, hand_y, 13 * scale, 11 * scale)
        draw_filled_circle(hand_screen_x, hand_y, 11 * scale)

    if pose == "slam":
        # 손 원 반지름(11)만큼 천장에서 내린다. 9로 두면 손이 천장 위로 2×scale 삐져나온다
        hand_limit = ceiling_y - 11 * scale
        draw_arm(-1, 58, min(foot_y + 177 * scale, hand_limit - 9 * scale), 64, min(foot_y + 220 * scale, hand_limit))
        draw_arm(1, 58, foot_y + 105 * scale, 75, foot_y + 78 * scale)
    elif pose == "slam_double":
        # 손 원 반지름(11)만큼 천장에서 내린다. 9로 두면 손이 천장 위로 2×scale 삐져나온다
        hand_limit = ceiling_y - 11 * scale
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
    for line_y, half in ((body_top - 36 * scale, 22), (body_top - 46 * scale, 24)):
        draw_line(
            lean(center_x - half * scale, line_y),
            line_y,
            lean(center_x + half * scale, line_y),
            line_y,
        )
    # 눈 — 빨강 발광 #E01C2C (BOSS1_SPEC 보스 강조색). 실루엣 안에서 유일하게 빛나는 점.
    # 각성 시 더 밝고 커지던 변화는 뺐다 — 상태와 무관하게 같다
    eye_rgb, eye_radius, glow_radius, glow_alpha = (224, 28, 44), 4.0, 12, 110
    for eye_side in (-1, 1):
        eye_x = head_x + eye_side * 10 * scale
        # 주변 약한 발광 — 가장자리로 갈수록 투명
        draw_radial_glow(eye_x, head_y, glow_radius * scale, glow_radius * 0.75 * scale, eye_rgb, glow_alpha, 20)
        set_draw_rgb(*eye_rgb)
        draw_filled_circle(eye_x, head_y, eye_radius * scale)
    clear_clip()

    # 매몰선의 흙더미 — 잘린 단면 대신 몸이 땅에 박혀 있는 것처럼 보이게
    set_boss_color("shadow")
    draw_filled_ellipse(center_x, burial_y, BOSS_MOUND_HALF_WIDTH * scale, 9 * scale)


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

    # 림 라이트 — 보스가 앞줄 바로 뒤까지 커지면서 같은 검은 실루엣(#0A0C10)인 플레이어가
    # 보스 몸통 앞에서 묻혔다. 실루엣보다 2px 큰 차가운 빛 테두리로 윤곽을 떼어 낸다
    rim = PLAYER_RIM_PX
    set_draw_rgb(*PLAYER_RIM_RGBA)
    draw_filled_circle(screen_x, foot_y + 70 * scale, 15 * scale + rim)
    draw_filled_rectangle(
        screen_x - body_half_width - 3 * scale - rim,
        body_bottom - 3 * scale - rim,
        screen_x + body_half_width + 3 * scale + rim,
        body_top + 3 * scale + rim,
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
        self.player_lane = "platform_2"
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
        # 카메라 줌(그리기 전용). 시작 레인의 줌에서 출발한다
        self.view_zoom = LANE_VIEW_ZOOM[self.player_lane]
        self.view_zoom_from = self.view_zoom
        self.view_zoom_to = self.view_zoom
        self.view_zoom_elapsed = VIEW_ZOOM_DURATION
        # 좌우 카메라(월드 x). 시작 위치에서 바로 맞춰 첫 프레임에 미끄러지지 않게 한다
        self.camera_x = self.camera_target_x()
        self.apply_view_zoom()
        # 각성 연출 진행도 0~1 (그리기 전용). 깊이·크기·역광을 이 값으로 섞는다
        self.boss_awaken_blend = 0.0

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
            elif event.key in (pico2d.SDLK_LSHIFT, pico2d.SDLK_RSHIFT):
                self.start_dodge()
            elif event.key == pico2d.SDLK_SPACE:
                target_lane = (
                    "platform_2"
                    if self.player_lane == "platform_1"
                    else "platform_1"
                )
                self.start_lane_transition(target_lane)
        elif event.type == pico2d.SDL_MOUSEBUTTONDOWN:
            # 공격은 마우스: 왼쪽 클릭 = 기본 공격, 오른쪽 클릭 = 강공격
            if event.button == pico2d.SDL_BUTTON_LEFT:
                self.start_attack("basic")
            elif event.button == pico2d.SDL_BUTTON_RIGHT:
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
        self.player_lane = "platform_2"
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

    def recover_health_from_pushback(self):
        # 체력이 가득이면 회복할 게 없으니 기준점을 현재값으로 당겨, 되민 양을 미리 쌓아두지 못하게 한다
        if self.player_health >= PLAYER_MAX_HEALTH:
            self.seal_gauge.reset_recovery_mark()
            return
        if self.seal_gauge.try_recover_health():
            self.player_health = min(PLAYER_MAX_HEALTH, self.player_health + 1)

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

    def update_camera(self, fixed_delta):
        """레인별 카메라 줌 보간. 게임플레이에는 영향이 없다 (그리기 전용 상태)."""
        # 전환 중이면 도착할 레인, 아니면 지금 레인의 줌을 목표로 한다
        target_lane = self.lane_transition_target or self.player_lane
        target_zoom = LANE_VIEW_ZOOM[target_lane]
        if target_zoom != self.view_zoom_to:
            self.view_zoom_from = self.view_zoom
            self.view_zoom_to = target_zoom
            self.view_zoom_elapsed = 0.0
        self.view_zoom_elapsed = min(
            self.view_zoom_elapsed + fixed_delta,
            VIEW_ZOOM_DURATION,
        )
        t = self.view_zoom_elapsed / VIEW_ZOOM_DURATION
        eased = 1.0 - (1.0 - t) ** 3  # ease-out: 빠르게 출발해 부드럽게 멈춘다
        self.view_zoom = self.view_zoom_from + (
            self.view_zoom_to - self.view_zoom_from
        ) * eased

        # 좌우 추적: 목표로 지수 감쇠 보간 (프레임 속도와 무관하게 같은 지연)
        follow = 1.0 - math.exp(-fixed_delta / CAMERA_FOLLOW_TIME)
        self.camera_x += (self.camera_target_x() - self.camera_x) * follow
        self.apply_view_zoom()

        # 각성 연출: 판정과 무관하게 화면에서만 BOSS_AWAKEN_BLEND_TIME에 걸쳐 전환한다
        step = fixed_delta / BOSS_AWAKEN_BLEND_TIME
        goal = 1.0 if self.boss.awakened else 0.0
        if self.boss_awaken_blend < goal:
            self.boss_awaken_blend = min(goal, self.boss_awaken_blend + step)
        else:
            self.boss_awaken_blend = max(goal, self.boss_awaken_blend - step)

    def boss_awaken_visual(self):
        """각성 연출 진행도에 ease-in-out을 건 값 (0~1)."""
        t = self.boss_awaken_blend
        return t * t * (3.0 - 2.0 * t)

    def camera_target_x(self):
        return logical_to_world_x(self.player_logical_x) * CAMERA_FOLLOW

    def apply_view_zoom(self):
        """카메라 상태(줌, 좌우)를 그리기 함수들이 읽는 전역에 반영한다."""
        global view_zoom, camera_x
        view_zoom = self.view_zoom
        camera_x = self.camera_x

    def update(self, fixed_delta):
        self.update_camera(fixed_delta)
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
                    self.recover_health_from_pushback()
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

        # 사망은 체력 0일 때만. 게이지가 보스 쪽 끝에 닿아도 각성 상태로 계속 싸운다
        if self.player_health <= 0:
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
        self.player_lane = "platform_2"
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
        # 게이지는 0.5로 되돌리지 않고 이어받는다. 죽기까지 세 대(≈0.45)를 이미 밀렸으므로
        # 0.5 리셋은 이중 처벌이었다. 대신 사망 패널티만큼 보스 쪽으로 민다 (0~1 클램프 유지)
        self.seal_gauge.player_hit(DEATH_GAUGE_PENALTY)
        self.boss.reset_for_phase(phase)
        # 각성은 강제로 끄지 않고 게이지 값에 따라 다시 판정한다
        self.boss.set_awakened(self.seal_gauge.boss_awakened)

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
        self.apply_view_zoom()
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
        # 바닥 타일만 빼고 벽·기둥·안개는 그린다. 바닥 자리는 보이드로 남는다
        draw_room(with_floor=False)
        draw_pillars(with_floor=False)
        draw_back_fog()
        draw_boss_backlight(self.boss_awaken_visual())
        draw_pedestal()
        boss_pose = "idle"
        if self.boss.current_pattern is not None:
            boss_pose = PATTERNS[self.boss.current_pattern]["pose"]
            if self.boss.state in ("active", "recovery"):
                if self.boss.current_pattern in ("slam", "slam_double"):
                    boss_pose = "slam_impact"
                elif self.boss.current_pattern == "shockwave":
                    boss_pose = "shockwave_impact"

        boss_screen_x, boss_foot_y, boss_depth = boss_anchor(
            self.boss.position_x,
            self.boss.forward_progress,
            self.boss_awaken_visual(),
        )
        # 돌진 조준 오프셋(논리 x)을 보스 깊이의 화면 px로 바꾸고 절반만 쓴다.
        # 조준 그대로 기울이면 머리가 레인 끝(±300px 이상)까지 넘어가 몸이 부러져 보인다
        boss_lean_px = (
            self.boss.current_lean_x * logical_pixels(boss_depth) * BOSS_LEAN_DRAW_RATIO
        )
        draw_boss_placeholder(
            self.boss_awaken_visual(),
            self.boss_hit_timer > 0,
            self.boss_defeated,
            boss_pose,
            self.boss.forward_progress,
            boss_screen_x,
            boss_foot_y,
            boss_lean_px,
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
        # 깊이 배율(player_scale)은 투영에만 쓰고, 그리는 크기에는 카메라 줌을 곱한다
        player_scale *= view_zoom
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
                18 * growth * target_lane["scale"] * view_zoom,
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
            self.boss_awaken_visual(),
        )
        launch_y = boss_foot_y + 220 * view_zoom
        projectile_x = boss_screen_x + (target_x - boss_screen_x) * progress
        projectile_y = launch_y + (target_y - launch_y) * progress

        set_draw_color("accent", 100)
        draw_filled_ellipse(
            target_x,
            target_y,
            (80 - 40 * progress) * view_zoom,
            (16 - 8 * progress) * view_zoom,
        )
        set_draw_color("accent_light")
        draw_filled_circle(projectile_x, projectile_y, (8 + 12 * progress) * view_zoom)

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
            # 바닥이 없으므로 띠는 플랫폼 높이를 따라 이어진다:
            # 보스 발치 → 앞줄 먼 모서리, 앞줄 앞 모서리 → 뒷줄 먼 모서리
            rear = LANES["platform_2"]
            front = LANES["platform_1"]
            gap_color = (255, 228, 196, round(160 * fade))
            for near_depth, near_elevation, far_depth, far_elevation, near_rgba, far_rgba in (
                (front["far"], front["elevation"], BOSS_CHARGE_DEPTH, BOSS_CHARGE_ELEVATION, far_color, far_color),
                (rear["far"], rear["elevation"], front["near"], front["elevation"], gap_color, gap_color),
            ):
                draw_polygon(
                    (
                        project(left, near_depth, near_elevation),
                        project(right, near_depth, near_elevation),
                        project(right, far_depth, far_elevation),
                        project(left, far_depth, far_elevation),
                    ),
                    (near_rgba, near_rgba, far_rgba, far_rgba),
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
                18 * (1.0 - 0.5 * marker_progress) * lane["scale"] * view_zoom,
            )

    def draw_impact_flash(self):
        if self.impact_flash_timer <= 0:
            return
        x, y = self.impact_flash_position
        remaining = min(self.impact_flash_timer / 0.08, 1.0)
        spread = 1.0 - remaining
        # 바닥에 납작하게 퍼지는 착탄 고리 + 위로 솟는 짧은 섬광
        set_draw_color("flash", int(200 * remaining))
        draw_filled_ellipse(x, y, (40 + 50 * spread) * view_zoom, (10 + 12 * spread) * view_zoom)
        draw_polygon(
            (
                (x - 14 * view_zoom, y),
                (x + 14 * view_zoom, y),
                (x + 4 * view_zoom, y + (60 + 40 * spread) * view_zoom),
                (x - 4 * view_zoom, y + (60 + 40 * spread) * view_zoom),
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
