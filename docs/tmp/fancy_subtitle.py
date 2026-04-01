#!/usr/bin/env python3
"""
动态字幕生成器 v2 - ASS 高级特效版
从 Whisper JSON 生成带逐字高亮、关键词变色放大、横竖排交替的 ASS 字幕。
"""

import json
import re
import sys
from pathlib import Path
from opencc import OpenCC

T2S = OpenCC("t2s")

# ── 屏幕配置 ──────────────────────────────────────────
PLAY_RES_X = 480
PLAY_RES_Y = 854

# ── 断句参数 ──────────────────────────────────────────
SENTENCE_ENDS = set("。！？!?")
CLAUSE_BREAKS = set("，,；;：:、")
MAX_SENTENCE_CHARS = 22
MAX_SENTENCE_DURATION = 5.0
SHORT_THRESHOLD = 4
MAX_LINE_CHARS = 13  # 480px 竖屏，字号36，单行最多13字

# ── 颜色（ASS BGR: &HAABBGGRR）──────────────────────
COLOR_WHITE = "&H00FFFFFF"
COLOR_YELLOW = "&H0000FFFF"     # 黄色
COLOR_CYAN = "&H00FFFF00"       # 青色
COLOR_RED = "&H004040FF"        # 红色
COLOR_GREEN = "&H0000CC00"      # 绿色
COLOR_ORANGE = "&H0055AAFF"     # 橙色
HIGHLIGHT_COLORS = [COLOR_YELLOW, COLOR_CYAN, COLOR_RED, COLOR_GREEN, COLOR_ORANGE]

# ── 关键词 ────────────────────────────────────────────
KEYWORD_PATTERNS = [
    r"孙悟空|唐僧|猪八戒|沙僧|如来|观音|菩提祖师|玉帝|太上老君",
    r"花果山|五行山|流沙河|天庭|龙宫|西天",
    r"金箍棒|紧箍咒|筋斗云|七十二变|定海神针|斗战圣佛",
    r"自由|成佛|修行|力量|存在主义|心力|清醒|本能|幻觉",
    r"真正|最狠|从来|偏要|哪怕|居然|竟然|其实|根本",
    r"妖怪|师父|徒弟|取经|西游记",
]
KEYWORD_RE = re.compile("|".join(KEYWORD_PATTERNS))

# ── 竖排配置 ──────────────────────────────────────────
VERTICAL_INTERVAL = 5       # 每 N 句触发一次竖排
VERTICAL_MAX_CHARS = 10     # 竖排最大字数（去标点后）

# ── 错别字修正 ────────────────────────────────────────
TYPO_FIXES = {
    "磨顿": "磨钝", "学礼术": "学法术", "七十二遍": "七十二变",
    "不准踢石门": "不准提师门", "金菇棒": "金箍棒", "锦箍咒": "紧箍咒",
    "念咒腾": "念咒疼", "令这金箍棒": "拎着金箍棒", "宋悟空": "孙悟空",
    "辟善": "劈山", "煤俏": "没鞘", "伤气": "伤己", "韧性": "任性",
    "温柔天下去的": "温柔天下去得", "袁文": "原文", "背懒": "耍懒",
    "青头云": "筋斗云", "洗油剂": "西游记", "爽闻": "爽文",
    "金斗云": "筋斗云", "考山": "靠山", "不了曲青路": "不聊取经路",
    "曲青路": "取经路", "被押": "被压",
}


# ── 数据加载 ──────────────────────────────────────────

def load_whisper_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            text = T2S.convert(w["word"].strip())
            if text:
                words.append({"word": text, "start": w["start"], "end": w["end"]})
    return words


