# 视频字幕重构指南

基于 mlx_whisper 语音识别 + 自定义断句脚本 + FFmpeg 硬烧字幕，重新为视频生成高质量中文字幕。

## 背景

原视频的字幕存在断句不自然、字幕与语音不同步等问题。核心原因是原字幕按**固定字数截断**（如每行 12 字），而非按**句子语义边界**断句，导致完整句子被从中间切开。

## 整体流程

```
原始视频
   ↓
[1] mlx_whisper 语音识别 → JSON（词级时间戳）
   ↓
[2] sentence_subtitle.py 断句脚本 → ASS 字幕文件
   ↓
[3] 人工校对错别字（Whisper 同音字误识别）
   ↓
[4] FFmpeg 硬烧字幕 → 新视频 MP4
```

## 环境准备

### 1. 安装 mlx_whisper（Apple Silicon 优化的 Whisper）

```bash
pip install mlx-whisper
```

### 2. 安装 opencc（繁转简）

```bash
pip install opencc-python-reimplemented
```

### 3. 安装带 libass 的 FFmpeg

brew 默认的 ffmpeg 不含 libass（ASS 字幕渲染库），需要使用第三方 tap：

```bash
# 添加 tap
brew tap homebrew-ffmpeg/ffmpeg

# 如果已装过官方 ffmpeg，先卸载
brew uninstall ffmpeg

# 安装带 libass 的版本（需要代理的话加 ALL_PROXY）
ALL_PROXY=http://127.0.0.1:7890 brew install homebrew-ffmpeg/ffmpeg/ffmpeg
```

验证 libass 可用：

```bash
ffmpeg -filters 2>&1 | grep "ass"
# 应看到: .. ass  V->V  Render ASS subtitles onto input video using the libass library.
```

### 4. 安装 HuggingFace 镜像（国内环境）

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## 操作步骤

### 第一步：语音识别生成词级时间戳

```bash
export HF_ENDPOINT=https://hf-mirror.com

mlx_whisper "视频文件.mp4" \
  --model "mlx-community/whisper-medium-mlx" \
  --language zh \
  --word-timestamps True \
  --initial-prompt "以下是普通话的转录文本，使用简体中文。" \
  --condition-on-previous-text False \
  --hallucination-silence-threshold 2 \
  --compression-ratio-threshold 1.8 \
  --no-speech-threshold 0.4 \
  --output-format json \
  --output-dir ./output \
  --verbose False
```

**关键参数说明：**

| 参数 | 作用 |
|------|------|
| `--word-timestamps True` | 输出每个词的精确起止时间，这是后续断句的基础 |
| `--initial-prompt` | 引导模型输出简体中文 |
| `--condition-on-previous-text False` | 防止错误累积，每段独立识别 |
| `--hallucination-silence-threshold 2` | 静音超过 2 秒时避免幻觉输出 |

输出文件为 JSON，结构如下：

```json
{
  "segments": [
    {
      "words": [
        {"word": "各位", "start": 0.0, "end": 0.4},
        {"word": "朋友", "start": 0.4, "end": 0.8}
      ]
    }
  ]
}
```

### 第二步：运行断句脚本生成 ASS 字幕

```bash
python3 sentence_subtitle.py 视频文件.json 视频文件.ass
```

**断句脚本的核心逻辑：**

1. **繁转简** — Whisper medium 模型会混用简繁体，加载时统一转简体
2. **按句终标点合并** — 以 `。！？` 为句子边界，将词合并为完整句子
3. **超长句拆分** — 单条字幕超过 22 字或 5 秒时，在逗号/顿号处拆分为多条
4. **短句合并** — 不足 4 字的句段向后合并，避免字幕闪现
5. **长行分行** — 单行超过 15 字时在逗号处插入换行（`\N`），保证竖屏不超屏

**与传统方案的对比：**

