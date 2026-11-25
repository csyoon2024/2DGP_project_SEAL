import os
import math
import random
from ctypes import c_int

import pico2d
import sdl2

from seal_gauge import SealGauge
import player_sprite
import boss_sprite
from pico2d import (
    draw_circle as pico_draw_circle,
    draw_line as pico_draw_line,
    draw_rectangle as pico_draw_rectangle,
)
from boss import (
    ARMOR_BREAK_GAUGE_BONUS,
    ARMOR_STAGE_LEAK_SCALE,
    BOSS_PARTS,
    PART_BREAK_GAUGE_BONUS,
    PART_DAMAGE,
    PHASE_MODIFIERS,
    PHASE_PATTERNS,
    PATTERNS,
    BossAttack,
    BossController,
    part_at,
)


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
# 테스트용: 보스 공격 속도 배율. 0.2 = 20% — 보스의 시간이 5배 느리게 흐른다
#   (예고 0.40초 → 2.0초 등, 패턴 사이 공백도 같이). 부위 파괴 등을 천천히 시험하려고 낮췄다.
#   밸런스 확인 전에 1.0으로 되돌릴 것
BOSS_TEST_SPEED = 0.2
# 보스 처치 연출 1.5초: 여운 0.5초(보스가 쓰러진 걸 볼 시간) → 1.0초 페이드 아웃 →
#   보스 사이 화면(InterludeScene)으로 전환. 예전에는 2.8초 뒤 게임을 닫았다
GAME_END_LINGER = 0.5
GAME_END_FADE = 1.0
GAME_END_HOLD = 0.0
# 플레이어 스프라이트의 화면 키 (플레이어 배율 단위). 뒷줄 100px, 앞줄(배율 0.71 × 줌 1.12) ≈ 80px.
#   예전 도형 캐릭터(머리 꼭대기 ≈ 85)보다 조금 크게 — 그림체의 머리·검이 읽히는 최소 크기
PLAYER_SPRITE_HEIGHT = 100

# 기세 표시 — 플레이어 머리 위 4칸 (수치는 SealGauge.MOMENTUM_*_GAINS).
# 칸 크기는 플레이어 배율 단위라 앞줄·뒷줄·줌에서 캐릭터와 같은 비율로 보인다.
#   앞줄(배율 ≈ 0.8)에서 막대 폭 ≈ 75px, 칸 높이 ≈ 7px — 회피 중 곁눈으로 읽히는 크기
MOMENTUM_CELL_WIDTH = 18
MOMENTUM_CELL_HEIGHT = 9
MOMENTUM_CELL_GAP = 5
# 머리 꼭대기(발치 + 85)보다 조금 위. 회피 중 곁눈으로 보이게 캐릭터에 붙인다
MOMENTUM_BAR_OFFSET = PLAYER_SPRITE_HEIGHT + 12
MOMENTUM_COLOR = (74, 158, 255)  # 플레이어 강조색 #4A9EFF
MOMENTUM_MAX_COLOR = (170, 214, 255)  # 기세 4: 같은 계열을 더 밝게
# 칸이 새로 채워질 때 흰색에서 강조색으로 돌아오는 시간
MOMENTUM_FLASH_TIME = 0.18
# 피격으로 0이 될 때 칸 조각이 튀어 흩어지는 시간. 잃는 게 눈에 보여야 도박이 성립한다
MOMENTUM_SHATTER_TIME = 0.55
MOMENTUM_SHARD_GRAVITY = 260  # 조각 낙하 가속 (플레이어 배율 단위/초²)

# 보스 스프라이트(boss_sprite.py) 배치.
#   몸통 높이(발 ~ 어깨 위, 원본 칸 264px)를 도형 보스와 같은 화면 높이에 맞춘다:
#   배율 = boss_desired_scale × BOSS_VISIBLE_HEIGHT / 264 (평시 뒷줄 ≈ 340px, 화면의 47%).
#   단 머리 위로 든 팔(칸 맨 위 0)까지 천장(615) 아래에 들어오도록 배율을 줄인다
BOSS_SPRITE_BODY_HEIGHT = 264
BOSS_SPRITE_MAX_LEAN = 12  # 돌진 기울기 상한 (도)
BOSS_SPRITE_BROKEN_RGB = (118, 118, 128)  # 부서진 팔 — 원래 색에 곱해 생기 빠진 회색으로
BOSS_SPRITE_DEFEATED_RGB = (80, 82, 92)
BOSS_SPRITE_FLASH_RGB = (255, 244, 224)
# 보스 2: 보스 1 스프라이트를 색만 바꿔 쓴다 (원래 색에 곱한다 — 회색 돌·붉은 빛 → 보랏빛 쇠)
BOSS2_TINT_RGB = (172, 150, 255)
# 보스 2 장갑판 — 핵 위를 덮는 육각 철판 (도형). 반지름 = 핵 표시 반지름 × 이 값
ARMOR_RADIUS_SCALE = 1.45
ARMOR_RGB = (78, 84, 108)
ARMOR_EDGE_RGB = (150, 158, 186)
ARMOR_SHARD_RGB = (176, 182, 206)
ARMOR_BREAK_SHAKE = (18, 0.40)  # 장갑이 깨지는 순간 — 팔 파괴(14, 0.3)보다 크게  # 피격 순간 흰 번쩍임 (실루엣을 반투명으로 덮는다)