def fix_typos(words: list[dict]) -> list[dict]:
    """在完整文本上修正错别字，然后重新映射回 words"""
    full_text = "".join(w["word"] for w in words)
    fixed_text = full_text
    for wrong, right in TYPO_FIXES.items():
        fixed_text = fixed_text.replace(wrong, right)

    if fixed_text == full_text:
        return words

    # 重新分配字符到 words（保持时间不变，按比例分配字符）
    new_words = []
    char_idx = 0
    for w in words:
        old_len = len(w["word"])
        # 按比例计算新词应该占多少字符
        ratio = old_len / max(1, len(full_text))
        new_len = max(1, round(ratio * len(fixed_text)))
        # 确保不超出
        new_len = min(new_len, len(fixed_text) - char_idx)
        if new_len <= 0:
            continue
        new_word = fixed_text[char_idx:char_idx + new_len]
        new_words.append({"word": new_word, "start": w["start"], "end": w["end"]})
        char_idx += new_len

    # 剩余字符追加到最后一个词
    if char_idx < len(fixed_text) and new_words:
        new_words[-1]["word"] += fixed_text[char_idx:]

    return new_words


# ── 断句 ──────────────────────────────────────────────

def words_to_sentences(words):
    sentences = []
    buf_words, buf_text, buf_start = [], "", None

    for w in words:
        if not w["word"]:
            continue
        if buf_start is None:
            buf_start = w["start"]
        buf_text += w["word"]
        buf_words.append(w)

        if buf_text and buf_text[-1] in SENTENCE_ENDS:
            _flush(sentences, buf_text, buf_start, w["end"], buf_words)
            buf_text, buf_start, buf_words = "", None, []

    if buf_text.strip():
        _flush(sentences, buf_text, buf_start, words[-1]["end"], buf_words)
    return sentences


def _flush(sentences, text, start, end, wbuf):
    text = text.strip()
    dur = end - start
    if dur <= MAX_SENTENCE_DURATION and len(text) <= MAX_SENTENCE_CHARS:
        sentences.append({"text": text, "start": start, "end": end, "words": list(wbuf)})
        return

    # 超长句拆分
    char_pos = []
    for wi, w in enumerate(wbuf):
        for c in w["word"]:
            char_pos.append((c, wi))

    breaks = [i for i, (c, _) in enumerate(char_pos) if c in CLAUSE_BREAKS and 2 <= i < len(char_pos) - 2]

    if not breaks:
        mid = len(wbuf) // 2
        mid_time = (start + end) / 2
        sentences.append({"text": "".join(w["word"] for w in wbuf[:mid]).strip(),
                          "start": start, "end": mid_time, "words": wbuf[:mid]})
        sentences.append({"text": "".join(w["word"] for w in wbuf[mid:]).strip(),
                          "start": mid_time, "end": end, "words": wbuf[mid:]})
        return

    segs = []
    last_cut, last_start = 0, start
    for bi in breaks:
        seg_text = "".join(c for c, _ in char_pos[last_cut:bi + 1])
        _, word_idx = char_pos[bi]
        seg_end = wbuf[word_idx]["end"]
        if len(seg_text) >= MAX_SENTENCE_CHARS or (seg_end - last_start) >= MAX_SENTENCE_DURATION:
            prev = [b for b in breaks if last_cut <= b < bi]
            if prev:
                cut_at = prev[-1]
                ct = "".join(c for c, _ in char_pos[last_cut:cut_at + 1])
                _, cwi = char_pos[cut_at]
                ce = wbuf[cwi]["end"]
                w_si = char_pos[last_cut][1]
                segs.append({"text": ct.strip(), "start": last_start, "end": ce,
                             "words": wbuf[w_si:cwi + 1]})
                last_cut = cut_at + 1
                last_start = ce
            else:
                w_si = char_pos[last_cut][1]
                segs.append({"text": seg_text.strip(), "start": last_start, "end": seg_end,
                             "words": wbuf[w_si:word_idx + 1]})
                last_cut = bi + 1
                last_start = seg_end

    remaining = "".join(c for c, _ in char_pos[last_cut:])
    if remaining.strip():
        w_si = char_pos[last_cut][1] if last_cut < len(char_pos) else len(wbuf)
        segs.append({"text": remaining.strip(), "start": last_start, "end": end,
                     "words": wbuf[w_si:]})
    sentences.extend(segs)


def merge_short(sentences):
    merged = []
    i = 0
    while i < len(sentences):
        cur = sentences[i]
        if len(cur["text"]) < SHORT_THRESHOLD and i + 1 < len(sentences):
            nxt = sentences[i + 1]
            merged.append({"text": cur["text"] + nxt["text"], "start": cur["start"],
                           "end": nxt["end"], "words": cur["words"] + nxt["words"]})
            i += 2
        else:
            merged.append(cur)
            i += 1
    return merged


