"""플레이어 스프라이트 (대기 idle / 달리기 run / 공격 attack).

세 시트 모두 3840×2160, 6열 × 6행, 칸 640×360, 배경 투명, 뒷모습(보스를 바라봄).
  player_idle.png  : 35프레임 (마지막 칸 비어 있음)
  player_run.png   : 36프레임 — 0~8 출발(대기 → 숙인 자세), 9~20 달리기 반복, 21~35 감속 → 대기
  player_attack.png: 36프레임 — 0~6 준비, 7~17 회전 베기(검기), 18~27 거두기, 28~35는 대기와 거의 같다
같은 좌표계로 그려져 있어 발 기준점을 공유한다 — 발 중심 x ≈ 326, 발바닥 y ≈ 332
(칸 왼쪽 위 기준), 머리 꼭대기 y ≈ 30 → 캐릭터 키 ≈ 302px. 달리기는 발이 뜨는 프레임이
있어 발바닥이 314~334로 오르내리는데, 기준점을 고정해야 그 들썩임이 그대로 산다.

원본을 화면 키 80~100px로 3배 넘게 줄이면 선형 보간으로도 자글거린다. 그래서 처음 그릴 때
GPU로 한 번 절반 크기로 줄인 시트(칸 320×180)를 만들어 쓴다 (정확히 2배 축소 + 선형 보간 =
2×2 평균). 같은 픽셀로 림 라이트용 단색 실루엣도 만든다.
"""

import ctypes
import os

import pico2d
import sdl2
import sdl2.sdlimage as sdlimage

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_COLUMNS = 6
SOURCE_CELL = (640, 360)
SOURCE_FOOT = (326, 332)  # 칸 안 발 중심 (왼쪽 위 기준)
SOURCE_HEIGHT = 302  # 발바닥 ~ 머리 꼭대기
DOWNSAMPLE = 2  # GPU로 한 번 줄이는 배율

# 달리기 시트 구간. 반복 9~20은 프레임 윤곽을 비교해 고른 이음매가 가장 매끄러운 구간
#   (20 → 9 겹침 0.78, 이웃 프레임끼리 평균 ≈ 0.70)
RUN_INTRO_END = 8  # 0~8: 출발, 한 번만
RUN_LOOP = (9, 20)  # 반복
RUN_BRAKE = (27, 35)  # 멈출 때 한 번 재생하고 대기로 (28 이후는 대기 자세와 거의 같다)
# 36fps: 출발 0.25초, 반복 한 주기(12프레임) 0.33초. 이동 속도(뒷줄 ≈ 420px/s)에 발이 맞는 빠르기
RUN_FPS = 36

SHEETS = {
    # 대기: 35프레임 / 24fps ≈ 1.46초 한 주기 — 숨 쉬는 속도에 가깝다
    "idle": {"file": "player_idle.png", "frames": 35, "fps": 24},
    # 달리기: 고정 반복이 아니라 출발·반복·제동 구간으로 나눠 쓴다 (run_frame / brake_frame).
    #   36프레임을 통째로 돌리면 반복할 때마다 대기 자세로 일어섰다 다시 숙인다
    "run": {"file": "player_run.png", "frames": 36, "fps": RUN_FPS},
    # 공격: 고정 fps가 아니라 공격 시간에 맞춰 늘이고 줄인다 (attack_frame 참고).
    #   기본 공격 0.25초와 강공격 0.70초가 같은 시트를 쓴다
    "attack": {"file": "player_attack.png", "frames": 36, "fps": 0},
}

# 검기가 몸 앞을 크게 지나는 프레임. 판정이 들어가는 순간(공격 시간의 50%)에 이 프레임이 오게 한다
ATTACK_HIT_FRAME = 10
# 칼을 거둬 대기 자세로 돌아온 프레임. 28 이후는 대기와 거의 같아 공격 시간을 늘리기만 한다
ATTACK_END_FRAME = 27


# 판정 뒤(검기 → 칼 거두기) 구간을 공격 시간보다 이만큼 길게 재생한다. 판정 전은 판정 시점에
#   베기 프레임이 와야 해서 늘일 수 없다. 공격이 끝난 뒤 남는 꼬리는 서 있는 동안만 재생되고,
#   움직이거나 다시 공격하면 바로 끊긴다 (판정·이동은 그대로).
#   기본 공격 판정 뒤 0.125초 → 0.21초, 강공격 0.35초 → 0.6초
ATTACK_RECOVER_SLOWDOWN = 1.7


