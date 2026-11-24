"""보스 1 스프라이트 — 몸통 / 왼팔 / 오른팔 세 레이어 (tools/split_boss_sheet.py가 만든다).

원본 Boss_smash.png(6×6칸, 칸 640×360, 36프레임)는 떠 있는 두 팔로 한쪽 팔을 내리찍는 동작 하나다.
레이어를 나눠 두면:
  - 내려찍기(slam)는 원본 프레임을 그대로 쓴다 (원본을 좌우 반전해 돌 팔이 화면 오른쪽 arm_r)
  - 다른 패턴은 팔 레이어를 어깨(팔 윗끝) 기준으로 돌리고 옮겨 포즈를 만든다
  - 부서진 팔만 회색으로 처지게, 조준한 팔만 빛나게 할 수 있다

좌표는 모두 원본 칸 좌표(px, 왼쪽 위 0). 그릴 때 scale(화면 px / 칸 px)을 곱한다.
"""

import json
import math
import os

import sdl2

import player_sprite

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
LAYERS = ("body", "arm_l", "arm_r")
CELL = (640, 360)
COLUMNS = 6
DOWNSAMPLE = player_sprite.DOWNSAMPLE

# 프레임 구간 (원본 smash 시트, 반전 후 기준)
IDLE_SEQUENCE = list(range(29, 36)) + list(range(0, 4))  # 거의 정지한 숨쉬기 — 왕복 재생
IDLE_FPS = 10
SMASH_RAISE = (4, 17)  # 오른팔을 들어 머리 위로 (12~17은 머리 위에서 멈춤)
SMASH_SWING = (18, 19)  # 휘둘러 내림
SMASH_IMPACT = 20  # 착탄 — 판정 순간
SMASH_RECOVER = (20, 28)  # 반동 후 대기 자세로
REFERENCE_FRAME = 0  # 회전으로 포즈를 만들 때 쓰는 팔 모양 (대기)

# 팔 회전 기준점 = 팔 윗끝(어깨 쪽 뾰족한 끝). 대기 프레임 경계 상자 위 가운데에서 조금 아래
ARM_PIVOT_DROP = 14
# 사슬이 묶이는 땅 위치 (발 기준 좌우 거리, 칸 px) — 대기 자세 팔 바로 아래
CHAIN_ANCHOR_SPREAD = 200

_state = None


def is_available():
    global _state
    if _state is None:
        _state = _load() or False
    return bool(_state)