# ── 关键词检测 ────────────────────────────────────────

def find_keyword_positions(text):
    """返回文本中关键词字符的位置集合"""
    positions = set()
    for m in KEYWORD_RE.finditer(text):
        for pos in range(m.start(), m.end()):
            positions.add(pos)
    return positions


# ── ASS 时间格式 ──────────────────────────────────────

def fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ── 横排字幕（带逐字高亮 + 关键词 + 换行）────────────

def build_horizontal(sentence, color_idx):
    """生成横排卡拉OK字幕，自动在逗号处换行"""
    words = sentence["words"]
    text = sentence["text"]
    highlight_color = HIGHLIGHT_COLORS[color_idx % len(HIGHLIGHT_COLORS)]
    kw_pos = find_keyword_positions(text)

    parts = []
    char_idx = 0          # 在 text 中的位置
    line_char_count = 0   # 当前行已显示字符数

    in_keyword = False  # 跟踪当前是否在关键词中

    for w in words:
        word_text = w["word"]
        duration_cs = max(1, int((w["end"] - w["start"]) * 100))

        for ci, char in enumerate(word_text):
            char_dur = max(1, duration_cs // max(1, len(word_text)))
            is_kw = char_idx in kw_pos

            # 关键词→普通：插入重置
            if in_keyword and not is_kw:
                parts.append(f"{{\\r\\K{char_dur}}}{char}")
                in_keyword = False
            elif is_kw:
                parts.append(f"{{\\K{char_dur}\\1c{highlight_color}\\fs42\\b1}}{char}")
                in_keyword = True
            else:
                parts.append(f"{{\\K{char_dur}}}{char}")

            line_char_count += 1
            char_idx += 1

            # 在逗号/顿号后换行（如果当前行已超过一半宽度）
            if char in CLAUSE_BREAKS and line_char_count >= 6:
                parts.append("{\\r}\\N")
                line_char_count = 0
                in_keyword = False
                continue

            # 强制换行：超过 MAX_LINE_CHARS 且不在词中间
            if line_char_count >= MAX_LINE_CHARS and ci == len(word_text) - 1:
                parts.append("{\\r}\\N")
                line_char_count = 0
                in_keyword = False

    return "".join(parts)


# ── 竖排字幕 ──────────────────────────────────────────

def build_vertical(sentence, color_idx):
    """生成竖排字幕：每个字一行，用 \\N 换行模拟竖排"""
    text = sentence["text"]
    highlight_color = HIGHLIGHT_COLORS[color_idx % len(HIGHLIGHT_COLORS)]
    kw_pos = find_keyword_positions(text)

    words = sentence["words"]
    lines = []
    char_idx = 0
    in_keyword = False

    for w in words:
        word_text = w["word"]
        dur_cs = max(1, int((w["end"] - w["start"]) * 100))
        char_dur = max(1, dur_cs // max(1, len(word_text)))

        for char in word_text:
            if char in SENTENCE_ENDS or char in CLAUSE_BREAKS or char in "、":
                if lines:
                    lines[-1] += char
                char_idx += 1
                continue

            is_kw = char_idx in kw_pos
            if in_keyword and not is_kw:
                lines.append(f"{{\\r\\K{char_dur}}}{char}")
                in_keyword = False
            elif is_kw:
                lines.append(f"{{\\K{char_dur}\\1c{highlight_color}\\fs44\\b1}}{char}")
                in_keyword = True
            else:
                lines.append(f"{{\\K{char_dur}}}{char}")
            char_idx += 1

    return "\\N".join(lines)


def compute_vertical_flags(sentences):
    """预先计算哪些句子用竖排。
    策略：纯文字≤10字的短句可以竖排，但不连续，且间隔≥3句。
    """
    flags = [False] * len(sentences)
    last_vert_idx = -999

    for i, s in enumerate(sentences):
        pure = re.sub(r"[。！？!?，,；;：:、\s]", "", s["text"])
        dur = s["end"] - s["start"]
        # 条件：短句、有足够时长、距上次竖排≥3句
        if (len(pure) <= VERTICAL_MAX_CHARS
                and dur >= 1.2
                and i - last_vert_idx >= 3
                and len(pure) >= 3):  # 太短（1-2字）不适合竖排
            flags[i] = True
            last_vert_idx = i

    return flags


# ── 生成 ASS ──────────────────────────────────────────

def generate_ass(sentences, vert_flags):
    header = f"""[Script Info]
Title: Fancy Subtitle
ScriptType: v4.00+
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hz,Arial Unicode MS,36,{COLOR_WHITE},{COLOR_YELLOW},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,0,8,20,20,220,1
Style: Vt,Arial Unicode MS,40,{COLOR_WHITE},{COLOR_YELLOW},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for i, s in enumerate(sentences):
        start = fmt_time(s["start"])
        end = fmt_time(s["end"])

        if vert_flags[i]:
            text = build_vertical(s, i)
            x = PLAY_RES_X // 2 + 60
            y = PLAY_RES_Y // 2 - 40
            text = f"{{\\pos({x},{y})}}" + text
            events.append(f"Dialogue: 0,{start},{end},Vt,,0,0,0,,{text}")
        else:
            text = build_horizontal(s, i)
            events.append(f"Dialogue: 0,{start},{end},Hz,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


# ── 分析 ──────────────────────────────────────────────

def analyze(sentences, vert_flags):
    total = len(sentences)
    vert = sum(vert_flags)
    kw = sum(1 for s in sentences if find_keyword_positions(s["text"]))

    print(f"\n--- 效果分析 ({PLAY_RES_X}x{PLAY_RES_Y} 竖屏) ---")
    print(f"  总条数: {total}")
    print(f"  横排: {total - vert}  竖排: {vert}")
    print(f"  含关键词高亮: {kw}/{total}")

    # 检查换行后每行是否超屏
    over = 0
    for i, s in enumerate(sentences):
        if vert_flags[i]:
            continue
        # 模拟换行
        lines = [""]
        for char in s["text"]:
            if char in CLAUSE_BREAKS and len(lines[-1]) >= 6:
                lines[-1] += char
                lines.append("")
                continue
            lines[-1] += char
            if len(lines[-1]) >= MAX_LINE_CHARS:
                lines.append("")
        for ln in lines:
            if len(ln) > MAX_LINE_CHARS + 3:  # 容忍标点溢出
                over += 1
                print(f"  ⚠ #{i+1} 行超屏({len(ln)}字): {ln}")
                break

    if over == 0:
        print("  ✓ 无超屏问题")

    # 预览竖排句子
    if vert > 0:
        print(f"\n  竖排句子:")
        for i, s in enumerate(sentences):
            if vert_flags[i]:
                pure = re.sub(r"[。！？!?，,；;：:、]", "", s["text"])
                print(f"    #{i+1} ({len(pure)}字): {s['text']}")


# ── 主函数 ────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python fancy_subtitle.py <whisper.json> [output.ass]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(json_path).with_suffix(".fancy.ass"))

    # 1. 加载
    words = load_whisper_json(json_path)
    print(f"加载 {len(words)} 个词")

    # 2. 错别字修正（在词级别，修正后重建 words）
    words = fix_typos(words)
    print(f"错别字修正完成")

    # 3. 断句
    sentences = words_to_sentences(words)
    print(f"合并为 {len(sentences)} 个句子")

    # 4. 短句合并
    sentences = merge_short(sentences)
    print(f"短句合并后 {len(sentences)} 个句段")

    # 5. 计算竖排标记
    vert_flags = compute_vertical_flags(sentences)

    # 6. 生成 ASS
    ass_content = generate_ass(sentences, vert_flags)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    print(f"ASS 已生成: {output_path}")

    # 7. 分析
    analyze(sentences, vert_flags)

    # 8. 预览前 10 条
    print(f"\n--- 预览 ---")
    for i, s in enumerate(sentences[:10]):
        v = "竖" if vert_flags[i] else "横"
        kw = "★" if find_keyword_positions(s["text"]) else " "
        print(f"  {i+1}. [{fmt_time(s['start'])}] {v}{kw} | {s['text']}")


if __name__ == "__main__":
    main()