| 维度 | 传统方案（按字数截断） | 本方案（句界优先） |
|------|----------------------|-------------------|
| 分段依据 | 固定字数（12字） | 句终标点（。！？） |
| 完整句子 | 经常从中间截断 | 保证完整 |
| 短句处理 | 无 | 自动合并避免闪现 |
| 长句处理 | 强制截断 | 在逗号处智能分行 |

### 第三步：校对错别字

Whisper 识别中文时最常见的问题是**同音字错误**，特别是专有名词。需要人工校对。

常见错误模式（以西游记为例）：

| Whisper 识别 | 正确 | 错误类型 |
|-------------|------|---------|
| 金菇棒 | 金箍棒 | 同音 |
| 锦箍咒 | 紧箍咒 | 同音 |
| 七十二遍 | 七十二变 | 同音 |
| 筋头云 | 筋斗云 | 近音 |
| 宋悟空 | 孙悟空 | 同音 |
| 袁文 | 原文 | 同音 |

**批量修正方法：** 在 ASS 文件中用 Python 脚本批量替换：

```python
fixes = {
    "金菇棒": "金箍棒",
    "锦箍咒": "紧箍咒",
    "七十二遍": "七十二变",
    # ... 更多修正
}

with open("视频文件.ass", "r", encoding="utf-8") as f:
    content = f.read()
for wrong, right in fixes.items():
    content = content.replace(wrong, right)
with open("视频文件.ass", "w", encoding="utf-8") as f:
    f.write(content)
```

### 第四步：调整字幕样式

ASS 文件头部的 Style 行控制字幕外观。关键参数：

```
Style: Top,Arial Unicode MS,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,0,8,10,10,220,1
```

| 字段位置 | 含义 | 推荐值（480×854竖屏） |
|---------|------|---------------------|
| Fontname | 字体 | `Arial Unicode MS`（跨平台兼容） |
| Fontsize | 字号 | `36`（竖屏清晰可读） |
| PrimaryColour | 字色 | `&H00FFFFFF`（白色） |
| OutlineColour | 描边色 | `&H00000000`（黑色） |
| Bold | 加粗 | `-1`（开启） |
| Outline | 描边宽度 | `2.5` |
| Alignment | 对齐方式 | `8`（顶部居中） |
| MarginV | 垂直边距 | `220`（约 30% 位置，方便与底部原字幕对比） |

### 第五步：FFmpeg 硬烧字幕生成 MP4

```bash
# 先复制 ASS 到英文路径（避免 FFmpeg 中文路径问题）
cp 视频文件.ass /tmp/vv_subtitle.ass

ffmpeg -y \
  -i 原始视频.mp4 \
  -vf "ass=/tmp/vv_subtitle.ass:fontsdir=/System/Library/Fonts" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a copy \
  -map 0:v:0 -map 0:a:0 \
  输出视频.mp4
```

**关键参数说明：**

| 参数 | 作用 |
|------|------|
| `-vf "ass=..."` | 使用 libass 渲染 ASS 字幕到视频画面 |
| `fontsdir=/System/Library/Fonts` | 指定字体目录，否则 ASS 无法找到字体 |
| `-c:a copy` | 音频直接拷贝不重编码（避免音频丢失） |
| `-map 0:v:0 -map 0:a:0` | 明确映射视频和音频流 |
| `-crf 23` | 视频质量（越小越清晰，23 为默认平衡值） |

**注意事项：**
- 中文路径会导致 FFmpeg 解析 ASS 文件失败，必须先复制到英文临时路径
- macOS 上 fontsdir 指向 `/System/Library/Fonts`，Linux 指向 `/usr/share/fonts`

---

## 进阶：动态花字字幕

在基础字幕之上，可以生成短视频风格的动态字幕效果，包括逐字高亮、关键词变色放大、横竖排交替。

### 效果说明