def attack_frame(elapsed, duration, hit_ratio=0.5):
    """공격 시작 후 경과 시간 → 공격 시트 프레임 (끝나면 None).

    판정 시점(duration × hit_ratio)에 ATTACK_HIT_FRAME이 오고, 그 뒤는
    ATTACK_RECOVER_SLOWDOWN만큼 느리게 ATTACK_END_FRAME까지 간다.
    """
    hit_time = duration * hit_ratio
    if elapsed < hit_time:
        return int(ATTACK_HIT_FRAME * max(elapsed, 0.0) / hit_time)
    recover_time = (duration - hit_time) * ATTACK_RECOVER_SLOWDOWN
    frame = ATTACK_HIT_FRAME + (ATTACK_END_FRAME - ATTACK_HIT_FRAME) * (
        (elapsed - hit_time) / recover_time
    )
    if frame > ATTACK_END_FRAME + 0.999:
        return None
    return min(int(frame), ATTACK_END_FRAME)


def run_frame(elapsed, skip_intro=False):
    """달리기 시작 후 경과 시간 → 프레임. 제동 중에 다시 달리면 출발 구간을 건너뛴다."""
    count = int(elapsed * RUN_FPS)
    if skip_intro:
        count += RUN_INTRO_END + 1
    if count <= RUN_INTRO_END:
        return count
    loop_start, loop_end = RUN_LOOP
    return loop_start + (count - RUN_INTRO_END - 1) % (loop_end - loop_start + 1)


def brake_frame(elapsed):
    """멈춘 뒤 경과 시간 → 제동 프레임 (끝나면 None)."""
    frame = RUN_BRAKE[0] + int(elapsed * RUN_FPS)
    return frame if frame <= RUN_BRAKE[1] else None

_sheets = None  # 처음 쓸 때 만든다: {이름: {"sprite", "silhouette", "cell", "foot", "height"}}


def _renderer():
    return pico2d.open_canvas.__globals__.get("renderer")


