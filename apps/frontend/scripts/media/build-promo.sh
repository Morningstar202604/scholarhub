#!/usr/bin/env bash
# 把录屏 + 片头片尾合成宣传片（1920×1080 / H.264 / AAC-ready MP4）。
#
# 输入：
#   /tmp/promo/intro.png          — 片头卡片（fade + 缩放）
#   raw/*.webm                    — Playwright 录制的使用流程
#   /tmp/promo/outro.png          — 片尾卡片（仓库地址 + 指标）
# 输出：
#   /workspace/scholarhub-media/ScholarHUB-promo.mp4      宣传片（含片头尾）
#   /workspace/scholarhub-media/ScholarHUB-walkthrough.mp4 纯使用演示（含字幕）
set -euo pipefail

MEDIA=/workspace/scholarhub-media
RAW=$(ls -t "$MEDIA"/raw/*.webm | head -1)
FONT=/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc
TMP=$(mktemp -d)
echo "raw: $RAW"

# 中文字幕样式：底部居中、半透明底、白字
SUBSTYLE="FontName=Noto Serif CJK SC,FontSize=30,PrimaryColour=&H00FFFFFF,OutlineColour=&H00202020,BorderStyle=3,Outline=1,Shadow=0,MarginV=48,Alignment=2,Bold=1"

# ---------------------------------------------------------------
# 1) 片头：4s，黑底淡入 + 轻微放大 → 标题定住
# ---------------------------------------------------------------
ffmpeg -v error -y -loop 1 -i /tmp/promo/intro.png -t 4.2 \
  -vf "scale=2112:1188,zoompan=z='min(zoom+0.0004,1.10)':d=105:s=1920x1080:fps=25,format=yuv420p" \
  -c:v libopenh264 -b:v 6M -pix_fmt yuv420p "$TMP/intro.mp4"

# ---------------------------------------------------------------
# 2) 片尾：5s，淡入 + 缓慢放大
# ---------------------------------------------------------------
ffmpeg -v error -y -loop 1 -i /tmp/promo/outro.png -t 5.2 \
  -vf "scale=2112:1188,zoompan=z='min(zoom+0.0003,1.08)':d=130:s=1920x1080:fps=25,format=yuv420p" \
  -c:v libopenh264 -b:v 6M -pix_fmt yuv420p "$TMP/outro.mp4"

# ---------------------------------------------------------------
# 3) 使用演示：加底部中文字幕 + 淡入淡出
# ---------------------------------------------------------------
cat > "$TMP/subs.ass" <<ASS
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CN,Noto Serif CJK SC,30,&H00FFFFFF,&H00FFFFFF,&H00202020,&H99000000,1,0,0,0,100,100,0,0,3,1,0,2,80,80,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.40,0:00:04.20,CN,,0,0,0,,资源目录 · 支持按学科、年份、类型筛选
Dialogue: 0,0:00:04.60,0:00:09.00,CN,,0,0,0,,全文检索：标题 / 作者 / 摘要
Dialogue: 0,0:00:09.60,0:00:14.00,CN,,0,0,0,,资源详情 · DOI · 卷期页码 · 参考文献
Dialogue: 0,0:00:14.40,0:00:17.60,CN,,0,0,0,,邮箱验证 + 强密码登录
Dialogue: 0,0:00:18.60,0:00:23.60,CN,,0,0,0,,编辑工作台 · 一键分配审稿人
Dialogue: 0,0:00:24.20,0:00:29.00,CN,,0,0,0,,审稿工作台 · 接受邀请 / 提交评审意见
Dialogue: 0,0:00:29.60,0:00:34.60,CN,,0,0,0,,个性化推荐 · 基于阅读历史的内容画像
Dialogue: 0,0:00:34.80,0:00:38.60,CN,,0,0,0,,阅读列表 · 私人收藏与阅读清单
Dialogue: 0,0:00:39.00,0:00:43.00,CN,,0,0,0,,通知中心 · 审稿与投稿状态实时提醒
Dialogue: 0,0:00:43.60,0:00:50.00,CN,,0,0,0,,在线阅读器 · 进度自动同步
ASS

ffmpeg -v error -y -i "$RAW" \
  -vf "subtitles='$TMP/subs.ass':fontsdir=/usr/share/fonts/opentype/noto,fade=t=in:st=0:d=0.6,fade=t=out:st=49.6:d=0.8,format=yuv420p" \
  -c:v libopenh264 -b:v 6M -pix_fmt yuv420p -r 25 "$TMP/walk.mp4"

# ---------------------------------------------------------------
# 4) 拼接三段 → 宣传片
# ---------------------------------------------------------------
: > "$TMP/list.txt"
for f in intro walk outro; do echo "file '$TMP/$f.mp4'" >> "$TMP/list.txt"; done
ffmpeg -v error -y -f concat -safe 0 -i "$TMP/list.txt" -c copy "$MEDIA/ScholarHUB-promo.mp4"

# 纯演示版（无片头尾，方便贴 README）
cp "$TMP/walk.mp4" "$MEDIA/ScholarHUB-walkthrough.mp4"

echo
for f in "$MEDIA/ScholarHUB-promo.mp4" "$MEDIA/ScholarHUB-walkthrough.mp4"; do
  echo "== $(basename "$f")"
  ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,width,height,r_frame_rate \
    -show_entries format=duration,size -of default=nw=1 "$f"
done
rm -rf "$TMP"
