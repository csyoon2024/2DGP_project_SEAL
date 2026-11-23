"""플레이어 대기(idle) 스프라이트.

player_idle.png: 3840×2160, 6열 × 6행, 칸 640×360, 35프레임(마지막 칸 비어 있음), 배경 투명.
모든 프레임에서 발 위치가 같다 — 발 중심 x ≈ 326, 발바닥 y ≈ 332 (칸 왼쪽 위 기준),
머리 꼭대기 y ≈ 30 → 캐릭터 키 ≈ 302px.

원본을 화면 키 80~100px로 3배 넘게 줄이면 선형 보간으로도 자글거린다. 그래서 처음 그릴 때
GPU로 한 번 절반 크기로 줄인 시트(칸 320×180)를 만들어 쓴다 (정확히 2배 축소 + 선형 보간 =
2×2 평균). 같은 픽셀로 림 라이트용 단색 실루엣도 만든다.
"""

import ctypes
import os

import pico2d
import sdl2
import sdl2.sdlimage as sdlimage

SHEET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_idle.png")
SHEET_COLUMNS = 6
FRAME_COUNT = 35
SOURCE_CELL = (640, 360)
SOURCE_FOOT = (326, 332)  # 칸 안 발 중심 (왼쪽 위 기준)
SOURCE_HEIGHT = 302  # 발바닥 ~ 머리 꼭대기
DOWNSAMPLE = 2  # GPU로 한 번 줄이는 배율

# 대기 동작 재생 속도. 35프레임 / 24fps ≈ 1.46초 한 주기 — 숨 쉬는 속도에 가깝다
IDLE_FPS = 24

_state = None  # 처음 그릴 때 만든다: {"sprite", "silhouette", "cell", "foot", "height"}


def _renderer():
    return pico2d.open_canvas.__globals__.get("renderer")


def _load(rim_rgb):
    renderer = _renderer()
    surface = sdlimage.IMG_Load(SHEET_PATH.encode("utf-8"))
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
    global _state
    if _state is None:
        _state = _load(rim_rgb) or False
    return bool(_state)


def draw_idle(foot_x, foot_y, screen_height, anim_time, canvas_height,
              rim_px=0.0, rim_alpha=0, offset=(0, 0)):
    """발 중심(foot_x, foot_y — pico2d 좌표, 아래가 0)에 키 screen_height px로 그린다."""
    state = _state
    if not state:
        return
    renderer = _renderer()
    cell_w, cell_h = state["cell"]
    foot_cx, foot_cy = state["foot"]
    scale = screen_height / state["height"]
    frame = int(anim_time * IDLE_FPS) % FRAME_COUNT
    column, row = frame % SHEET_COLUMNS, frame // SHEET_COLUMNS
    source = sdl2.SDL_Rect(column * cell_w, row * cell_h, cell_w, cell_h)

    # SDL 좌표는 위가 0. 발 기준점이 (foot_x, foot_y)에 오도록 칸 왼쪽 위를 정한다
    left = foot_x + offset[0] - foot_cx * scale
    top = (canvas_height - (foot_y + offset[1])) - foot_cy * scale
    width, height = cell_w * scale, cell_h * scale

    silhouette = state["silhouette"]
    if silhouette is not None and rim_px > 0 and rim_alpha > 0:
        # 림 라이트: 단색 실루엣을 상하좌우로 조금씩 밀어 깐 뒤 본 스프라이트를 덮는다
        sdl2.SDL_SetTextureAlphaMod(silhouette, rim_alpha)
        for dx, dy in ((rim_px, 0), (-rim_px, 0), (0, rim_px), (0, -rim_px)):
            sdl2.SDL_RenderCopyF(
                renderer, silhouette, source,
                sdl2.SDL_FRect(left + dx, top + dy, width, height),
            )
    sdl2.SDL_RenderCopyF(
        renderer, state["sprite"], source, sdl2.SDL_FRect(left, top, width, height)
    )