def _load_sheet(path, rim_rgb):
    renderer = _renderer()
    surface = sdlimage.IMG_Load(path.encode("utf-8"))
    if not surface:
        return None
    full = sdl2.SDL_CreateTextureFromSurface(renderer, surface)
    sheet_w, sheet_h = surface.contents.w, surface.contents.h
    sdl2.SDL_FreeSurface(surface)

    half_w, half_h = sheet_w // DOWNSAMPLE, sheet_h // DOWNSAMPLE
    target = sdl2.SDL_CreateTexture(
        renderer,
        sdl2.SDL_PIXELFORMAT_ARGB8888,
        sdl2.SDL_TEXTUREACCESS_TARGET,
        half_w,
        half_h,
    )
    if not target:
        # 렌더 타깃을 못 쓰는 환경이면 원본 그대로 쓴다 (실루엣 없이)
        sdl2.SDL_SetTextureBlendMode(full, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_SetTextureScaleMode(full, sdl2.SDL_ScaleModeLinear)
        return {
            "sprite": full,
            "silhouette": None,
            "cell": SOURCE_CELL,
            "foot": SOURCE_FOOT,
            "height": SOURCE_HEIGHT,
        }

    # 1) 절반 크기로 축소 — 알파를 그대로 옮기려고 블렌드 없이 복사한다
    previous_target = sdl2.SDL_GetRenderTarget(renderer)
    sdl2.SDL_SetTextureScaleMode(full, sdl2.SDL_ScaleModeLinear)
    sdl2.SDL_SetTextureBlendMode(full, sdl2.SDL_BLENDMODE_NONE)
    sdl2.SDL_SetRenderTarget(renderer, target)
    sdl2.SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0)
    sdl2.SDL_RenderClear(renderer)
    sdl2.SDL_RenderCopy(renderer, full, None, sdl2.SDL_Rect(0, 0, half_w, half_h))

    # 2) 축소된 픽셀을 읽어 정적 텍스처 두 장(원본색 / 단색 실루엣)으로 만든다
    pitch = half_w * 4
    pixels = (ctypes.c_ubyte * (pitch * half_h))()
    sdl2.SDL_RenderReadPixels(
        renderer, None, sdl2.SDL_PIXELFORMAT_ARGB8888, pixels, pitch
    )
    sdl2.SDL_SetRenderTarget(renderer, previous_target)
    sdl2.SDL_DestroyTexture(target)
    sdl2.SDL_DestroyTexture(full)

    def static_texture(data):
        texture = sdl2.SDL_CreateTexture(
            renderer,
            sdl2.SDL_PIXELFORMAT_ARGB8888,
            sdl2.SDL_TEXTUREACCESS_STATIC,
            half_w,
            half_h,
        )
        sdl2.SDL_UpdateTexture(texture, None, data, pitch)
        sdl2.SDL_SetTextureBlendMode(texture, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_SetTextureScaleMode(texture, sdl2.SDL_ScaleModeLinear)
        return texture

    sprite = static_texture(pixels)
    # ARGB8888은 리틀 엔디언 메모리에서 B, G, R, A 순서. 알파는 그대로 두고 색만 바꾼다
    rim = bytearray(pixels)
    count = half_w * half_h
    red, green, blue = rim_rgb
    rim[0::4] = bytes((blue,)) * count
    rim[1::4] = bytes((green,)) * count
    rim[2::4] = bytes((red,)) * count
    silhouette = static_texture((ctypes.c_ubyte * len(rim)).from_buffer(rim))

    return {
        "sprite": sprite,
        "silhouette": silhouette,
        "cell": (SOURCE_CELL[0] // DOWNSAMPLE, SOURCE_CELL[1] // DOWNSAMPLE),
        "foot": (SOURCE_FOOT[0] / DOWNSAMPLE, SOURCE_FOOT[1] / DOWNSAMPLE),
        "height": SOURCE_HEIGHT / DOWNSAMPLE,
    }


def is_available(rim_rgb):
    """두 시트를 (처음 한 번) 읽는다. 대기 시트가 없으면 False — 도형 캐릭터로 대신 그린다."""
    global _sheets
    if _sheets is None:
        _sheets = {}
        for name, info in SHEETS.items():
            loaded = _load_sheet(os.path.join(ASSET_DIR, info["file"]), rim_rgb)
            if loaded:
                _sheets[name] = loaded
    return "idle" in _sheets


def draw(animation, foot_x, foot_y, screen_height, anim_time, canvas_height,
         flip=False, rim_px=0.0, rim_alpha=0, offset=(0, 0), frame=None):
    """발 중심(foot_x, foot_y — pico2d 좌표, 아래가 0)에 키 screen_height px로 그린다.

    animation: "idle" / "run" / "attack" (없으면 idle). flip: 좌우 반전 (왼쪽을 볼 때).
    frame: 프레임을 직접 정할 때 (공격). None이면 anim_time × fps.
    """
    if not _sheets:
        return
    requested = animation
    if animation not in _sheets:
        animation = "idle"
    state = _sheets[animation]
    info = SHEETS[animation]
    renderer = _renderer()
    cell_w, cell_h = state["cell"]
    foot_cx, foot_cy = state["foot"]
    scale = screen_height / state["height"]
    if frame is None or animation != requested:
        frame = int(anim_time * info["fps"]) % info["frames"]
    column, row = frame % SHEET_COLUMNS, frame // SHEET_COLUMNS
    source = sdl2.SDL_Rect(column * cell_w, row * cell_h, cell_w, cell_h)

    # SDL 좌표는 위가 0. 발 기준점이 (foot_x, foot_y)에 오도록 칸 왼쪽 위를 정한다.
    # 반전하면 칸 안 발 위치도 거울상(cell_w - foot_cx)이 된다
    anchor_x = (cell_w - foot_cx) if flip else foot_cx
    left = foot_x + offset[0] - anchor_x * scale
    top = (canvas_height - (foot_y + offset[1])) - foot_cy * scale
    width, height = cell_w * scale, cell_h * scale
    flip_flag = sdl2.SDL_FLIP_HORIZONTAL if flip else sdl2.SDL_FLIP_NONE

    def copy(texture, dx=0.0, dy=0.0):
        sdl2.SDL_RenderCopyExF(
            renderer, texture, source,
            sdl2.SDL_FRect(left + dx, top + dy, width, height),
            0.0, None, flip_flag,
        )

    silhouette = state["silhouette"]
    if silhouette is not None and rim_px > 0 and rim_alpha > 0:
        # 림 라이트: 단색 실루엣을 상하좌우로 조금씩 밀어 깐 뒤 본 스프라이트를 덮는다
        sdl2.SDL_SetTextureAlphaMod(silhouette, rim_alpha)
        for dx, dy in ((rim_px, 0), (-rim_px, 0), (0, rim_px), (0, -rim_px)):
            copy(silhouette, dx, dy)
    copy(state["sprite"])
