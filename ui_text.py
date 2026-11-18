"""씬 UI용 글꼴 로드·가운데 정렬. 한글이 나와야 하므로 맑은 고딕을 쓴다."""

import os
from ctypes import byref, c_int

import pico2d
from sdl2 import sdlttf

FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
_cache = {}


def font(size, bold=False):
    """캔버스가 열린 뒤에만 부른다. 맑은 고딕이 없으면 consola로 대신한다 (한글은 깨진다)."""
    key = (size, bold)
    if key not in _cache:
        names = ("malgunbd.ttf" if bold else "malgun.ttf", "consola.ttf")
        for name in names:
            try:
                _cache[key] = pico2d.load_font(os.path.join(FONT_DIR, name), size)
                break
            except (OSError, RuntimeError):
                continue
        else:
            _cache[key] = None
    return _cache[key]


def text_width(loaded_font, text):
    width, height = c_int(0), c_int(0)
    sdlttf.TTF_SizeUTF8(loaded_font.font, text.encode("utf-8"), byref(width), byref(height))
    return width.value


def draw_text(x, y, text, size, color, bold=False, align="left"):
    """y는 글자 세로 중심. align: left / center / right."""
    loaded = font(size, bold)
    if loaded is None or not text:
        return
    if align == "center":
        x -= text_width(loaded, text) / 2
    elif align == "right":
        x -= text_width(loaded, text)
    loaded.draw(x, y, text, color)
