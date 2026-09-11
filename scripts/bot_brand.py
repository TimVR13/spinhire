#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Картинки бота: приветственный баннер и аватарка.

Баннер уходит первым сообщением на /start (Telegram показывает его крупно,
пустой текстовый экран выглядит как служебный скрипт). Аватарку API бота
поставить не умеет — её загружает владелец через @BotFather /setuserpic.

    python3 scripts/bot_brand.py

Пишет img/bot-welcome.jpg (едет в репозиторий, отдаётся с сайта) и
assets/brand/bot/avatar.png.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from server import tgcards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNER = os.path.join(ROOT, "img", "bot-welcome.jpg")
AVATAR = os.path.join(ROOT, "assets", "brand", "bot", "avatar.png")
FAVICON = os.path.join(ROOT, "favicon.svg")

TITLE = "SPINHIRE"
SUB = "Работа в казино, беттинге и партнёрках"
CHIPS = ("СНГ · Европа · удалёнка", "Отклик в один тап", "Резюме файлом или ссылкой")


def mark(size: int):
    """Фирменный знак из favicon.svg — через rsvg-convert, он есть и на маке, и на дроплете."""
    png = os.path.join("/tmp", f"spinhire-mark-{size}.png")
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), FAVICON, "-o", png],
                   check=True)
    return Image.open(png).convert("RGBA")


def banner():
    img, draw = tgcards._canvas(tgcards.GREEN, seed=0)
    logo = mark(96)
    img.paste(logo, (72, 92), logo)
    tgcards._shadowed(draw, (188, 94), TITLE, tgcards._font(78, "black"), tgcards.WHITE)
    tgcards._fit(draw, SUB, 74, 228, 640, 46, tgcards.GREEN, "bold")

    y = 330
    for i, chip in enumerate(CHIPS):
        font = tgcards._font(34, "bold")
        width = draw.textlength(chip, font=font) + 56
        color = (tgcards.CYAN, tgcards.PINK, tgcards.GOLD)[i % 3]
        draw.rounded_rectangle([74, y, 74 + width, y + 66], radius=33,
                               outline=color, width=3)
        draw.text((102, y + 15), chip, font=font, fill=tgcards.WHITE)
        y += 84

    tgcards._shadowed(draw, (74, H_FOOT), "spinhire.io", tgcards._font(36, "bold"),
                      tgcards.MUTE)
    img.save(BANNER, quality=90)
    return BANNER


H_FOOT = 632


def avatar(size: int = 640):
    """Квадрат под круглую обрезку: знак крупно, но с полями, чтобы круг ничего не срезал."""
    img = Image.new("RGB", (size, size), (8, 11, 14))
    # без рамки по краю: Telegram обрезает аватарку в круг ровно по ней
    inner = int(size * 0.66)
    logo = mark(inner)
    img.paste(logo, ((size - inner) // 2, (size - inner) // 2), logo)
    img.save(AVATAR)
    return AVATAR


if __name__ == "__main__":
    print(banner())
    print(avatar())