| 效果 | 实现方式 | 视觉表现 |
|------|---------|---------|
| 逐字高亮 | ASS `\K` 卡拉OK标签 | 白色文字跟随语音逐字变为黄色 |
| 关键词放大变色 | `\1c` 变色 + `\fs` 变字号 + `\r` 重置 | 专有名词/情绪词放大+变色（黄/青/红/绿/橙轮换） |
| 横竖排交替 | 短句用 `\N` 逐字换行模拟竖排 | 每隔几句出现一次竖排，制造视觉节奏 |

### 技术原理

**逐字高亮（卡拉OK效果）：**

ASS 的 `\K` 标签控制每个字的高亮时长（单位：厘秒）。Whisper 的词级时间戳直接映射为 `\K` 值：

```
{\K14}各{\K14}位{\K17}朋{\K17}友
```

表示"各"显示 0.14 秒后高亮，"位"再过 0.14 秒高亮，以此类推。

**关键词变色：**

用 `\1c` 改变字色，`\fs` 改变字号，关键词结束后用 `\r` 重置回默认样式：

```
{\K20\1c&H0000FFFF\fs42\b1}孙{\K16\1c&H0000FFFF\fs42\b1}悟{\K5\1c&H0000FFFF\fs42\b1}空{\r\K14}一{\K14}个
```

> **重要：** 关键词结束后必须用 `\r` 重置样式，否则后续所有文字都会继承关键词的颜色和大小。

**关键词自动检测：** 用正则匹配句子全文，返回关键词字符的位置集合：

```python
KEYWORD_PATTERNS = [
    r"孙悟空|唐僧|如来|观音|玉帝|太上老君",
    r"金箍棒|紧箍咒|筋斗云|七十二变|斗战圣佛",
    r"自由|成佛|力量|存在主义|心力|清醒",
    r"真正|最狠|从来|偏要|哪怕|根本",
    r"妖怪|师父|徒弟|取经|西游记",
]
```

**竖排效果：** 对短句（去标点后≤10字），用 `\N` 让每个字独占一行模拟竖排，标点跟随前字不独占行：

```
{\K12}什\N{\K12}么\N{\K13}叫\N{\K28\1c&H0000FFFF\fs44\b1}存\N...
```

竖排触发规则：
- 去标点后纯文字 ≤ 10 字
- 与上一个竖排间隔 ≥ 3 句（避免连续竖排）
- 字幕时长 ≥ 1.2 秒

**横排自动换行：** 在逗号/顿号后且当前行已超 6 字时插入 `\N` 换行，超 13 字在词边界强制换行。

### 使用方法

```bash
# 生成花字 ASS（复用第一步的 Whisper JSON）
python3 fancy_subtitle.py "视频文件.json" "视频文件.fancy.ass"

# 硬烧到视频
cp "视频文件.fancy.ass" /tmp/vv_fancy.ass
ffmpeg -y -i "原始视频.mp4" \
  -vf "ass=/tmp/vv_fancy.ass:fontsdir=/System/Library/Fonts" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a copy -map 0:v:0 -map 0:a:0 \
  "花字视频.mp4"
```

### ASS 样式配置

花字版使用两种样式：

```
Style: Hz（横排）: 字号36, 顶部30%位置, Alignment=8
Style: Vt（竖排）: 字号40, 屏幕正中, Alignment=5
```

| 参数 | 横排 Hz | 竖排 Vt |
|------|---------|---------|
| 字号 | 36（关键词 42） | 40（关键词 44） |
| 位置 | 顶部 30%（MarginV=220） | 屏幕中央偏右 |
| 对齐 | 8（顶部居中） | 5（正中） |

### 花字踩坑记录

| 问题 | 原因 | 解决 |
|------|------|------|
| 关键词变色后不恢复 | `\1c` 改色后未重置 | 关键词结束后插入 `\r` 重置样式 |
| 横排文字超屏 | 卡拉OK逐字输出无换行 | 在逗号处和超 13 字时插入 `\N` |
| 竖排太少 | 按固定间隔触发，大部分句子超字数 | 改为按短句自动触发，间隔≥3句 |
| 错别字在卡拉OK文本中未修正 | 修正只改了句子文本，未改词级数据 | 在完整拼接文本上修正后重新分配回词 |

