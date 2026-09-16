"""把界面截图拼成一张总览图（README / 宣传物料用）。

输出 4 列网格，每格带标题条与细边框，桌面端 + 移动端混排。
用法：python3 scripts/media/contact_sheet.py
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path("/workspace/scholarhub-media/screenshots")
OUT = Path("/workspace/scholarhub-media/screenshots-overview.png")
LOGO = Path("/workspace/scholarhub/docs/assets/logo.svg")

ITEMS = [
    ("01-home.png", "概览 Overview"),
    ("02-catalog.png", "资源目录 Catalog"),
    ("03-resource-detail.png", "资源详情 Detail"),
    ("04-dashboard.png", "个人面板 Dashboard"),
    ("05-editor-workbench.png", "编辑工作台 Editor"),
    ("06-reviewer-workbench.png", "审稿工作台 Reviewer"),
    ("07-my-submissions.png", "我的提交 Submissions"),
    ("08-admin-users.png", "用户管理 Users"),
    ("09-admin-audit.png", "审计日志 Audit"),
    ("10-ingest.png", "元数据导入 Ingest"),
    ("11-recommendations.png", "个性化推荐 Recommend"),
    ("12-library.png", "阅读列表 Library"),
    ("13-notifications.png", "通知中心 Notifications"),
    ("14-admin-journal.png", "期刊设置 Journal"),
    ("15-account-security.png", "账号安全 Security"),
    ("16-follows.png", "关注与订阅 Follows"),
    ("17-reader.png", "在线阅读器 Reader"),
    ("mobile-catalog.png", "移动端 · 目录 Mobile"),
    ("mobile-detail.png", "移动端 · 详情 Mobile"),
]

COLS = 4
CELL_W = 460
CAP_H = 42
THUMB_H = CELL_W * 900 // 1440  # 桌面截图 1440×900 等比
PAD = 16
HEADER_H = 120
BORDER = 2

BG = (255, 255, 255)
FRAME = (226, 232, 240)
CAP_BG = (248, 250, 252)
INK = (15, 23, 42)
MUTED = (100, 116, 139)

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def main() -> None:
    present = [(f, label) for f, label in ITEMS if (SRC / f).exists()]
    rows = (len(present) + COLS - 1) // COLS
    W = COLS * (CELL_W + PAD) + PAD
    H = HEADER_H + rows * (THUMB_H + CAP_H + PAD) + PAD

    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)

    # ---- 标题区 ----
    draw.text(
        (PAD + 4, 30),
        "ScholarHUB · 界面总览",
        font=font(FONT_BOLD, 34),
        fill=INK,
    )
    draw.text(
        (PAD + 4, 74),
        "11 个后端模块 · 投稿 / 审稿 / 发表 / 阅读全流程 · 桌面 1440×900 · 移动端 390×844",
        font=font(FONT_REG, 17),
        fill=MUTED,
    )
    draw.line((PAD, HEADER_H - 8, W - PAD, HEADER_H - 8), fill=FRAME, width=2)

    cap_font = font(FONT_BOLD, 16)
    for i, (fname, label) in enumerate(present):
        src = Image.open(SRC / fname).convert("RGB")
        sw, sh = src.size
        inner_w = CELL_W - BORDER * 2
        inner_h = THUMB_H - BORDER * 2

        if fname.startswith("mobile"):
            # 移动端是竖版，contain 到底部居中，两侧留白
            scale = min(inner_w / sw, inner_h / sh)
            nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
            thumb = src.resize((nw, nh), Image.LANCZOS)
            tile = Image.new("RGB", (inner_w, inner_h), (255, 255, 255))
            tile.paste(thumb, ((inner_w - nw) // 2, (inner_h - nh) // 2))
        else:
            tile = src.resize((inner_w, inner_h), Image.LANCZOS)

        cell = Image.new("RGB", (CELL_W, THUMB_H + CAP_H), FRAME)
        cell.paste(tile, (BORDER, BORDER))
        cd = ImageDraw.Draw(cell)
        cd.rectangle([0, THUMB_H, CELL_W, THUMB_H + CAP_H], fill=CAP_BG)
        cd.text((14, THUMB_H + 11), label, font=cap_font, fill=(51, 65, 85))

        col, row = i % COLS, i // COLS
        x = PAD + col * (CELL_W + PAD)
        y = HEADER_H + PAD + row * (THUMB_H + CAP_H + PAD)
        canvas.paste(cell, (x, y))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, optimize=True)
    size_kb = os.path.getsize(OUT) // 1024
    print(f"总览图: {OUT}  {W}×{H}  {len(present)} 张  {size_kb} KB")


if __name__ == "__main__":
    main()