# 부위 파괴 연출
PART_BREAK_SHAKE = (14, 0.30)  # 팔이 부서지는 순간 화면 흔들림 (px, 초)
CHAIN_LINK_SPACING = 9  # 사슬 고리 간격 (보스 배율 단위)
CHAIN_RGB = (78, 84, 100)  # 사슬 쇠 색 — 검은 실루엣과 역광 모두에서 읽히는 회청색
CHAIN_HIGHLIGHT_RGB = (150, 160, 182)
BROKEN_ARM_RGB = (40, 43, 54)  # 부서진 팔 색 — 검은 몸(#0A0C10)보다 밝고 벽보다 어둡다
CHAIN_SHARD_LIFE = 1.0  # 끊긴 사슬 조각이 흩어져 사라지는 시간 (초)
CHAIN_SHARD_GRAVITY = 900  # 조각 낙하 가속 (화면 px/초²)
# 조준 표시 — 지금 공격하면 맞을 부위. 플레이어 강조색으로 윤곽과 발광
AIM_RGB = (74, 158, 255)
PART_BAR_CELL = (7, 5, 2)  # 팔 내구도 칸 (폭, 높이, 간격 — 화면 px, 줌 배율 곱함)

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
    pose_side=1,
    head_lift=0.0,
    eye_glow=0.0,
    broken_sides=(),
):
    """보스 1 — 땅에 반쯤 묻힌 거상 상반신.

    pose_side: 한 팔 포즈(후려치기)에서 휘두르는 팔이 출발하는 쪽 (-1 왼쪽 / 1 오른쪽).
    head_lift(0~1): 머리를 드는 양. eye_glow(0~1): 눈을 밝히는 양 (유도탄 예고·발사).
    broken_sides: 부서진 팔 (-1 화면 왼쪽 arm_l / 1 화면 오른쪽 arm_r). 포즈와 상관없이
      축 늘어진 채로 그리고 사슬이 없다. 성한 팔은 손목에서 땅으로 사슬이 묶여 있다.
    반환: {"eye": 두 눈 사이, "arms": {side: (어깨, 팔꿈치, 손)}, "chains": {side: (손, 땅)},
           "core": (x, y, 반지름), "scale"} — 유도탄 발사 지점·조준 표시·사슬 파편에 쓴다.

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
    # 유도탄 예고: 머리를 최대 12 들어 올린다 (뿔 끝은 천장에서 잘린다)
    head_y = foot_y + (166 + 12 * head_lift) * scale

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
    arms_drawn = {}
    chains_drawn = {}

    def draw_chain(x1, y1, x2, y2):
        draw_chain_line(x1, y1, x2, y2, scale)

    def draw_arm(side, elbow_x, elbow_y, hand_x, hand_y):
        # 팔은 어깨 높이만큼 밀린 몸통에 붙어 함께 움직인다
        broken = side in broken_sides
        if broken:
            # 부서진 팔: 포즈와 상관없이 어깨에서 몸 바깥쪽으로 축 늘어진다.
            #   몸통(반폭 42) 안으로 늘어뜨리면 검은 몸에 묻혀 안 보여서 바깥으로 뺐다
            elbow_x, elbow_y = 66, foot_y + 96 * scale
            hand_x, hand_y = 74, foot_y + 54 * scale
        arm_shift = lean(center_x, shoulder_y) - center_x
        shoulder_x = center_x + side * body_half_width + arm_shift
        elbow_screen_x = center_x + side * elbow_x * scale + arm_shift
        hand_screen_x = center_x + side * hand_x * scale + arm_shift
        if broken:
            # 생기 빠진 회색 — 성한 팔(검은 실루엣)과 한눈에 구분된다
            set_draw_rgb(*BROKEN_ARM_RGB, 255)
        else:
            set_boss_color("actor_dark")
        draw_thick_line(shoulder_x, shoulder_y, elbow_screen_x, elbow_y, 16 * scale, 13 * scale)
        draw_filled_circle(elbow_screen_x, elbow_y, 6.5 * scale)
        draw_thick_line(elbow_screen_x, elbow_y, hand_screen_x, hand_y, 13 * scale, 11 * scale)
        draw_filled_circle(hand_screen_x, hand_y, 11 * scale)
        arms_drawn[side] = (
            (shoulder_x, shoulder_y),
            (elbow_screen_x, elbow_y),
            (hand_screen_x, hand_y),
        )
        if broken:
            # 금 간 자국과 손목에 남은 끊긴 쇠고리
            set_draw_rgb(96, 104, 122, 210)
            draw_line(shoulder_x - side * 3 * scale, shoulder_y - 6 * scale,
                      elbow_screen_x + side * 2 * scale, elbow_y + 9 * scale)
            draw_line(elbow_screen_x - side * 4 * scale, elbow_y - 5 * scale,
                      elbow_screen_x + side * 3 * scale, elbow_y - 15 * scale)
            set_draw_rgb(*CHAIN_RGB, 255)
            draw_filled_ellipse(hand_screen_x, hand_y - 9 * scale, 4.2 * scale, 2.6 * scale, 10)
        else:
            # 사슬: 손목에서 몸 옆 땅으로. 보스가 대좌에 결박돼 있다는 설정을 보여 준다
            anchor = (center_x + side * 70 * scale, burial_y - 4 * scale)
            draw_chain(hand_screen_x, hand_y - 8 * scale, *anchor)
            chains_drawn[side] = ((hand_screen_x, hand_y - 8 * scale), anchor)
        set_boss_color("actor_dark")

    if pose == "slam":
        # 내려찍기는 화면 오른쪽 팔(arm_r)이 든다 — 부위 파괴 연결(PATTERN_PART)과 맞춘다.
        # 손 원 반지름(11)만큼 천장에서 내린다. 9로 두면 손이 천장 위로 2×scale 삐져나온다
        hand_limit = ceiling_y - 11 * scale
        draw_arm(1, 58, min(foot_y + 177 * scale, hand_limit - 9 * scale), 64, min(foot_y + 220 * scale, hand_limit))
        draw_arm(-1, 58, foot_y + 105 * scale, 75, foot_y + 78 * scale)
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
        # 유도탄은 머리(눈)에서 나간다. 팔은 몸 옆에 붙이고 머리를 든다 (head_lift)
        draw_arm(-1, 54, foot_y + 104 * scale, 66, foot_y + 74 * scale)
        draw_arm(1, 54, foot_y + 104 * scale, 66, foot_y + 74 * scale)
    elif pose == "backhand":
        # 후려치기 예고: 한 팔을 충격파와 같은 높이로 수평으로 뻗어 뒤로 젖힌다. 다른 팔은 대기
        draw_arm(pose_side, 75, foot_y + 142 * scale, 118, foot_y + 146 * scale)
        draw_arm(-pose_side, 56, foot_y + 108 * scale, 78, foot_y + 82 * scale)
    elif pose == "backhand_impact":
        # 후려치기 실행: 같은 팔이 몸 앞을 가로질러 반대쪽 낮은 곳까지 쓸고 지나간다
        draw_arm(pose_side, 30, foot_y + 118 * scale, -96, foot_y + 96 * scale)
        draw_arm(-pose_side, 56, foot_y + 108 * scale, 78, foot_y + 82 * scale)
    elif pose == "slam_impact":
        # 내려찍기 착탄: 오른팔만 내리꽂는다
        draw_arm(1, 68, foot_y + 76 * scale, 90, foot_y + 12 * scale)
        draw_arm(-1, 56, foot_y + 108 * scale, 78, foot_y + 82 * scale)
    elif pose in ("double_impact", "shockwave_impact"):
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
    if eye_glow > 0:
        # 유도탄 예고·발사: 눈이 밝고 커진다 (빨강 → 주황빛 흰색 쪽으로)
        eye_rgb = tuple(round(c + (t - c) * eye_glow) for c, t in zip(eye_rgb, (255, 196, 150)))
        eye_radius *= 1.0 + 0.5 * eye_glow
        glow_radius *= 1.0 + 1.6 * eye_glow
        glow_alpha = round(glow_alpha + (230 - glow_alpha) * eye_glow)
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
    core_y = body_top - 41 * scale  # 가슴의 붉은 두 줄 사이 = 핵
    return {
        "eye": (head_x, head_y),
        "arms": arms_drawn,
        "chains": chains_drawn,
        "core": (lean(center_x, core_y), core_y, 30 * scale),
        "scale": scale,
    }


# ---------------------------------------------------------------------------
# 예고 표시 — 전투(보스 패턴)와 추격 구간(흘러오는 위협)이 같은 함수를 쓴다. 새로 배울 표시가 없다.
# visible: 깜빡임 켜짐 여부, progress: 예고 진행도 0~1
# ---------------------------------------------------------------------------
def draw_lane_marker(lane_name, visible):
    """레인 전체 (충격파)."""
    quad = lane_quad(lane_name)
    set_draw_color("accent", 90 if visible else 0)
    draw_polygon(quad)
    set_draw_color("accent_light")
    draw_polyline(quad)


def draw_range_marker(lane_name, left, right, visible):
    """레인 한 구간 (후려치기)."""
    quad = lane_quad(lane_name, left, right)
    set_draw_color("accent", 90 if visible else 0)
    draw_polygon(quad)
    set_draw_color("accent_light", 255 if visible else 45)
    draw_polyline(quad)


def draw_column_marker(left, right, visible):
    """두 레인을 꿰뚫는 기둥 (돌진)."""
    for lane_name in ("platform_1", "platform_2"):
        draw_range_marker(lane_name, left, right, visible)


def draw_spot_marker(lane_name, target_x, visible, progress):
    """한 점 (내려찍기) — 줄어드는 타원 그림자."""
    target_lane = LANES[lane_name]
    scale = logical_pixels(target_lane["scale"])
    screen_x, screen_y = lane_point(lane_name, target_x)
    growth = 1.0 - 0.5 * progress
    set_draw_color("accent", int(60 + 140 * progress) if visible else 60)
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


def draw_chain_line(x1, y1, x2, y2, scale):
    """사슬 한 줄 (pico 좌표). 고리를 가로·세로로 번갈아 놓는다. scale = 고리 크기 배율."""
    length = math.hypot(x2 - x1, y2 - y1)
    count = max(2, int(length / (CHAIN_LINK_SPACING * scale)))
    set_draw_rgb(*CHAIN_RGB, 255)
    draw_thick_line(x1, y1, x2, y2, 2.2 * scale, 2.2 * scale)
    for index in range(count + 1):
        t = index / count
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        rx, ry = (4.2, 2.6) if index % 2 else (2.6, 4.2)
        set_draw_rgb(*CHAIN_RGB, 255)
        draw_filled_ellipse(x, y, rx * scale, ry * scale, 10)
        set_draw_rgb(*CHAIN_HIGHLIGHT_RGB, 200)
        draw_filled_circle(x - 0.8 * scale, y + 0.8 * scale, 1.1 * scale)


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
    def __init__(self, scene_manager=None, run_state=None, boss_id=1):
        # 씬 전환용. 없으면(테스트 스크립트 등) 처치 연출 뒤 quit_requested만 세운다
        self.scene_manager = scene_manager
        self.run_state = run_state
        # 1 = 보스 1, 2 = 보스 2 (핵이 장갑에 덮여 있다). 디버그 F10으로 바꿀 수 있다
        self.boss_id = boss_id
        # 전투 기록 (InterludeScene에 넘긴다). 판정에는 쓰지 않는다
        self.battle_elapsed = 0.0
        self.hits_taken = 0
        # 기세 0~4 (SealGauge.MOMENTUM_MAX). 앞줄 적중 +1, 뒷줄 전환 -1, 피격 0
        self.momentum = 0
        # 그리기 전용 연출 상태. 게임플레이 난수(debug_pattern_rng)와 섞이지 않게 따로 둔다
        self.momentum_flash_timer = 0.0
        self.momentum_shards = []
        self.fx_rng = random.Random(0)
        # 애니메이션 상태 (그리기 전용). 실제로 x가 움직였는지로 정해 벽에 막히면 대기로 돌아온다
        self.player_anim_time = 0.0
        self.player_animation = "idle"
        # 실제로 나간 공격 횟수 (그리기 전용). 홀수 번째 공격은 공격 동작을 좌우 반전해
        #   시트 한 장으로 좌우 번갈아 베는 연타처럼 보이게 한다
        self.attack_count = 0
        self.attack_visual_count = 0  # 지금 그리는 공격 동작이 몇 번째 공격인지
        self.attack_visual_duration = BASIC_ATTACK_DURATION
        self.run_skip_intro = False
        self.battle_finished = False
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
        self.boss = BossController(boss_id)
        self.boss_phase = 1
        self.boss_defeated = False
        self.game_end_elapsed = 0.0
        self.quit_requested = False
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
        # 보스 두 눈 사이 화면 좌표 (보스를 그릴 때 갱신). 유도탄 발사 지점
        self.boss_eye_screen = (VANISHING_X, HEIGHT / 2)
        # 보스를 그릴 때 갱신하는 부위 화면 좌표 (조준 표시·사슬 파편용, 그리기 전용)
        self.boss_geometry = None
        self.chain_shards = []

    def enter(self):
        # 스프라이트를 전투 시작 때 미리 읽는다. 첫 프레임에 읽으면 약 75ms 끊긴다
        player_sprite.is_available(PLAYER_RIM_RGBA[:3])
        boss_sprite.is_available()

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
                available_patterns = tuple(self.boss.phase_patterns[self.boss_phase])
                pattern_index = (
                    available_patterns.index(self.debug_forced_pattern) + 1
                    if self.debug_forced_pattern in available_patterns
                    else 0
                )
                self.debug_forced_pattern = available_patterns[
                    pattern_index % len(available_patterns)
                ]
            elif event.key in (pico2d.SDLK_F8, pico2d.SDLK_F9):
                # 디버그: 팔 즉시 파괴 (F8 화면 왼쪽 팔, F9 화면 오른쪽 팔)
                part = "arm_l" if event.key == pico2d.SDLK_F8 else "arm_r"
                armor_stage = self.boss.armor_intact()
                for broken in self.boss.break_part(part):
                    self.on_part_broken(broken, armor_stage)
            elif event.key == pico2d.SDLK_F11:
                # 디버그: 지금 구간을 끝낸다 (전투 → 추격 구간, 추격 → 성공)
                self.debug_skip()
            elif event.key == pico2d.SDLK_F10:
                # 디버그: 보스 1 ↔ 2 바꿔 처음부터
                self.switch_boss(2 if self.boss_id == 1 else 1)
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
        if target_lane == "platform_2":
            # 뒷줄로 물러서면 기세 -1. 전환을 시작한 순간 깎아 결정의 대가가 바로 보이게 한다
            self.lose_momentum()

    def debug_skip(self):
        if not self.battle_finished:
            self.finish_battle()

    def switch_boss(self, boss_id):
        self.boss_id = boss_id
        self.boss = BossController(boss_id)
        self.reset_player()

    def reset_player(self):
        self.momentum = 0
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
        self.game_end_elapsed = 0.0
        self.quit_requested = False
        self.boss.reset_for_phase(1)
        self.boss.reset_parts()
        self.chain_shards = []
        self.boss.set_awakened(False)

    def boss_should_awaken(self):
        # 2페이즈는 처음부터 끝까지 각성 상태다. 예전에는 게이지를 60%까지 되밀면 2페이즈에서도
        # 각성이 풀렸다. 1페이즈는 그대로 게이지로 판정한다 (85%에서 각성, 60%에서 해제)
        return self.boss_phase >= 2 or self.seal_gauge.boss_awakened

    def receive_player_hit(self, ignore_dodge=False):
        # ignore_dodge: 회피 무적을 무시하는 공격 (후려치기)
        if self.debug_invulnerability_enabled:
            return False
        if self.invulnerability_timer > 0 and not ignore_dodge:
            return False
        if self.player_health <= 0:
            return False
        self.player_health -= 1
        # 피격 손실은 현재 페이즈 값 (PHASE_MODIFIERS["hit_loss"], 각성 중엔 같은 비율로 증가)
        hit_loss = self.seal_gauge.hit_loss(self.boss.awakened)
        self.seal_gauge.player_hit(hit_loss)
        self.trigger_impact_flash(
            *lane_point(self.player_lane, self.player_logical_x)
        )
        self.trigger_screen_shake(8, 0.15)
        self.hits_taken += 1
        self.break_momentum()
        return True

    def battle_record(self):
        from run_state import BattleRecord

        return BattleRecord(
            elapsed=self.battle_elapsed,
            hits_taken=self.hits_taken,
            health_left=self.player_health,
            max_health=PLAYER_MAX_HEALTH,
        )

    def finish_battle(self):
        """처치 연출이 끝나면 전투 기록을 넘기고 보스 사이 화면으로 간다."""
        if self.scene_manager is None or self.run_state is None:
            # 씬 매니저 없이 단독 실행된 경우 — GameFramework가 이 값을 보고 루프를 끝낸다
            self.quit_requested = True
            return
        from chase_scene import ChaseScene

        record = self.battle_record()
        self.run_state.record_battle(record)
        self.battle_finished = True  # 한 번만 전환한다
        # 봉인 직후, 봉인이 깨지기 전에 다음 방으로 달린다 (추격 구간 → 결과·기술 선택 → 다음 보스전).
        #   체력은 이번 전투에서 남은 만큼 들고 간다 (다음 보스전 시작 때 가득 찬다)
        self.scene_manager.change_scene(
            ChaseScene(self.scene_manager, self.run_state, record, self.player_health)
        )

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

    def on_armor_broken(self):
        """보스 2 장갑 파괴: 게이지 큰 보상, 강한 흔들림, 철판 조각, 핵 노출 → 2페이즈(핵)."""
        self.seal_gauge.push_toward_player(ARMOR_BREAK_GAUGE_BONUS)
        self.trigger_screen_shake(*ARMOR_BREAK_SHAKE)
        core = (self.boss_geometry or {}).get("core")
        if core is not None:
            x, y, radius = core
            self.trigger_impact_flash(x, y)
            for index in range(22):
                angle = index / 22 * math.tau + self.fx_rng.uniform(-0.2, 0.2)
                speed = self.fx_rng.uniform(140, 380)
                self.chain_shards.append(
                    {
                        "x": x + math.cos(angle) * radius * 0.8,
                        "y": y + math.sin(angle) * radius * 0.8,
                        "vx": math.cos(angle) * speed,
                        "vy": math.sin(angle) * speed + 120,
                        "angle": self.fx_rng.uniform(0, math.tau),
                        "spin": self.fx_rng.uniform(-14, 14),
                        "life": CHAIN_SHARD_LIFE * self.fx_rng.uniform(0.8, 1.1),
                        "size": self.fx_rng.uniform(5.0, 9.0),
                        "rgb": ARMOR_SHARD_RGB,
                    }
                )
        if self.boss_phase == 1:
            # 핵이 드러나면 2페이즈. 게이지는 이어받고(리셋 없음), 이후는 보스 1의 2페이즈와 같다
            self.boss_phase = 2
            self.debug_phase = 2
            self.seal_gauge.set_phase(2)
            self.boss.reset_for_phase(2)
            self.boss.begin_awakening_demo()

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
        self.attack_count += 1

    def resolve_attack_hit(self):
        if self.player_lane != "platform_1":
            return False
        return self.attack_reaches_boss()

    def attack_reaches_boss(self):
        """지금 바라보는 쪽으로 공격하면 보스 판정에 닿는가 (레인 무관)."""
        if self.facing_direction > 0:
            attack_left = self.player_logical_x
            attack_right = self.player_logical_x + BASIC_ATTACK_REACH
        else:
            attack_left = self.player_logical_x - BASIC_ATTACK_REACH
            attack_right = self.player_logical_x

        boss_left = self.boss.position_x - BOSS_HITBOX_HALF_WIDTH
        boss_right = self.boss.position_x + BOSS_HITBOX_HALF_WIDTH
        return attack_left <= boss_right and attack_right >= boss_left

    def attack_target_part(self):
        """플레이어 논리 x로 정한 맞을 부위. 핵(몸통)은 정면 구역에서만, 좌우는 항상 팔이다.

        팔이 부서져도 그 구역은 핵이 되지 않는다 — 부서진 팔에 맞으면 아무 일도 없다.
        """
        return self.boss.part_at(self.player_logical_x)

    def aimed_part(self):
        """조준 표시용 — 앞줄에서 공격이 닿는 거리일 때만 부위 이름, 아니면 None."""
        if self.player_lane != "platform_1" or self.lane_transition_target is not None:
            return None
        if self.boss_defeated or not self.attack_reaches_boss():
            return None
        return self.attack_target_part()

    def strike_boss(self):
        """공격 적중 처리. 핵이면 게이지, 팔이면 내구도 (게이지는 안 민다)."""
        part = self.attack_target_part()
        if part == "core":
            # 획득량은 적중 전 기세로 정한다
            self.seal_gauge.player_attack_hit(self.attack_type, self.momentum)
        else:
            # 팔·장갑: 내구도만 깎는다 (게이지는 안 민다). 부서진 팔이면 아무 일도 없다.
            # 보스 2는 팔이 부서지면 장갑도 깎여 같이 부서질 수 있다
            armor_stage = self.boss.armor_intact()
            for broken in self.boss.damage_part(part, PART_DAMAGE[self.attack_type]):
                self.on_part_broken(broken, armor_stage)
        return part

    def on_part_broken(self, part, armor_stage=False):
        """부위가 부서진 순간. 팔: 게이지 보상·흔들림·사슬 파편. 장갑: 핵 노출·2페이즈.

        armor_stage: 이 타격이 보스 2 장갑 단계에서 일어났는가 — 그 단계에선 어떤 타격도
        게이지를 밀지 않으므로 팔 파괴 보상도 없다 (대신 장갑이 8 깎인다).
        """
        if part == "armor":
            self.on_armor_broken()
            return
        if not armor_stage:
            self.seal_gauge.push_toward_player(PART_BREAK_GAUGE_BONUS)
        self.trigger_screen_shake(*PART_BREAK_SHAKE)
        side = -1 if part == "arm_l" else 1
        chain = (self.boss_geometry or {}).get("chains", {}).get(side)
        if chain is None:
            return
        (x1, y1), (x2, y2) = chain
        self.trigger_impact_flash(x1, y1)
        for index in range(16):
            t = index / 15
            self.chain_shards.append(
                {
                    "x": x1 + (x2 - x1) * t,
                    "y": y1 + (y2 - y1) * t,
                    # 끊긴 자리(손목)에서 멀어지는 쪽 + 바깥으로 튄다
                    "vx": side * self.fx_rng.uniform(60, 260),
                    "vy": self.fx_rng.uniform(80, 360) * (1.0 - 0.6 * t),
                    "angle": self.fx_rng.uniform(0, math.tau),
                    "spin": self.fx_rng.uniform(-16, 16),
                    "life": CHAIN_SHARD_LIFE * self.fx_rng.uniform(0.7, 1.0),
                    "size": self.fx_rng.uniform(3.5, 5.5),
                }
            )

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

    def set_player_animation(self, animation):
        self.player_animation = animation
        self.player_anim_time = 0.0

    def update_player_animation(self, moved):
        """그리기 전용 동작 상태: idle / run / brake / attack.

        공격 중이면 attack (공격 시간에 맞춰 늘임, 끝난 뒤 꼬리는 서 있을 때만).
        실제로 움직였으면 run (회피·대시 포함) — 출발 구간 후 반복.
        달리다 멈추면 brake (감속 프레임) 후 idle.
        좌우 반전은 판정과 같은 facing_direction을 따른다 — 칼이 판정 쪽으로 나간다.
        """
        moving = abs(moved) > 1e-6
        if self.lane_transition_target is not None:
            # 레인 전환 도약. 뒷줄 → 앞줄 시트를 앞줄 → 뒷줄에도 그대로 쓴다 (뒷걸음 시트가 따로 없다).
            #   전환 시계(lane_transition_elapsed)에 맞춘다
            self.player_animation = "front_dash"
            self.player_anim_time = self.lane_transition_elapsed
            return
        if self.player_animation == "front_dash":
            # 도착 뒤 착지 꼬리 — 움직이거나 공격하면 끊는다
            if self.attack_type is not None:
                self.player_animation = "idle"  # 아래 공격 분기가 이어받는다
            elif moving:
                self.run_skip_intro = False
                self.set_player_animation("run")
                return
            elif player_sprite.front_dash_frame(self.player_anim_time, LANE_SWITCH_DURATION) is None:
                self.set_player_animation("idle")
                return
            else:
                return
        if self.attack_type is not None:
            if self.player_animation != "attack" or self.attack_visual_count != self.attack_count:
                self.attack_visual_count = self.attack_count
                self.attack_visual_duration = (
                    BASIC_ATTACK_DURATION
                    if self.attack_type == "basic"
                    else HEAVY_ATTACK_DURATION
                )
                self.player_animation = "attack"
            # 공격 중에는 판정 시계(attack_elapsed)에 맞춘다
            self.player_anim_time = self.attack_elapsed
            return

        if self.player_animation == "attack":
            if moving:
                self.run_skip_intro = False
                self.set_player_animation("run")
            elif self.player_attack_frame() is None:
                self.set_player_animation("idle")
            return

        if moving:
            if self.player_animation != "run":
                # 제동 중에 다시 달리면 출발(일어선 자세) 구간을 건너뛴다
                self.run_skip_intro = self.player_animation == "brake"
                self.set_player_animation("run")
        elif self.player_animation == "run":
            self.set_player_animation("brake")
        elif self.player_animation == "brake":
            if player_sprite.brake_frame(self.player_anim_time) is None:
                self.set_player_animation("idle")

    def update_chain_shards(self, fixed_delta):
        alive = []
        for shard in self.chain_shards:
            shard["life"] -= fixed_delta
            if shard["life"] <= 0:
                continue
            shard["vy"] -= CHAIN_SHARD_GRAVITY * fixed_delta
            shard["x"] += shard["vx"] * fixed_delta
            shard["y"] += shard["vy"] * fixed_delta
            shard["angle"] += shard["spin"] * fixed_delta
            alive.append(shard)
        self.chain_shards = alive

    def update_momentum_fx(self, fixed_delta):
        self.update_chain_shards(fixed_delta)
        self.player_anim_time += fixed_delta
        self.momentum_flash_timer = max(0.0, self.momentum_flash_timer - fixed_delta)
        alive = []
        for shard in self.momentum_shards:
            shard["life"] -= fixed_delta
            if shard["life"] <= 0:
                continue
            shard["vy"] -= MOMENTUM_SHARD_GRAVITY * fixed_delta
            shard["x"] += shard["vx"] * fixed_delta
            shard["y"] += shard["vy"] * fixed_delta
            shard["angle"] += shard["spin"] * fixed_delta
            alive.append(shard)
        self.momentum_shards = alive

    def gain_momentum(self):
        if self.momentum < SealGauge.MOMENTUM_MAX:
            self.momentum += 1
            self.momentum_flash_timer = MOMENTUM_FLASH_TIME

    def lose_momentum(self):
        self.momentum = max(0, self.momentum - 1)

    def break_momentum(self):
        """피격: 기세 0. 차 있던 칸마다 조각 3개를 튀긴다."""
        for index in range(self.momentum):
            cell_x = self.momentum_cell_center(index)
            for _ in range(3):
                self.momentum_shards.append(
                    {
                        "x": cell_x + self.fx_rng.uniform(-4, 4),
                        "y": self.fx_rng.uniform(-2, 2),
                        "vx": cell_x * 2.2 + self.fx_rng.uniform(-55, 55),
                        "vy": self.fx_rng.uniform(40, 120),
                        "angle": self.fx_rng.uniform(0, math.tau),
                        "spin": self.fx_rng.uniform(-14, 14),
                        "size": self.fx_rng.uniform(4.5, 7.5),
                        "life": MOMENTUM_SHATTER_TIME,
                        "max_color": self.momentum == SealGauge.MOMENTUM_MAX,
                    }
                )
        self.momentum = 0
        self.momentum_flash_timer = 0.0

    @staticmethod
    def momentum_cell_center(index):
        """index번 칸 중심의 가로 위치 (막대 가운데 기준, 플레이어 배율 단위)."""
        count = SealGauge.MOMENTUM_MAX
        step = MOMENTUM_CELL_WIDTH + MOMENTUM_CELL_GAP
        return (index - (count - 1) / 2) * step

    def update(self, fixed_delta):
        self.update_camera(fixed_delta)
        self.update_momentum_fx(fixed_delta)
        if self.boss_defeated:
            self.game_end_elapsed += fixed_delta
            if (
                not self.battle_finished
                and self.game_end_elapsed >= GAME_END_LINGER + GAME_END_FADE + GAME_END_HOLD
            ):
                self.finish_battle()
            return
        self.battle_elapsed += fixed_delta

        attack_locked = self.attack_type is not None
        previous_x = self.player_logical_x
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
        self.update_gauge(fixed_delta)

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
                    # 핵이면 게이지(적중 전 기세로), 팔이면 내구도. 앞줄 적중이면 그다음에 기세 +1
                    self.strike_boss()
                    if self.player_lane == "platform_1":
                        self.gain_momentum()
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
        self.update_player_animation(self.player_logical_x - previous_x)

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

        self.update_encounter(fixed_delta)

    def update_gauge(self, fixed_delta):
        """게이지 누수·각성 판정. 추격 구간(ChaseScene)은 게이지가 없어 아무것도 안 한다."""
        # 보스 2 장갑 단계: 게이지를 되밀 방법이 없으므로 누수를 절반으로
        self.seal_gauge.leak_scale = ARMOR_STAGE_LEAK_SCALE if self.boss.armor_intact() else 1.0
        self.seal_gauge.update(fixed_delta)
        self.boss.set_awakened(self.boss_should_awaken())

    def update_encounter(self, fixed_delta):
        """보스 패턴·피격·사망·페이즈·승리. 추격 구간은 흘러오는 위협으로 바꿔 끼운다."""
        phase_jump = self.consume_debug_phase_jump()
        if phase_jump is not None:
            self.boss_phase = phase_jump
            self.seal_gauge.set_phase(phase_jump)
            self.debug_phase = phase_jump
            self.boss.reset_for_phase(phase_jump)
            self.boss.set_awakened(self.boss_should_awaken())

        # 테스트용: 보스 시간만 느리게 흘린다 (예고·실행·후경직·공백이 모두 같은 비율로 길어진다)
        boss_delta = fixed_delta * BOSS_TEST_SPEED
        forced_pattern = None
        if self.boss.state == "rest" and self.boss.timer <= boss_delta:
            forced_pattern = self.consume_debug_forced_pattern()
        boss_attacks = self.boss.update(
            boss_delta,
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
            if boss_attack.delayed:
                # 뒷줄 시간차 타격은 퍼져 나온 여진이라 흔들림을 약하게 (60%)
                shake_strength = round(shake_strength * 0.6)
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
            if self.boss_phase == 1 and self.boss.has_armor():
                # 보스 2는 장갑이 부서져야 2페이즈 (장갑 단계엔 게이지가 안 움직여 보통 닿지 않는다)
                pass
            elif self.boss_phase == 1:
                self.boss_phase = 2
                self.seal_gauge.set_phase(2)
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
        self.momentum = 0
        self.boss.reset_for_phase(phase)
        # 각성은 강제로 끄지 않고 게이지 값에 따라 다시 판정한다
        self.boss.set_awakened(self.boss_should_awaken())

    def resolve_boss_attack(self, attack):
        if self.debug_invulnerability_enabled:
            return False
        # 회피 무적(invulnerability_timer는 회피에서만 걸린다)은 후려치기에 통하지 않는다 —
        #   좌우 회피가 아니라 뒷줄로 물러나야만 피하는 패턴이다
        if self.invulnerability_timer > 0 and attack.pattern != "backhand":
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
            return self.receive_player_hit(ignore_dodge=attack.pattern == "backhand")
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
                if self.boss.current_pattern == "slam":
                    boss_pose = "slam_impact"
                elif self.boss.current_pattern == "slam_double":
                    boss_pose = "double_impact"
                elif self.boss.current_pattern == "shockwave":
                    boss_pose = "shockwave_impact"
                elif self.boss.current_pattern == "backhand":
                    boss_pose = "backhand_impact"
        # 후려치기는 화면 왼쪽 팔(arm_l)이 왼쪽에서 오른쪽으로 쓸어친다 (PATTERN_PART)
        backhand_side = -1
        broken_sides = tuple(
            side
            for side, name in ((-1, "arm_l"), (1, "arm_r"))
            if self.boss.part_broken(name)
        )
        head_lift, eye_glow = self.boss_homing_head()

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
        # 반환값: 두 눈 사이(유도탄 발사 지점), 팔·핵·사슬의 화면 좌표
        if boss_sprite.is_available():
            self.boss_geometry = self.draw_boss_sprite(
                boss_screen_x, boss_foot_y, boss_lean_px, head_lift, eye_glow
            )
        else:
            self.boss_geometry = draw_boss_placeholder(
            self.boss_awaken_visual(),
            self.boss_hit_timer > 0,
            self.boss_defeated,
            boss_pose,
            self.boss.forward_progress,
            boss_screen_x,
            boss_foot_y,
            boss_lean_px,
            backhand_side,
            head_lift,
            eye_glow,
            broken_sides,
            )
        self.boss_eye_screen = self.boss_geometry["eye"]
        if self.boss.armor_intact():
            self.draw_armor()
        self.draw_aim_marker()

        draw_lane("platform_1", "front_lane", "front_edge", 8)
        draw_lane("platform_2", "rear_lane", "rear_edge", 10)

        self.draw_boss_status()
        self.draw_seal_gauge()
        self.draw_boss_telegraph()
        self.draw_homing_projectile()
        self.draw_active_boss_effects()
        self.draw_impact_flash()
        self.draw_chain_shards()

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
        self.draw_player(screen_x, player_y, player_scale)
        self.draw_momentum(screen_x, player_y, player_scale)
        self.draw_player_health()

        # 예전 도형 베기 선은 스프라이트가 없을 때만 — 공격 시트에 검기가 그려져 있다
        if self.attack_type is not None and not player_sprite.is_available(PLAYER_RIM_RGBA[:3]):
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
        self.draw_game_end_fade()

    def draw_game_end_fade(self):
        """2페이즈 클리어 후 화면 전체(UI 포함)를 검게 덮는다."""
        if not self.boss_defeated:
            return
        t = (self.game_end_elapsed - GAME_END_LINGER) / GAME_END_FADE
        alpha = round(255 * max(0.0, min(t, 1.0)))
        if alpha <= 0:
            return
        black = (0, 0, 0, alpha)
        draw_polygon(
            ((0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT)),
            (black, black, black, black),
        )

    def player_sprite_flipped(self):
        """바라보는 방향으로 반전하고, 홀수 번째 공격이면 한 번 더 뒤집는다 (그리기 전용).

        판정 방향(facing_direction)은 그대로다. 짝수 번째 클릭은 기본 동작, 홀수 번째는 반대 동작.
        """
        flipped = self.facing_direction < 0
        if self.player_animation == "attack" and self.attack_visual_count % 2 == 1:
            flipped = not flipped
        return flipped

    def player_attack_frame(self):
        """공격 동작 프레임 (꼬리 포함). 끝났으면 None."""
        # 판정은 공격 시간의 50%에 들어간다 (update의 attack_duration * 0.5)
        return player_sprite.attack_frame(
            self.player_anim_time, self.attack_visual_duration, 0.5
        )

    def player_sprite_frame(self):
        """(시트 이름, 프레임) — 프레임이 None이면 시간 × fps로 돈다 (대기)."""
        if self.player_animation == "attack":
            frame = self.player_attack_frame()
            if frame is not None:
                return "attack", frame
            return "idle", None
        if self.player_animation == "front_dash":
            frame = player_sprite.front_dash_frame(self.player_anim_time, LANE_SWITCH_DURATION)
            if frame is not None:
                return "front_dash", frame
            return "idle", None
        if self.player_animation == "run":
            return "run", player_sprite.run_frame(self.player_anim_time, self.run_skip_intro)
        if self.player_animation == "brake":
            frame = player_sprite.brake_frame(self.player_anim_time)
            if frame is not None:
                return "run", frame
        return "idle", None

    def draw_player(self, screen_x, foot_y, scale):
        """대기 스프라이트. 이미지를 못 읽으면 예전 도형 캐릭터로 그린다."""
        if not player_sprite.is_available(PLAYER_RIM_RGBA[:3]):
            draw_player_placeholder(screen_x, foot_y, scale)
            return
        # 발밑 그림자는 도형 캐릭터와 같다
        set_draw_color("shadow", 170, 0.7)
        draw_filled_ellipse(screen_x, foot_y + 3 * scale, 24 * scale, 8 * scale)
        sheet, frame = self.player_sprite_frame()
        player_sprite.draw(
            sheet,
            screen_x,
            foot_y,
            PLAYER_SPRITE_HEIGHT * scale,
            self.player_anim_time,
            HEIGHT,
            flip=self.player_sprite_flipped(),
            frame=frame,
            rim_px=1.5,
            rim_alpha=PLAYER_RIM_RGBA[3],
            offset=(DRAW_OFFSET_X, DRAW_OFFSET_Y),
        )

    def draw_momentum(self, screen_x, foot_y, scale):
        """플레이어 머리 위 기세 4칸. 플레이어 위치를 따라다닌다 (회피·레인 전환 중에도)."""
        center_y = foot_y + MOMENTUM_BAR_OFFSET * scale
        half_w = MOMENTUM_CELL_WIDTH * 0.5 * scale
        half_h = MOMENTUM_CELL_HEIGHT * 0.5 * scale
        slant = 2.5 * scale  # 평행사변형으로 기울여 속도감

        def cell(center_x, grow=0.0):
            hw, hh = half_w + grow, half_h + grow
            return (
                (center_x - hw - slant, center_y - hh),
                (center_x + hw - slant, center_y - hh),
                (center_x + hw + slant, center_y + hh),
                (center_x - hw + slant, center_y + hh),
            )

        if self.momentum > 0:
            maxed = self.momentum == SealGauge.MOMENTUM_MAX
            color = MOMENTUM_MAX_COLOR if maxed else MOMENTUM_COLOR
            if maxed:
                # 기세 4: 막대 뒤로 맥박치는 빛
                pulse = 0.5 + 0.5 * math.sin(self.battle_elapsed * 9.0)
                draw_radial_glow(
                    screen_x, center_y, 62 * scale, 20 * scale,
                    MOMENTUM_MAX_COLOR, round(70 + 60 * pulse),
                )
            for index in range(SealGauge.MOMENTUM_MAX):
                points = cell(screen_x + self.momentum_cell_center(index) * scale)
                if index < self.momentum:
                    rgb = color
                    newest = index == self.momentum - 1
                    if newest and self.momentum_flash_timer > 0:
                        # 새로 찬 칸: 흰색에서 강조색으로, 살짝 컸다가 제자리
                        t = self.momentum_flash_timer / MOMENTUM_FLASH_TIME
                        rgb = tuple(round(c + (255 - c) * t) for c in color)
                        points = cell(
                            screen_x + self.momentum_cell_center(index) * scale,
                            2.0 * scale * t,
                        )
                    draw_polygon(points, [rgb + (255,)] * 4)
                else:
                    # 빈 칸: 어두운 바탕 + 흐린 테두리
                    draw_polygon(points, [(10, 12, 16, 200)] * 4)
                    set_draw_rgb(*MOMENTUM_COLOR, 90)
                    draw_polyline(points)

        # 부서진 조각 — 기세가 0이어도 그린다
        for shard in self.momentum_shards:
            t = shard["life"] / MOMENTUM_SHATTER_TIME
            rgb = MOMENTUM_MAX_COLOR if shard["max_color"] else MOMENTUM_COLOR
            x = screen_x + shard["x"] * scale
            y = center_y + shard["y"] * scale
            size = shard["size"] * scale * (0.6 + 0.4 * t)
            points = [
                (
                    x + math.cos(shard["angle"] + offset) * size,
                    y + math.sin(shard["angle"] + offset) * size,
                )
                for offset in (0.0, 2.3, 4.1)
            ]
            draw_polygon(points, [rgb + (round(255 * t),)] * 3)

    def draw_debug_panel(self):
        set_draw_color("actor_dark")
        draw_filled_rectangle(20, 286, 430, 700)  # 390 → 286: PHASE MOD·MOMENTUM·PARTS·BOSS 네 줄(26px씩) 추가
        set_draw_color("rear_edge")
        draw_rectangle(20, 286, 430, 700)

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
            f"PHASE MOD  tel x{PHASE_MODIFIERS[self.boss_phase]['telegraph_scale']:.2f}  hit {PHASE_MODIFIERS[self.boss_phase]['hit_loss'] * SealGauge.GAUGE_CHANGE_SCALE:.3f}",
            f"PARTS      L {self.boss.part_durability['arm_l']}  R {self.boss.part_durability['arm_r']}"
            + (f"  A {self.boss.part_durability['armor']}" if self.boss.has_armor() else "")
            + f"  aim {self.aimed_part() or '-'}  [F8/F9]",
            f"BOSS       {self.boss_id}  rage x{self.boss.rage_scale():.2f}  [F10 switch]",
            f"MOMENTUM   {self.momentum}/{SealGauge.MOMENTUM_MAX}  gain B {self.seal_gauge.attack_gain('basic', self.momentum):.0%} H {self.seal_gauge.attack_gain('heavy', self.momentum):.0%}",
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
        progress = min(elapsed / self.boss.current_telegraph, 1.0)
        fill_alpha = 90 if visible else 0
        marker_alpha = int(60 + 140 * progress) if visible else 60

        if pattern["marker"] == "lane":
            draw_lane_marker(self.boss.target_lane, visible)
            return

        if pattern["marker"] == "sweep":
            # 후려치기: 앞줄의 판정 범위 전체를 칠한다 (각성 판정 배율 포함 — 실제 판정과 같은 폭)
            left, right = self.backhand_range()
            draw_range_marker("platform_1", left, right, visible)
            return

        if pattern["marker"] == "column":
            half_width = pattern["hitbox_width"] * 0.5
            draw_column_marker(self.boss.target_x - half_width, self.boss.target_x + half_width, visible)
            return

        targets = [(self.boss.target_lane, self.boss.target_x)]
        if pattern["marker"] == "two_spots":
            targets.append(("platform_1", self.boss.secondary_target_x))
        if self.boss.current_pattern in ("slam", "slam_double"):
            # 내리찍기는 뒷줄 같은 x에도 시간차로 닿으므로 뒷줄에도 예고를 띄운다
            targets += [("platform_2", target_x) for _, target_x in list(targets)]

        for target_lane_name, target_x in targets:
            draw_spot_marker(target_lane_name, target_x, visible, progress)

    def boss_homing_head(self):
        """유도탄 예고·발사 중 (머리 드는 양, 눈 밝기) — 0~1. 그리기 전용."""
        if self.boss.current_pattern != "homing":
            return 0.0, 0.0
        if self.boss.state == "telegraph":
            t = min(self.boss.telegraph_elapsed / self.boss.current_telegraph, 1.0)
            return t * t * (3.0 - 2.0 * t), t
        if self.boss.state == "active":
            return 1.0, 1.0
        if self.boss.state == "recovery":
            # 후경직 동안 머리를 내리고 눈빛을 거둔다
            t = 1.0 - min(self.boss.timer / PATTERNS["homing"]["recovery"], 1.0)
            return 1.0 - t, max(0.0, 1.0 - 2.0 * t)
        return 0.0, 0.0

    def draw_homing_projectile(self):
        if self.boss.current_pattern != "homing" or self.boss.state != "active":
            return

        target_x, target_y = lane_point(self.boss.target_lane, self.boss.target_x)
        progress = min(
            self.boss.attack_elapsed / PATTERNS["homing"]["duration"],
            1.0,
        )
        # 구체는 보스의 두 눈 사이에서 생겨 날아간다 (예전: 팔 높이)
        launch_x, launch_y = self.boss_eye_screen
        projectile_x = launch_x + (target_x - launch_x) * progress
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

    def boss_state_progress(self):
        """보스 현재 상태 안의 진행도 0~1 (스프라이트 포즈용)."""
        boss = self.boss
        if boss.current_pattern is None:
            return 0.0
        pattern = PATTERNS[boss.current_pattern]
        if boss.state == "telegraph":
            return min(boss.telegraph_elapsed / max(boss.current_telegraph, 1e-6), 1.0)
        if boss.state == "active":
            return min(boss.attack_elapsed / pattern["duration"], 1.0)
        if boss.state == "recovery":
            return 1.0 - min(boss.timer / pattern["recovery"], 1.0)
        return 0.0

    def draw_boss_sprite(self, center_x, burial_y, lean_px, head_lift, eye_glow):
        """스프라이트 보스. 발(몸통 아래 가운데)을 단상 윗면(burial_y)에 세운다.

        반환하는 좌표는 도형 보스와 같은 꼴(pico 좌표) + "layout"(조준 발광에 쓴다).
        """
        broken = {name for name in ("arm_l", "arm_r") if self.boss.part_broken(name)}
        pose = boss_sprite.compute_pose(
            self.boss.current_pattern,
            self.boss.state,
            self.boss_state_progress(),
            self.battle_elapsed,  # 대기 숨쉬기 시계 (전투 시간)
            broken,
            head_lift,
        )
        foot_x, foot_y = boss_sprite.foot()
        desired = (
            boss_desired_scale(self.boss_awaken_visual(), self.boss.forward_progress)
            * BOSS_VISIBLE_HEIGHT / BOSS_SPRITE_BODY_HEIGHT * view_zoom
        )
        # 칸 맨 위(머리 위로 든 팔)까지 천장 아래에 들어오게
        ceiling = (zoom_y(BOSS_CEILING_Y) - burial_y) / foot_y
        scale = min(desired, ceiling)
        # 돌진 조준: 몸 전체를 발 둘레로 기울인다. 다리까지 같이 돌아가므로 도형 보스(상체만)보다
        #   약하게 — 절반 각도, 최대 12°. 그 이상이면 한쪽 발이 단상에서 들려 보인다
        lean_angle = math.degrees(math.atan2(lean_px, BOSS_SPRITE_BODY_HEIGHT * scale * 2.0))
        lean_angle = max(-BOSS_SPRITE_MAX_LEAN, min(lean_angle, BOSS_SPRITE_MAX_LEAN))
        foot_screen = (center_x + DRAW_OFFSET_X, HEIGHT - (burial_y + DRAW_OFFSET_Y))
        layout = boss_sprite.Layout(pose, foot_screen, scale, lean_angle)

        def pico(point):
            return point[0] - DRAW_OFFSET_X, HEIGHT - point[1] - DRAW_OFFSET_Y

        # 발밑 그림자
        set_draw_color("shadow")
        draw_filled_ellipse(center_x, burial_y, 150 * scale, 12 * scale)

        tint = BOSS2_TINT_RGB if self.boss_id == 2 else None
        if self.boss_defeated:
            tint = BOSS_SPRITE_DEFEATED_RGB
        flash = self.boss_hit_timer > 0
        layout.draw("body", color=tint)
        if flash:
            layout.draw("body", "silhouette", BOSS_SPRITE_FLASH_RGB, 170)
        core = pico(layout.core())
        if eye_glow > 0:
            # 유도탄: 가슴의 붉은 핵이 밝아진다 (구체가 여기서 나간다)
            draw_radial_glow(*core, (20 + 40 * eye_glow) * scale, (18 + 34 * eye_glow) * scale,
                             (255, 120 + round(80 * eye_glow), 110), round(110 + 130 * eye_glow))

        chains = {}
        arms = {}
        for side, name in ((-1, "arm_l"), (1, "arm_r")):
            points = [pico(p) for p in layout.box_points(name)]
            arms[side] = points
            if name in broken:
                layout.draw(name, color=BOSS_SPRITE_BROKEN_RGB)
                continue
            # 사슬: 팔 가운데에서 그 아래 땅으로 — 떠 있는 팔이 대좌에 묶여 있다
            start = pico(layout.center(name))
            anchor = pico(layout.chain_anchor(name))
            draw_chain_line(*start, *anchor, scale * 1.4)
            chains[side] = (start, anchor)
            layout.draw(name, color=tint)
            if flash:
                layout.draw(name, "silhouette", BOSS_SPRITE_FLASH_RGB, 170)
        return {
            "eye": core,
            "core": (core[0], core[1], 34 * scale),
            "arms": {},
            "arm_boxes": arms,
            "chains": chains,
            "layout": layout,
            "scale": scale,
        }

    def draw_aim_marker(self):
        """지금 공격하면 맞을 부위에 윤곽·발광, 팔이면 위에 내구도 칸. 사거리 밖이면 없음."""
        geometry = self.boss_geometry
        if geometry is None:
            return
        scale = geometry["scale"]
        aimed = self.aimed_part()
        if "layout" not in geometry and self.boss.armor_intact():
            self.draw_armor_aim(aimed == "armor")
        if "layout" in geometry:
            self.draw_aim_marker_sprite(geometry, aimed)
            return
        if aimed == "core":
            x, y, radius = geometry["core"]
            draw_radial_glow(x, y, radius * 1.6, radius * 1.2, AIM_RGB, 120)
            set_draw_rgb(*AIM_RGB, 230)
            draw_polyline(
                [
                    (x + math.cos(a) * radius, y + math.sin(a) * radius * 0.8)
                    for a in (i * math.tau / 24 for i in range(24))
                ]
            )
        for side, name in ((-1, "arm_l"), (1, "arm_r")):
            arm = geometry["arms"].get(side)
            if arm is None or self.boss.part_broken(name):
                continue
            shoulder, elbow, hand = arm
            durability = self.boss.part_durability[name]
            damaged = durability < self.part_total(name)
            if aimed == name:
                # 팔 윤곽: 팔 위에 반투명 굵은 선 + 밝은 얇은 선
                set_draw_rgb(*AIM_RGB, 90)
                draw_thick_line(*shoulder, *elbow, 22 * scale, 18 * scale)
                draw_thick_line(*elbow, *hand, 18 * scale, 16 * scale)
                set_draw_rgb(170, 214, 255, 230)
                draw_polyline((shoulder, elbow, hand), closed=False)
                draw_radial_glow(*hand, 22 * scale, 22 * scale, AIM_RGB, 120)
            if aimed == name or damaged:
                self.draw_part_bar(name, shoulder, side, bright=aimed == name)

    def armor_points(self, grow=0.0):
        x, y, radius = self.boss_geometry["core"]
        r = radius * ARMOR_RADIUS_SCALE + grow
        # 위아래가 뾰족한 육각형 (가로로 조금 넓게)
        return [
            (x + math.cos(math.radians(90 + 60 * i)) * r * 1.12, y + math.sin(math.radians(90 + 60 * i)) * r)
            for i in range(6)
        ]

    def draw_armor(self):
        """보스 2 장갑판 — 핵을 덮는 육각 철판. 깎일수록 금이 늘어난다."""
        x, y, radius = self.boss_geometry["core"]
        outer = self.armor_points(3 * view_zoom)
        inner = self.armor_points()
        draw_polygon(outer, [(34, 36, 48, 255)] * 6)
        top, bottom = (104, 112, 140, 255), ARMOR_RGB + (255,)
        draw_polygon(inner, [top, top, bottom, bottom, bottom, top])
        set_draw_rgb(*ARMOR_EDGE_RGB, 220)
        draw_polyline(inner)
        r = radius * ARMOR_RADIUS_SCALE
        for i in range(6):  # 리벳
            a = math.radians(60 * i + 30)
            set_draw_rgb(*ARMOR_EDGE_RGB, 255)
            draw_filled_circle(x + math.cos(a) * r * 0.78, y + math.sin(a) * r * 0.72, 2.4 * view_zoom)
        # 금: 깎인 비율만큼 (최대 7줄). 방향은 고정이라 매 프레임 같은 자리에 남는다
        total = self.part_total("armor")
        damage = 1.0 - self.boss.part_durability["armor"] / total
        cracks = int(damage * 7 + 0.999) if damage > 0 else 0
        set_draw_rgb(20, 18, 28, 255)
        for i in range(cracks):
            a = math.radians(37 + i * 101)
            length = r * (0.55 + 0.35 * ((i * 37) % 10) / 10)
            mid = (x + math.cos(a + 0.35) * length * 0.5, y + math.sin(a + 0.35) * length * 0.5)
            draw_line(x, y, *mid)
            draw_line(*mid, x + math.cos(a) * length, y + math.sin(a) * length)

    def draw_aim_marker_sprite(self, geometry, aimed):
        """스프라이트 보스용 조준 표시: 조준한 팔 실루엣을 파랗게 덮고, 핵이면 고리."""
        layout = geometry["layout"]
        if self.boss.armor_intact():
            self.draw_armor_aim(aimed == "armor")
        if aimed == "core":
            x, y, radius = geometry["core"]
            draw_radial_glow(x, y, radius * 1.6, radius * 1.3, AIM_RGB, 120)
            set_draw_rgb(*AIM_RGB, 230)
            draw_polyline(
                [
                    (x + math.cos(a) * radius, y + math.sin(a) * radius)
                    for a in (i * math.tau / 28 for i in range(28))
                ]
            )
        for side, name in ((-1, "arm_l"), (1, "arm_r")):
            if self.boss.part_broken(name):
                continue
            points = geometry["arm_boxes"][side]
            top = max(y for _, y in points)
            center_x = sum(x for x, _ in points) / 4
            durability = self.boss.part_durability[name]
            damaged = durability < self.part_total(name)
            if aimed == name:
                layout.draw(name, "silhouette", AIM_RGB, 110)
            if aimed == name or damaged:
                self.draw_part_bar(name, (center_x, top - 14 * view_zoom), 0, bright=aimed == name)

    def part_total(self, name):
        return dict((n, d) for n, _, _, d in self.boss.parts)[name]

    def draw_armor_aim(self, aimed):
        """장갑 조준 표시: 윤곽 발광 + 내구도. 깎였으면 조준이 아니어도 흐린 막대."""
        x, y, radius = self.boss_geometry["core"]
        damaged = self.boss.part_durability["armor"] < self.part_total("armor")
        if aimed:
            draw_radial_glow(x, y, radius * 2.2, radius * 2.0, AIM_RGB, 110)
            set_draw_rgb(170, 214, 255, 240)
            draw_polyline(self.armor_points(2 * view_zoom))
        if aimed or damaged:
            top = max(py for _, py in self.armor_points())
            self.draw_part_bar("armor", (x, top - 8 * view_zoom), 0, bright=aimed)

    def draw_part_bar(self, name, shoulder, side, bright):
        """부위 내구도 칸 — 팔은 어깨 위, 장갑은 장갑 위. 조준 중이면 밝게, 아니면(깎인 부위) 흐리게."""
        total = self.part_total(name)
        left_now = self.boss.part_durability[name]
        cell_w, cell_h, gap = (v * view_zoom for v in PART_BAR_CELL)
        if total > 8:
            # 장갑(20칸)은 칸을 좁혀 팔 막대(8칸)와 비슷한 폭으로
            cell_w, gap = cell_w * 0.45, gap * 0.5
        width = total * cell_w + (total - 1) * gap
        x0 = shoulder[0] + side * 18 * view_zoom - width / 2
        y0 = shoulder[1] + 22 * view_zoom
        alpha = 255 if bright else 120
        for index in range(total):
            x = x0 + index * (cell_w + gap)
            if index < left_now:
                set_draw_rgb(*AIM_RGB, alpha)
                draw_filled_rectangle(x, y0, x + cell_w, y0 + cell_h)
            else:
                set_draw_rgb(10, 12, 16, round(alpha * 0.8))
                draw_filled_rectangle(x, y0, x + cell_w, y0 + cell_h)
                set_draw_rgb(*AIM_RGB, round(alpha * 0.4))
                draw_rectangle(x, y0, x + cell_w, y0 + cell_h)

    def draw_chain_shards(self):
        for shard in self.chain_shards:
            t = shard["life"] / CHAIN_SHARD_LIFE
            size = shard["size"] * view_zoom
            # 고리 조각: 납작한 마름모
            points = [
                (
                    shard["x"] + math.cos(shard["angle"] + offset) * size * stretch,
                    shard["y"] + math.sin(shard["angle"] + offset) * size * stretch,
                )
                for offset, stretch in ((0.0, 1.0), (1.57, 0.55), (3.14, 1.0), (4.71, 0.55))
            ]
            rgb = shard.get("rgb", CHAIN_HIGHLIGHT_RGB)
            draw_polygon(points, [rgb + (round(255 * min(1.0, t * 1.5)),)] * 4)

    def backhand_range(self):
        """후려치기 판정 범위 (논리 x). resolve_boss_attack과 같은 폭 (+ 플레이어 반폭 25 제외)."""
        hitbox_scale = BossController.AWAKENING_HITBOX_SCALE if self.boss.awakened else 1.0
        half = PATTERNS["backhand"]["hitbox_width"] * hitbox_scale * 0.5
        target = self.boss.target_x if self.boss.target_x is not None else BOSS_LOGICAL_X
        return max(0, target - half), min(PLAYER_LOGICAL_WIDTH, target + half)

    def draw_active_boss_effects(self):
        if self.boss.state != "active" or self.boss.current_pattern is None:
            return
        if self.boss.current_pattern == "backhand":
            # 쓸고 지나가는 빛의 띠: 팔이 출발한 쪽에서 조준 쪽으로 훑는다
            pattern = PATTERNS["backhand"]
            progress = min(self.boss.attack_elapsed / pattern["duration"], 1.0)
            left, right = self.backhand_range()
            from_right = False  # 왼팔(arm_l)이 왼쪽에서 오른쪽으로 쓸어친다
            width = right - left
            head = right - width * progress if from_right else left + width * progress
            tail = right if from_right else left
            fade = round(220 * (1.0 - 0.7 * progress))
            bright, dim = (255, 214, 170, fade), (255, 107, 53, 0)
            a, b = (head, tail) if from_right else (tail, head)
            lane = LANES["platform_1"]
            ends = (dim, bright) if not from_right else (bright, dim)
            wa, wb = logical_to_world_x(a), logical_to_world_x(b)
            draw_polygon(
                (
                    project(wa, lane["near"], lane["elevation"]),
                    project(wb, lane["near"], lane["elevation"]),
                    project(wb, lane["far"], lane["elevation"]),
                    project(wa, lane["far"], lane["elevation"]),
                ),
                (ends[0], ends[1], ends[1], ends[0]),
            )
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
            stage = ""
            if self.boss.armor_intact():
                stage = f"  ARMOR {self.boss.part_durability['armor']}"
            status = f"BOSS {self.boss_id} PHASE {self.boss_phase}{stage}  {state}  {pattern.upper()}"
        self.debug_font.draw(24, HEIGHT - 40, status, (240, 230, 215))