---

## 文件清单

```
docs/tmp/
├── 西游记_1_14_高清.mp4          # 原始视频
├── 西游记_1_14_高清.json         # Whisper 识别结果（词级时间戳）
├── 西游记_1_14_高清.ass          # 基础 ASS 字幕（静态白字，已校对）
├── 西游记_1_14_新字幕.mp4        # 基础字幕版视频
├── 西游记_1_14_新字幕.mkv        # 软字幕版本（MKV 容器）
├── 西游记_1_14_花字.ass          # 花字 ASS 字幕（逐字高亮+关键词+竖排）
├── 西游记_1_14_花字.mp4          # 花字版视频
├── sentence_subtitle.py          # 基础断句脚本
└── fancy_subtitle.py             # 花字动态字幕脚本
```

## 一键复现命令

### 基础字幕版

```bash
export HF_ENDPOINT=https://hf-mirror.com

# 1. 语音识别
mlx_whisper "输入视频.mp4" \
  --model "mlx-community/whisper-medium-mlx" \
  --language zh --word-timestamps True \
  --initial-prompt "以下是普通话的转录文本，使用简体中文。" \
  --condition-on-previous-text False \
  --hallucination-silence-threshold 2 \
  --output-format json --output-dir .

# 2. 生成基础字幕
python3 sentence_subtitle.py "输入视频.json" "输入视频.ass"

# 3. 校对错别字（手动编辑 ASS 文件或用 Python 批量替换）

# 4. 硬烧字幕
cp "输入视频.ass" /tmp/vv_subtitle.ass
ffmpeg -y -i "输入视频.mp4" \
  -vf "ass=/tmp/vv_subtitle.ass:fontsdir=/System/Library/Fonts" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a copy -map 0:v:0 -map 0:a:0 \
  "输出视频.mp4"
```

### 花字动态字幕版

```bash
# 在第1步语音识别完成后，用 fancy_subtitle.py 替代 sentence_subtitle.py：

# 2. 生成花字字幕（含逐字高亮+关键词变色+竖排）
python3 fancy_subtitle.py "输入视频.json" "输入视频.fancy.ass"

# 3. 校对错别字（fancy_subtitle.py 内置了错别字修正表，可在脚本中 TYPO_FIXES 字典添加）
#    关键词列表可在 KEYWORD_PATTERNS 中自定义

# 4. 硬烧花字字幕
cp "输入视频.fancy.ass" /tmp/vv_fancy.ass
ffmpeg -y -i "输入视频.mp4" \
  -vf "ass=/tmp/vv_fancy.ass:fontsdir=/System/Library/Fonts" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a copy -map 0:v:0 -map 0:a:0 \
  "花字视频.mp4"
```

## 踩坑记录

| 问题 | 原因 | 解决 |
|------|------|------|
| FFmpeg 无 ass 滤镜 | brew 默认 ffmpeg 不含 libass | 用 `homebrew-ffmpeg/ffmpeg` tap 安装 |
| 输出视频没声音 | 音频用 `-c:a aac` 重编码可能失败 | 改用 `-c:a copy` 直接拷贝 |
| ASS 中文路径报错 | FFmpeg 无法解析中文路径中的特殊字符 | 复制 ASS 到英文临时路径 |
| Whisper 输出繁体字 | medium 模型简繁混用 | 脚本中用 opencc 繁转简 |
| 字幕截断不完整 | 按固定字数截断 | 改为按句终标点断句 |
| 超长句占满屏幕 | 单条字幕字数/时长不限 | 超 22 字或 5 秒在逗号处拆分 |
| 短句闪现 | 2-3 字的碎片独立显示 | 短于 4 字自动向后合并 |
| brew install 锁文件 | 上次安装中断残留 | 删除 `*.incomplete` 文件后重试 |
