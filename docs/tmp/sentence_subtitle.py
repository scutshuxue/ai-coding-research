#!/usr/bin/env python3
"""
Whisper JSON → ASS 字幕生成器
从 mlx_whisper 输出的 JSON（含词级时间戳）生成断句精确的 ASS 字幕。

断句策略：
1. 按句终标点（。！？!?）切分完整句子
2. 长句（>15字）在逗号/分号处拆为两行
3. 短句（<4字）向后合并避免闪现
"""

import json
import sys
from pathlib import Path

from opencc import OpenCC

# 繁转简转换器
T2S = OpenCC("t2s")


# ── 配置 ──────────────────────────────────────────────
MAX_LINE_CHARS = 15      # 单行最大字符数
SHORT_THRESHOLD = 4      # 短句合并阈值
SENTENCE_ENDS = set("。！？!?")
CLAUSE_BREAKS = set("，,；;：:、")


def load_whisper_json(path: str) -> list[dict]:
    """加载 Whisper JSON，提取 segments 中的 words"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            words.append({
                "word": T2S.convert(w["word"].strip()),
                "start": w["start"],
                "end": w["end"],
            })
    return words


MAX_SENTENCE_DURATION = 5.0  # 单条字幕最大时长（秒）
MAX_SENTENCE_CHARS = 22      # 单条字幕最大字符数（两行以内）


def words_to_sentences(words: list[dict]) -> list[dict]:
    """将词级时间戳按句终标点合并为完整句子"""
    sentences = []
    buf_words = []   # 缓存词列表，用于超长句拆分
    buf_text = ""
    buf_start = None

    for w in words:
        if not w["word"]:
            continue
        if buf_start is None:
            buf_start = w["start"]
        buf_text += w["word"]
        buf_words.append(w)
        buf_end = w["end"]

        # 检查末尾是否是句终标点
        if buf_text and buf_text[-1] in SENTENCE_ENDS:
            _flush_sentence(sentences, buf_text, buf_start, buf_end, buf_words)
            buf_text = ""
            buf_start = None
            buf_words = []

    # 剩余文本（没有句终标点的尾部）
    if buf_text.strip():
        end = words[-1]["end"] if words else 0
        _flush_sentence(sentences, buf_text, buf_start, end, buf_words)

    return sentences


def _flush_sentence(sentences, text, start, end, words_buf):
    """将一个句子加入列表，如果太长则在逗号处拆分为多条。

    策略：构建每个逗号/顿号处的切分候选点，然后贪心地从头开始，
    每当累积字数接近 MAX_SENTENCE_CHARS 时在最近的候选点切断。
    """
    text = text.strip()
    duration = end - start

    if duration <= MAX_SENTENCE_DURATION and len(text) <= MAX_SENTENCE_CHARS:
        sentences.append({"text": text, "start": start, "end": end})
        return

    # 构建字符→词索引映射
    char_positions = []  # [(char, word_index)]
    for wi, w in enumerate(words_buf):
        for c in w["word"]:
            char_positions.append((c, wi))

    # 找所有逗号/顿号/分号断点
    split_chars = CLAUSE_BREAKS | set("、")
    break_indices = [
        i for i, (c, _) in enumerate(char_positions)
        if c in split_chars and 2 <= i < len(char_positions) - 2
    ]

    if not break_indices:
        # 没有断点，强制按时间均分
        mid_time = (start + end) / 2
        mid_word = len(words_buf) // 2
        t1 = "".join(w["word"] for w in words_buf[:mid_word])
        t2 = "".join(w["word"] for w in words_buf[mid_word:])
        sentences.append({"text": t1.strip(), "start": start, "end": mid_time})
        sentences.append({"text": t2.strip(), "start": mid_time, "end": end})
        return

    # 贪心切分：每次找到刚好不超过阈值的最远断点
    segments = []
    seg_start_idx = 0
    seg_start_time = start

    for bi in break_indices:
        candidate_text = "".join(c for c, _ in char_positions[seg_start_idx:bi + 1])
        _, word_idx = char_positions[bi]
        candidate_end = words_buf[word_idx]["end"]
        candidate_dur = candidate_end - seg_start_time

        if len(candidate_text) > MAX_SENTENCE_CHARS or candidate_dur > MAX_SENTENCE_DURATION:
            # 当前候选已超限，回退到上一个断点切分
            # 找 seg_start_idx 到 bi 之间最后一个断点
            prev_breaks = [b for b in break_indices if seg_start_idx <= b < bi]
            if prev_breaks:
                cut_at = prev_breaks[-1]
                cut_text = "".join(c for c, _ in char_positions[seg_start_idx:cut_at + 1])
                _, cut_word_idx = char_positions[cut_at]
                cut_end = words_buf[cut_word_idx]["end"]
                segments.append({"text": cut_text.strip(), "start": seg_start_time, "end": cut_end})
                seg_start_idx = cut_at + 1
                seg_start_time = cut_end
            else:
                # 没有更早的断点，直接在此处切
                segments.append({"text": candidate_text.strip(), "start": seg_start_time, "end": candidate_end})
                seg_start_idx = bi + 1
                seg_start_time = candidate_end

    # 剩余部分
    remaining = "".join(c for c, _ in char_positions[seg_start_idx:])
    if remaining.strip():
        # 如果剩余部分仍然超限，在最后一个断点处再切一次
        remaining_breaks = [
            i - seg_start_idx for i, (c, _) in enumerate(char_positions[seg_start_idx:])
            if c in split_chars and i - seg_start_idx >= 2
        ]
        if len(remaining) > MAX_SENTENCE_CHARS and remaining_breaks:
            mid = len(remaining) // 2
            best_rb = min(remaining_breaks, key=lambda p: abs(p - mid))
            abs_idx = seg_start_idx + best_rb
            _, w1 = char_positions[abs_idx]
            t1 = remaining[:best_rb + 1].strip()
            t2 = remaining[best_rb + 1:].strip()
            mid_time = words_buf[w1]["end"]
            if t1:
                segments.append({"text": t1, "start": seg_start_time, "end": mid_time})
            if t2:
                segments.append({"text": t2, "start": mid_time, "end": end})
        else:
            segments.append({"text": remaining.strip(), "start": seg_start_time, "end": end})

    sentences.extend(segments)


def merge_short(sentences: list[dict]) -> list[dict]:
    """短句（<4字）向后合并，避免字幕闪现"""
    if not sentences:
        return sentences

    merged = []
    i = 0
    while i < len(sentences):
        current = sentences[i]
        # 短句且后面还有句子，且合并后单行不超限
        if (len(current["text"]) < SHORT_THRESHOLD
                and i + 1 < len(sentences)):
            nxt = sentences[i + 1]
            combined_text = current["text"] + nxt["text"]
            merged.append({
                "text": combined_text,
                "start": current["start"],
                "end": nxt["end"],
            })
            i += 2
        else:
            merged.append(current)
            i += 1
    return merged


def split_long_lines(text: str, depth: int = 0) -> str:
    """长句在逗号处拆为两行（用 \\N 表示 ASS 换行）"""
    if len(text) <= MAX_LINE_CHARS or depth > 5:
        return text

    # 找所有从句断点位置（排除首尾位置，避免空拆分）
    break_positions = [
        i for i, c in enumerate(text)
        if c in CLAUSE_BREAKS and 2 <= i < len(text) - 2
    ]

    if not break_positions:
        # 没有标点断点，强制在中点拆分
        mid = len(text) // 2
        return text[:mid] + "\\N" + text[mid:]

    # 选最接近中点的断点（标点跟前半部分）
    mid = len(text) // 2
    best = min(break_positions, key=lambda p: abs(p - mid))
    line1 = text[:best + 1].strip()
    line2 = text[best + 1:].strip()

    # 递归检查每行是否还需要继续拆
    if len(line1) > MAX_LINE_CHARS:
        line1 = split_long_lines(line1, depth + 1)
    if len(line2) > MAX_LINE_CHARS:
        line2 = split_long_lines(line2, depth + 1)

    return line1 + "\\N" + line2


def format_ass_time(seconds: float) -> str:
    """格式化为 ASS 时间格式 H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass(sentences: list[dict], width: int = 480, height: int = 854) -> str:
    """生成 ASS 字幕内容，字幕置顶"""

    # ASS 头部
    header = f"""[Script Info]
Title: Generated Subtitle
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Top,Arial Unicode MS,26,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,8,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # 生成每条字幕事件
    events = []
    for s in sentences:
        start = format_ass_time(s["start"])
        end = format_ass_time(s["end"])
        text = split_long_lines(s["text"])
        events.append(f"Dialogue: 0,{start},{end},Top,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


def main():
    if len(sys.argv) < 2:
        print("用法: python sentence_subtitle.py <whisper_output.json> [output.ass]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(json_path).with_suffix(".ass")
    )

    # 1. 加载 Whisper JSON
    words = load_whisper_json(json_path)
    print(f"加载了 {len(words)} 个词")

    # 2. 按句终标点合并为句子
    sentences = words_to_sentences(words)
    print(f"合并为 {len(sentences)} 个句子")

    # 3. 短句合并
    sentences = merge_short(sentences)
    print(f"短句合并后 {len(sentences)} 个句段")

    # 4. 生成 ASS
    ass_content = generate_ass(sentences)

    # 5. 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    print(f"ASS 字幕已生成: {output_path}")

    # 6. 预览前10条
    print("\n--- 预览 ---")
    for i, s in enumerate(sentences[:10], 1):
        display = split_long_lines(s["text"]).replace("\\N", "\n    ")
        print(f"  {i}. [{format_ass_time(s['start'])} → {format_ass_time(s['end'])}]")
        print(f"    {display}")


if __name__ == "__main__":
    main()