def _load():
    meta_path = os.path.join(ASSET_DIR, "boss_layers.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, encoding="utf-8") as fp:
        meta = json.load(fp)
    sheets = {}
    for name in LAYERS:
        path = os.path.join(ASSET_DIR, f"boss_{name}.png")
        # 실루엣은 흰색으로 만들어 두고 그릴 때 색을 곱한다 (조준 발광, 피격 번쩍임)
        sheet = player_sprite.load_sheet(path, (255, 255, 255))
        if not sheet:
            return None
        sheets[name] = sheet
    frames = meta["frames"]
    pivots = {}
    for name in ("arm_l", "arm_r"):
        x0, y0, x1, _ = frames[REFERENCE_FRAME]["boxes"][name]
        pivots[name] = ((x0 + x1) / 2, y0 + ARM_PIVOT_DROP)
    return {"sheets": sheets, "frames": frames, "foot": tuple(meta["foot"]), "pivots": pivots}


def foot():
    return _state["foot"]


def frame_box(name, frame):
    return _state["frames"][frame]["boxes"][name]


def idle_frame(time):
    seq = IDLE_SEQUENCE + IDLE_SEQUENCE[-2:0:-1]  # 왕복
    return seq[int(time * IDLE_FPS) % len(seq)]


def _lerp(a, b, t):
    return a + (b - a) * max(0.0, min(t, 1.0))


def _ease(t):
    t = max(0.0, min(t, 1.0))
    return t * t * (3.0 - 2.0 * t)


def _frame_lerp(span, t):
    first, last = span
    return int(round(_lerp(first, last, t)))


def compute_pose(pattern, state, t, idle_time, broken, lift=0.0):
    """레이어별 (프레임, 회전°, dx, dy). 회전은 화면 시계 방향이 +.

    pattern/state: 보스의 현재 패턴과 상태 (telegraph / active / recovery / rest …).
    t: 그 상태 안의 진행도 0~1. broken: 부서진 팔 이름 집합. lift: 유도탄 예고 때 몸을 드는 양 0~1.
    """
    base = idle_frame(idle_time)
    pose = {name: [base, 0.0, 0.0, 0.0] for name in LAYERS}

    def arm(name, angle, dx=0.0, dy=0.0):
        pose[name] = [REFERENCE_FRAME, angle, dx, dy]

    if pattern in ("slam", "slam_double") and state in ("telegraph", "active", "recovery"):
        # 원본 내리찍기 프레임 — 몸통과 두 팔 모두 같은 프레임(몸이 같이 흔들린다)
        if state == "telegraph":
            if t < 0.75:
                frame = _frame_lerp(SMASH_RAISE, t / 0.75)
            else:
                frame = _frame_lerp(SMASH_SWING, (t - 0.75) / 0.25)
        elif state == "active" and pattern == "slam":
            frame = SMASH_IMPACT
        elif state == "active":
            frame = _frame_lerp(SMASH_RECOVER, t * 0.6)
        else:
            frame = _frame_lerp(SMASH_RECOVER, t)
        for name in LAYERS:
            pose[name] = [frame, 0.0, 0.0, 0.0]
        if pattern == "slam_double":
            # 왼팔은 원본에 동작이 없어 회전으로 만든다: 예고 동안 수평 위로 들고,
            #   두 번째 타격(실행 시간의 2/3)에 내리꽂는다
            #   (82°·위로 8: 더 들면 앞줄 줌에서 주먹이 천장(615)을 넘는다)
            if state == "telegraph":
                arm("arm_l", _lerp(0, 82, _ease(t)), 0, _lerp(0, -8, _ease(t)))
            elif state == "active":
                drop = _ease((t - 0.45) / 0.22)
                arm("arm_l", _lerp(82, -8, drop), 0, _lerp(-8, 26, drop))
            else:
                arm("arm_l", _lerp(-8, 0, _ease(t)), 0, _lerp(26, 0, _ease(t)))
    elif pattern == "backhand" and state in ("telegraph", "active", "recovery"):
        # 왼팔: 수평으로 젖혔다가(예고) 몸 앞을 가로질러 오른쪽으로 쓸어친다(실행)
        if state == "telegraph":
            arm("arm_l", _lerp(0, 88, _ease(t)), 0, _lerp(0, 4, _ease(t)))
        elif state == "active":
            arm("arm_l", _lerp(88, -72, _ease(t)), _lerp(0, 60, _ease(t)), _lerp(4, 10, t))
        else:
            arm("arm_l", _lerp(-72, 0, _ease(t)), _lerp(60, 0, _ease(t)), _lerp(10, 0, t))
    elif pattern == "shockwave" and state in ("telegraph", "active", "recovery"):
        # 양팔을 수평으로 벌려 들었다가 땅으로 내리꽂는다
        if state == "telegraph":
            spread, rise = _ease(t), _ease(t)
            # 82°: 수평보다 조금 아래 — 더 벌리면 앞줄 줌(1.12)에서 주먹이 화면 밖으로 나간다
            arm("arm_l", 82 * spread, 22 * rise, -14 * rise)
            arm("arm_r", -82 * spread, -22 * rise, -14 * rise)
            pose["body"][3] = -10 * rise
        elif state == "active":
            slam = _ease(t * 2.0)
            arm("arm_l", _lerp(82, -6, slam), _lerp(22, 0, slam), _lerp(-14, 34, slam))
            arm("arm_r", _lerp(-82, 6, slam), _lerp(-22, 0, slam), _lerp(-14, 34, slam))
            pose["body"][3] = _lerp(-10, 8, slam)
        else:
            settle = _ease(t)
            arm("arm_l", _lerp(-6, 0, settle), 0, _lerp(34, 0, settle))
            arm("arm_r", _lerp(6, 0, settle), 0, _lerp(34, 0, settle))
            pose["body"][3] = _lerp(8, 0, settle)
    elif pattern == "charge" and state in ("telegraph", "active", "recovery"):
        # 팔을 몸 뒤로 당긴다. 몸 전체 기울기는 장면이 돌진 조준 기울기로 준다
        pull = _ease(t) if state == "telegraph" else (1.0 if state == "active" else 1.0 - _ease(t))
        arm("arm_l", -24 * pull, 18 * pull, -8 * pull)
        arm("arm_r", 24 * pull, -18 * pull, -8 * pull)
    if lift > 0:
        # 유도탄: 몸을 들고 팔을 살짝 벌린다 (핵이 빛나는 건 장면이 그린다)
        pose["body"][3] -= 14 * lift
        for name, sign in (("arm_l", 1), ("arm_r", -1)):
            if pose[name][0] != REFERENCE_FRAME or pose[name][1] == 0:
                arm(name, sign * 16 * lift, 0, -18 * lift)

    for name in broken:
        # 부서진 팔: 대기 모양으로 바깥쪽으로 기울어 아래로 처진 채 남는다
        sign = 1 if name == "arm_l" else -1
        pose[name] = [REFERENCE_FRAME, sign * 28.0, -sign * 6.0, 46.0]
    return pose


def _rotate(x, y, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


class Layout:
    """한 프레임의 화면 배치. 레이어 그리기와 부위 좌표(SDL 좌표, 위가 0)를 함께 계산한다."""

    def __init__(self, pose, foot_screen, scale, global_angle):
        self.pose = pose
        self.foot_screen = foot_screen  # SDL 좌표
        self.scale = scale
        self.global_angle = global_angle

    def _pivot(self, name):
        if name == "body":
            return _state["foot"]
        frame, angle, _, _ = self.pose[name]
        if frame == REFERENCE_FRAME or angle != 0:
            return _state["pivots"][name]
        x0, y0, x1, _ = frame_box(name, frame)
        return ((x0 + x1) / 2, y0 + ARM_PIVOT_DROP)

    def to_screen(self, name, x, y):
        """레이어 name의 칸 좌표 한 점 → SDL 화면 좌표."""
        frame, angle, dx, dy = self.pose[name]
        px, py = self._pivot(name)
        fx, fy = _state["foot"]
        # 1) 레이어 자체 회전(기준점 둘레) 2) 이동 3) 몸 전체 기울기(발 둘레) 4) 배율
        lx, ly = _rotate(x - px, y - py, angle)
        cx, cy = px + dx + lx - fx, py + dy + ly - fy
        gx, gy = _rotate(cx, cy, self.global_angle)
        return self.foot_screen[0] + gx * self.scale, self.foot_screen[1] + gy * self.scale

    def draw(self, name, texture_key="sprite", color=None, alpha=255):
        sheet = _state["sheets"][name]
        texture = sheet[texture_key]
        if texture is None:
            return
        frame, angle, _, _ = self.pose[name]
        cell_w, cell_h = sheet["cell"]  # 다운샘플된 칸
        column, row = frame % COLUMNS, frame // COLUMNS
        source = sdl2.SDL_Rect(column * cell_w, row * cell_h, cell_w, cell_h)
        px, py = self._pivot(name)
        sx, sy = self.to_screen(name, px, py)
        dst = sdl2.SDL_FRect(
            sx - px * self.scale, sy - py * self.scale, CELL[0] * self.scale, CELL[1] * self.scale
        )
        center = sdl2.SDL_FPoint(px * self.scale, py * self.scale)
        r, g, b = color or (255, 255, 255)
        sdl2.SDL_SetTextureColorMod(texture, r, g, b)
        sdl2.SDL_SetTextureAlphaMod(texture, alpha)
        sdl2.SDL_RenderCopyExF(
            player_sprite._renderer(), texture, source, dst,
            self.global_angle + angle, center, sdl2.SDL_FLIP_NONE,
        )
        sdl2.SDL_SetTextureColorMod(texture, 255, 255, 255)
        sdl2.SDL_SetTextureAlphaMod(texture, 255)

    def box_points(self, name):
        frame = self.pose[name][0]
        x0, y0, x1, y1 = frame_box(name, frame)
        return [self.to_screen(name, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]

    def center(self, name):
        frame = self.pose[name][0]
        x0, y0, x1, y1 = frame_box(name, frame)
        return self.to_screen(name, (x0 + x1) / 2, (y0 + y1) / 2)

    def core(self):
        frame = self.pose["body"][0]
        cx, cy = _state["frames"][frame]["core"]
        return self.to_screen("body", cx, cy)

    def chain_anchor(self, name):
        fx, fy = _state["foot"]
        sign = -1 if name == "arm_l" else 1
        gx, gy = _rotate(sign * CHAIN_ANCHOR_SPREAD, 0, self.global_angle)
        return self.foot_screen[0] + gx * self.scale, self.foot_screen[1] + gy * self.scale
