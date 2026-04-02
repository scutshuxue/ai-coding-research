# VV-VisionVoice

**从书名到短视频的自动化生成系统**

基于 LLM + TTS + FFmpeg 的智能内容创作平台，自动将书籍名称转化为系列短视频。本文档为详细记录项目关键信息的文档。

---

## 快速开始

### 安装依赖

```bash
# 克隆项目
git clone https://github.com/user/vv-visionvoice.git
cd vv-visionvoice

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 FFmpeg（必须，用于视频渲染）
# macOS:
brew install ffmpeg-full

# Ubuntu/Debian:
sudo apt install ffmpeg libass-dev

# Windows:
# 下载完整版: https://www.gyan.dev/ffmpeg/builds/
# 选择 "full" 或 "full_shared" 版本

# 验证 FFmpeg 安装
ffmpeg -version
ffmpeg -filters 2>&1 | grep -E "ass|subtitles"
# 应看到: ... ass   V->V       Render ASS subtitles
```

### 配置环境变量

```bash
# 复制配置文件
cp .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
```

**环境变量说明:**

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | 是 | LLM 提供商: `qwen` (推荐) 或 `openai` |
| `LLM_API_KEY` | 是 | LLM API 密钥 |
| `LLM_MODEL` | 否 | 模型名称，默认 `qwen-plus` |
| `STEP_API_KEY` | 是 | 阶跃星辰 TTS API 密钥 |
| `VOLCENGINE_API_KEY` | 否 | 火山引擎 AI 图片生成 API 密钥 |
| `DASHSCOPE_API_KEY` | 否 | 通义万相 AI 图片生成 API 密钥（备选） |

### 完整工作流

```bash
# 1. 爬取书评
python main.py crawler -b "三体"

# 2. 筛选评论（高质量内容蒸馏）
python main.py filter -b "三体"

# 3. 生成内容（大纲 → 章节 → 脚本 → 分集）
python main.py content -b "三体" --step all

# 4. 自动标签注入（为 TTS 添加情绪/风格标签）
python main.py tag -b "三体"

# 5. TTS 语音合成（将脚本转为音频）
# 全量生成
python main.py tts -b "三体"

# 或者只生成第1集（测试/调试用）
python main.py tts -b "三体" --episode 1 --dry-run  # 先预览
python main.py tts -b "三体" --episode 1             # 实际执行

# 6. Whisper 字幕生成（推荐！解决字幕错位）
python main.py whisper -b "三体" --time-offset 0.3

# 7. 视频渲染（音频 + 字幕 → 视频）
python main.py render -b "三体"
```

### 交互式模式

```bash
python main.py
```

---

## 项目架构

```
vv-visionvoice/
├── vv/                           # 主包
│   ├── core/                     # 核心模块
│   │   ├── config.py            # 配置管理
│   │   └── exceptions.py        # 异常定义
│   ├── utils/                    # 通用工具
│   │   └── logger.py            # 日志系统
│   ├── crawler/                  # 爬虫模块
│   │   ├── core/                # 爬虫核心引擎
│   │   │   ├── engine.py        # 爬虫引擎
│   │   │   ├── pipeline.py      # 处理管道
│   │   │   └── scheduler.py     # 调度器
│   │   ├── adapters/douban/     # 豆瓣适配器
│   │   │   ├── adapter.py       # 适配器主类
│   │   │   ├── parsers/         # 页面解析器
│   │   │   └── models.py        # 数据模型
│   │   ├── middlewares/         # 中间件
│   │   │   ├── rate_limiter.py  # 速率限制
│   │   │   ├── retry.py         # 重试机制
│   │   │   └── cookie.py        # Cookie 管理
│   │   └── main.py              # 爬虫入口
│   ├── content/                  # 内容生成模块
│   │   ├── llm_client.py        # LLM 客户端（OpenAI/Qwen）
│   │   ├── staged_generator.py  # 分阶段生成器
│   │   ├── staged_prompts.py    # Prompt 模板
│   │   ├── loader.py            # 数据加载
│   │   └── filter/              # 评论筛选
│   │       ├── filter.py        # 三层筛选系统
│   │       ├── scorers.py       # 语义评分器
│   │       └── config.py        # 筛选配置
│   ├── audio/                    # 音频生成模块
│   │   ├── step_tts.py          # 阶跃星辰 TTS
│   │   ├── tts_executor.py      # TTS 执行器（并发/缓存/重试）
│   │   ├── tts_alignment_engine.py # 时间轴对齐引擎（TTS 时间戳）
│   │   ├── whisper_aligner.py   # Whisper 音频驱动字幕生成（推荐）
│   │   └── tagger/              # 自动标签注入
│   │       ├── auto_tagger.py   # 情绪检测与标签注入
│   │       └── config.py        # 标签配置
│   ├── testing/                   # 自动测试模块
│   │   ├── test_config.py        # 测试配置
│   │   └── test_hooks.py         # 测试钩子实现
│   └── video/                    # 视频生成模块
│       ├── ass_generator.py     # ASS 字幕生成器
│       ├── video_renderer.py    # FFmpeg 视频渲染
│       └── template_video_generator.py # MoviePy 模板渲染
├── main.py                       # 主入口（CLI）
├── pyproject.toml                # 项目配置
├── requirements.txt              # 依赖
└── .env.example                  # 环境变量示例
```

### 数据流

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   爬虫模块   │ →  │   筛选模块   │ →  │  内容生成   │ →  │  标签注入   │
│  (豆瓣书评)  │    │ (三层筛选)   │    │ (分阶段LLM) │    │ (情绪检测)  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │
       ▼                  ▼                  ▼                  ▼
  [测试钩子]         [测试钩子]         [测试钩子]         [测试钩子]
                                                                │
                                                                ↓
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  视频渲染   │ ←  │  ASS 生成   │ ←  │ Whisper对齐  │ ←  │  TTS 合成   │
│  (FFmpeg)   │    │  (精确时间戳) │   │  (音频驱动)  │    │ (阶跃星辰)  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │
       ▼                  ▼                  ▼                  ▼
  [测试钩子]         [测试钩子]         [测试钩子]         [测试钩子]
```

> **推荐使用 Whisper 音频驱动字幕生成**，解决录音非线性导致的字幕错位问题。

---

## 核心技术

### 1. 爬虫模块 (Crawler)

**架构设计:**
- **引擎 (Engine)**: 异步爬虫核心，支持并发、速率限制、重试
- **适配器 (Adapter)**: 平台适配层，目前支持豆瓣
- **中间件 (Middleware)**: 请求拦截、Cookie 管理、User-Agent 轮换

**核心组件:**
- `Engine`: 爬虫引擎，管理请求调度和并发
- `Downloader`: HTTP 下载器，支持 requests/Selenium
- `Pipeline`: 数据处理管道
- `RateLimiter`: 令牌桶算法限速

**反爬虫对抗:**
- Selenium 隐身模式（隐藏 webdriver 特征）
- 自动从本机浏览器获取 Cookie（browser-cookie3）
- 随机访问节奏（2-5秒随机延迟）
- 真实浏览器请求头（Referer、User-Agent）
- 风控页面检测与处理

```python
from vv.crawler import DoubanAdapter, DoubanConfig, run_crawler

config = DoubanConfig(
    rate_limit=2.0,      # 请求间隔
    concurrency=3,       # 并发数
    max_retries=3,       # 最大重试
)

result = run_crawler(config)
```

**封面图片下载:**
- 自动从豆瓣书详情页提取高清封面
- 支持高清图片自动升级（/s/ → /l/）
- 请求头包含 Referer 避免 418 错误
- 下载失败自动回退原图

**输出数据:**
- `{书名}_douban_书评.json` - 长书评
- `{书名}_douban_短评_好评.json` - 好评短评
- `{书名}_douban_短评_差评.json` - 差评短评
- `{书名}_douban_原文摘录.json` - 原文摘录
- `images/cover.jpg` - 高清封面图片

### 2. 评论筛选 (Filter)

**三层筛选系统:**

```
第一层: 基础过滤
├── 去重（Levenshtein/Jaccard 相似度）
├── 长度过滤（最小/最大字数）
└── 无意义评论过滤

第二层: 语义评分
├── 观点强度 (0-5分)
├── 情绪强度 (0-5分)
├── 信息密度 (0-5分)
└── 争议性 (0-5分)

第三层: 结构化采样
├── 差评优先（3-5条，争议性排序）
├── 好评（2-3条，信息密度排序）
├── 中评（2条）
├── 原文摘录（3条，画面感排序）
└── 总长度控制（≤3000字符）
```

**关键算法:**

```python
# Levenshtein 相似度（用于去重）
def _levenshtein_similarity(text1: str, text2: str) -> float:
    # 动态规划实现
    # 返回 0.0-1.0，值越高越相似

# 多样性采样
def _select_diverse(comments, count, threshold=0.7):
    # 确保选中的评论不过于相似
    # 使用滑动窗口检测相似度
```

### 3. 内容生成 (Content Generation)

**分阶段生成流程:**

```
Step 1: 大纲生成 (outline)
    输入: 筛选后的评论 + 书籍信息
    输出: 6章节大纲 (outline.txt)

Step 2: 逐章生成 (chapters)
    输入: 大纲 + 章节主题
    输出: chapters/chapter_01.txt ~ chapter_06.txt

Step 3: 脚本拼接 (full)
    输入: 所有章节
    输出: full_script.txt

Step 4: 分集拆分 (episodes)
    输入: 完整脚本
    输出: episodes.json + episodes/ep_*.txt
```

**缓存机制:**
- 每个步骤独立缓存
- 已存在则自动跳过
- `--force` 强制重新生成

**LLM Provider 支持:**
- `qwen` - 阿里通义千问（推荐）
- `openai` - OpenAI API

```python
from vv.content import get_llm_client, run_content_pipeline

client = get_llm_client(provider="qwen", model="qwen-plus")
result = run_content_pipeline(
    book_name="三体",
    step="all",  # outline/chapters/full/episodes/all
    client=client,
)
```

### 4. 自动标签注入 (Tagger)

**情绪检测算法:**
- 基于关键词匹配 + 正则模式
- 滑动窗口平滑（避免频繁切换）
- 情绪持续时间限制（最多2句）

**支持的标签:**

| 类型 | 标签 |
|------|------|
| 情绪 | 高兴、非常高兴、悲伤、生气、非常生气、撒娇、恐惧、惊讶、兴奋、钦佩、困惑 |
| 风格 | 冷漠、尴尬、沮丧、骄傲、温柔、甜美、豪爽、严肃、傲慢、老年、吼叫、阴阳怪气、磕巴 |
| 语速 | 慢速、极慢、快速、极快 |

```python
from vv.audio.tagger import tag_episode, TaggerConfig

tagged = tag_episode(
    "这本书真是太精彩了！但是结局让我很失望？",
    voice_name="磁性男声",
)
# 输出:
# 【磁性男声】
# 【阴阳怪气】
# 这本书真是太精彩了！
# 【困惑】
# 但是结局让我很失望，作者为什么这样写呢？
```

### 5. TTS 执行器 (TTS Executor)

**核心特性:**
- 并发处理（可配置 workers）
- 请求缓存（避免重复合成）
- 速率限制（RPM 控制）
- 自动重试（失败重试3次）
- 长文本自动拆分（>1000字符）

```python
from vv.audio.tts_executor import run_tts_executor, ExecutorConfig

run_tts_executor(
    book_name="三体",
    config=ExecutorConfig(
        model="step-tts-2",
        default_voice="磁性男声",
        max_workers=3,
        rpm_limit=8,        # 每分钟8次请求
        enable_cache=True,
    ),
)
```

### 6. TTS 文本标准化 (TTS Normalizer)

TTS 文本标准化模块将书面文本转换为适合语音合成的格式，提升语音听感。

**处理流程 (4阶段):**

```
Stage 1: clean    → 清洗 (HTML/emoji/URL)
Stage 2: semantic → 语义 (俚语/缩写/列表)
Stage 3: replace  → 替换 (数字/符号/括号)
Stage 4: rhythm   → 节奏 (长句拆分)
```

**俚语映射系统 (SlangMapper):**

基于配置文件的俚语转换，支持热更新无需改代码：

```yaml
# vv/audio/config/slang_mapping.yaml
numeric_slang:
  "666":
    literal: "六六六"
    semantic: "太厉害了"
    mode: "literal"

text_slang:
  "yyds":
    literal: "yyds"
    mode: "literal"
```

**数字转换规则:**

| 输入 | 输出 | 说明 |
|------|------|------|
| 2024年 | 二零二四年 | 年份逐位读 |
| 3.14 | 三点一四 | 小数转换 |
| 666 | 六六六 | 俚语数字 |
| 100个 | 一百个 | 普通数字 |

**符号转换规则:**

| 输入 | 输出 |
|------|------|
| !!! | （激动） |
| ??? | （疑问） |
| —— | ， |

**使用示例:**

```python
from vv.audio.tts_normalizer import TTSNormalizer, SlangMapper

# 默认使用
normalizer = TTSNormalizer()
result = normalizer.normalize("2024年，AI发展迅速！！！")
# → "二零二四年，人工智能发展迅速（激动）"

# 自定义俚语映射
mapper = SlangMapper(config_path="custom_slang.yaml")
normalizer = TTSNormalizer(slang_mapper=mapper)
```

**配置参数:**

```python
from vv.audio.tts_normalizer import TTSNormalizerConfig

config = TTSNormalizerConfig(
    max_sentence_length=20,     # 最大句子长度
    convert_numbers=True,       # 数字转换
    convert_abbreviations=True, # 缩写转换
    convert_slang=False,        # 禁用俚语语义转换
)
```

### 7. 时间轴对齐 (Alignment Engine)

**核心原理:**
- **无需 ASR**: 直接使用 TTS 返回的音频时长
- **语速感知对齐**: 基于文本特征的时间分配算法
- 支持文本拆分（≤20字/行）

> ⚠️ **注意**: TTS 时间轴对齐方法存在固有缺陷——由于录音不是线性连续的，会导致字幕与音频错位。**推荐使用下方的 Whisper 音频驱动字幕生成方案。**

### 7.1 Whisper 音频驱动字幕生成（推荐）

**解决问题:**
- 录音非线性导致的字幕错位问题
- TTS 时间戳与实际音频不匹配
- 字幕滞后或提前于音频

**核心原理:**
- 使用 Whisper 进行音频识别，获取**词级别时间戳**
- 基于实际语音生成精确的字幕时间轴
- 支持时间偏移校正，微调字幕与音频的对齐

**技术流程:**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  音频预处理      │ →  │  Whisper 识别   │ →  │  字幕分段       │ →  │  ASS 生成       │
│  (FFmpeg)       │    │  (词级时间戳)   │    │  (语义断句)     │    │  (时间偏移校正) │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

**详细流程:**

1. **音频预处理 (FFmpeg)**
   - 统一采样率 (16kHz，Whisper 要求)
   - 转换为单声道
   - 可选去除前后静音

2. **Whisper 识别**
   - 使用 faster-whisper 进行音频识别
   - 获取每个词的精确开始/结束时间
   - 支持多种模型大小 (tiny/base/small/medium/large-v3)

3. **字幕分段 (语义断句)**
   - 优先在标点处断句（句号、逗号、问号等）
   - 每条字幕不超过 max_chars 字符（默认12）
   - 每条字幕不超过 max_duration 秒（默认3秒）

4. **ASS 生成 (时间偏移校正)**
   - 应用 time_offset 校正时间轴偏移
   - 可选 lead_time 提前显示字幕
   - 生成标准 ASS 格式

**使用示例:**

```python
from vv.audio.whisper_aligner import WhisperAlignerConfig, generate_ass_from_audio

config = WhisperAlignerConfig(
    model_size="large-v3",       # 推荐使用大模型
    language="zh",               # 中文
    max_chars_per_line=12,       # 每行最大字符
    time_offset=0.3,             # 字幕延后0.3秒（如果字幕太快）
    lead_time=0.0,               # 与音频同步
)

generate_ass_from_audio(
    audio_path="audio.mp3",
    output_path="subtitle.ass",
    config=config,
)
```

**关键参数说明:**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `model_size` | Whisper 模型大小 | `large-v3` |
| `max_chars_per_line` | 每行最大字符数 | `12` |
| `time_offset` | 时间偏移校正（正值延后，负值提前）| `0.0` |
| `lead_time` | 字幕提前显示时间 | `0.0` |

**time_offset 参数详解:**

```
字幕比音频快（字幕消失后声音才出）:
  → 使用正值延后字幕: time_offset=0.3

字幕比音频慢（声音先出，字幕后出）:
  → 使用负值提前字幕: time_offset=-0.3
```

**与 TTS 时间轴对齐的对比:**

| 特性 | TTS 时间轴对齐 | Whisper 音频驱动 |
|------|---------------|------------------|
| 时间戳来源 | TTS 合成时长 | 实际音频识别 |
| 准确度 | 中等（假设线性）| 高（实际语音）|
| 处理速度 | 快 | 较慢（需要识别）|
| 依赖 | 无额外依赖 | Whisper 模型 |
| 适用场景 | 快速预览 | **正式发布** |

**依赖安装:**

```bash
# 安装 faster-whisper（推荐，更快）
pip install faster-whisper

# 或安装 openai-whisper（原版）
pip install openai-whisper

# FFmpeg（必须）
brew install ffmpeg-full  # macOS
```

#### 语速感知字幕时间轴算法 (Speech-Aware Alignment)

传统的按字符数比例分配时间的方法忽略了标点、情绪等因素对朗读时长的影响。语速感知算法通过计算文本的"朗读权重"来更精确地分配字幕时间。

**权重计算公式:**

```
weight = len(text) × 1      # 基础字符权重
       + comma_count × 2    # 逗号/分号/冒号（需要停顿）
       + sentence_end × 4   # 句号/感叹/问号（句子结束）
       + pause_symbol × 6   # 省略号/破折号（长停顿）
       + emotion_tag × 3    # 情绪标签（语气转换）
```

**时间分配原理:**

```
每行时长 = 总时长 × (该行权重 / 总权重)
```

**关键特性:**

| 特性 | 说明 |
|------|------|
| 最小时长保护 | 每行至少 1.2 秒，避免闪现 |
| 句末停顿补偿 | 句号/感叹/问号后额外 +0.3s |
| 短句停顿 | <10 字短句额外 +0.2s |
| 悬念延迟 | 破折号/省略号后延迟 0.3s |
| 尾句强制对齐 | 最后一句结尾强制对齐音频结束时间 |

**代码示例:**

```python
from vv.audio.tts_alignment_engine import (
    generate_subtitles_for_book,
    build_speech_aware_timeline,
    AlignmentConfig,
)

# 完整流程（推荐）
generate_subtitles_for_book(
    book_name="三体",
    config=AlignmentConfig(
        max_chars_per_line=20,   # 每行最大字符
        use_speech_aware=True,   # 启用语速感知（默认开启）
        min_duration=1.2,        # 最小时长保护
        sentence_end_pause=0.3,  # 句末停顿
        suspense_delay=0.3,      # 悬念延迟
        output_format="ass",
    ),
)

# 直接使用语速感知时间轴
timeline = build_speech_aware_timeline(
    lines=["人类从来没有真正理解宇宙。", "直到这一刻——", "他们才意识到问题的严重性。"],
    audio_duration=6.0,
    debug=True,
)
# 输出:
#   1: 0.00s - 2.03s (2.03s) | 人类从来没有真正理解宇宙。
#   2: 2.03s - 4.77s (2.74s) | 直到这一刻——
#   3: 5.07s - 6.00s (0.93s) | 他们才意识到问题的严重性。
```

**权重计算示例:**

| 文本 | 权重 | 说明 |
|------|------|------|
| 普通句子 | 11.0 | 11 字 × 1 = 11 |
| 带逗号 | 14.0 | 12 字 × 1 + 1 逗号 × 2 = 14 |
| 句尾标点 | 15.0 | 11 字 × 1 + 1 句号 × 4 = 15 |
| 悬念句 | 16.0 | 8 字 × 1 + 1 破折号 × 6 = 14 → min(14, 1) = 14 |
| 带情绪标签 | 20.0 | 7 字 × 1 + 1 感叹 × 4 + 1 标签 × 3 = 14 |

**配置参数:**

```python
@dataclass
class AlignmentConfig:
    # 文本拆分
    max_chars_per_line: int = 20     # 每行最大字符
    max_lines_per_segment: int = 2   # 每段最大行数

    # 语速感知对齐（核心参数）
    use_speech_aware: bool = True    # 启用语速感知
    min_duration: float = 1.2        # 最小时长（秒）
    sentence_end_pause: float = 0.3  # 句末停顿（秒）
    short_sentence_pause: float = 0.2   # 短句停顿（秒）
    short_sentence_threshold: int = 10  # 短句阈值（字）
    suspense_delay: float = 0.3      # 悬念延迟（秒）
    suspense_patterns: tuple = ("——", "—", "……", "...")

    # 调试
    debug_alignment: bool = False    # 打印详细调试信息
```

### 8. ASS 字幕生成 (ASS Generator)

**短视频节奏优化:**
- 语义拆分（基于标点和语义）
- 情绪断句检测（短句独立显示）
- 悬念节奏（破折号句型特殊处理）
- 节奏优化���主语/副词开头切分）

**关键算法:**

```python
class SemanticTextSplitter:
    """语义文本拆分器"""

    def split(self, text: str) -> List[str]:
        # Step 1: 情绪断句检测
        if text in EMOTION_BREAKS:  # "停。"、"然后呢？"等
            return [text]

        # Step 2: 悬念句检测（破折号句型）
        # "真正的问题是——人性。" → ["真正的问题是——", "人性。"]

        # Step 3: 强调句检测（"关键是"、"重点是"等）

        # Step 4: 节奏优化（"今天"、"但是"等开头）

        # Step 5: 非递归语义拆分（队列实现，避免无限递归）
```

**ASS 样式配置:**

```python
@dataclass
class ASSConfig:
    # 字体（必须使用跨平台兼容字体！）
    font_name: str = "Arial Unicode MS"  # 最稳定的跨平台字体
    font_size: int = 56

    # 颜色（BGR 格式: &HAABBGGRR）
    primary_color: str = "&H00FFFFFF"  # 白色
    outline_color: str = "&H00000000"  # 黑色描边
    outline: float = 3.0

    # 对齐
    alignment: int = 2  # 底部居中
    margin_v: int = 100  # 底部安全区

    # 动画
    fade_in_ms: int = 150
    fade_out_ms: int = 150
```

### 9. 视频渲染 (Video Renderer)

**背景图片优先级策略:**

```
1. 用户指定背景图片 (--bg-image)
      ↓ (不存在时)
2. 爬虫下载的封面图片 (output/{书名}/images/cover.jpg)
      → 自动处理为 bg_processed.jpg（模糊背景 + 居中封面）
      ↓ (不存在时)
3. AI 生成的背景图片 (仅当 --use-ai-image 启用时)
      ↓ (失败或未启用)
4. 默认背景 (渐变/纯色)
```

**封面图片处理（prepare_background_image）:**

将爬虫下载的封面自动处理为短视频友好的背景图：

```
处理流程:
1. 创建 1080×1920 竖屏画布
2. 背景层: 原图放大填充 + 高斯模糊(radius=20)
3. 前景层: 原图等比缩放 + 居中放置
4. 暗化处理: 提升字幕对比度
5. 暗角效果: 增强视觉焦点
6. 缓存结果: 输出为 bg_processed.jpg
```

**FFmpeg 渲染流程:**

```bash
# 纯色背景 + ASS 字幕
ffmpeg -y -f lavfi -i "color=c=black:s=1080x1920:r=25" \
  -i audio.mp3 \
  -vf "ass=/path/to/subtitle.ass:fontsdir=/System/Library/Fonts" \
  -c:v libx264 -c:a aac \
  -b:v 5000k -b:a 192k \
  -preset medium -pix_fmt yuv420p \
  -shortest output.mp4
```

**关键实现细节:**

1. **fontsdir 参数**: 必须指定字体目录，否则 ASS 无法正确渲染
2. **路径处理**: 中文路径需要特殊处理（复制到临时英文路径）
3. **ASS 滤镜**: 使用 `ass=` 而非 `subtitles=`，支持 ASS 高级特性

```python
from vv.video.video_renderer import render_video, VideoRenderConfig

render_video(
    audio_path="audio.mp3",
    ass_path="subtitle.ass",
    output_path="output.mp4",
    config=VideoRenderConfig(
        width=1080,
        height=1920,  # 竖屏短视频
        fps=25,
        video_codec="libx264",
        audio_codec="aac",
    ),
)
```

### 10. 自动测试模块 (Testing)

自动测试模块作为钩子（Hook），在视频生成流程的每个环节完成后自动执行验证，确保输出结果符合预期。

**测试架构:**

```
Pipeline 任务执行 → post_execute() → 调用对应测试钩子 → 打印测试报告
```

**支持的测试钩子:**

| 钩子 | 对应环节 | 检查项 |
|------|----------|--------|
| `test_crawler_hook` | 爬虫 | 书评/短评数量、原文摘录、封面图片 |
| `test_filter_hook` | 筛选 | 差评/好评/中评数量、必须字段、总长度 |
| `test_content_hook` | 内容生成 | 大纲章节、分集数量、每集字数 |
| `test_tagger_hook` | 标签注入 | 标签覆盖率、标签有效性 |
| `test_tts_hook` | TTS 合成 | 音频数量、音频时长和大小 |
| `test_subtitle_hook` | 字幕生成 | 字幕数量、字符限制、时间轴连续性 |
| `test_video_hook` | 视频渲染 | 视频数量、分辨率/帧率、文件大小 |

**自动集成:**

测试钩子已集成到 Pipeline 任务中，每个任务完成后自动调用 `post_execute()` 执行测试：

```python
# Pipeline 执行流程
CrawlTask.execute() → CrawlTask.post_execute() → test_crawler_hook()
FilterTask.execute() → FilterTask.post_execute() → test_filter_hook()
ContentTask.execute() → ContentTask.post_execute() → test_content_hook()
TagTask.execute() → TagTask.post_execute() → test_tagger_hook()
TTSTask.execute() → TTSTask.post_execute() → test_tts_hook()
AlignTask.execute() → AlignTask.post_execute() → test_subtitle_hook()
RenderTask.execute() → RenderTask.post_execute() → test_video_hook()
```

**手动调用:**

```python
from vv.testing import test_crawler_hook, run_all_hooks

# 单独运行某个测试钩子
report = test_crawler_hook("三体", "./output")

# 运行所有测试钩子
reports = run_all_hooks("三体", "./output")

# 指定阶段运行
reports = run_all_hooks("三体", "./output", stages=["crawler", "tts", "video"])
```

**测试报告输出示例:**

```
============================================================
测试报告: crawler
书籍: 三体
状态: ✅ 全部通过
统计: 4/4 通过
耗时: 12.50ms
============================================================
  ✅ PASS | 书评数量: 书评数量正常: 15
  ✅ PASS | 短评数量: 短评数量正常: 40
  ✅ PASS | 原文摘录: 摘录数量正常: 10
  ✅ PASS | 封面图片: 封面正常: 245.3KB
```

**配置选项:**

```python
from vv.testing.test_config import TestConfig

config = TestConfig(
    fail_fast=True,       # 测试失败时停止后续测试
    save_report=True,     # 保存测试报告到文件
    report_dir="test_reports",  # 报告保存目录
)
```

**禁用测试:**

```python
# 在 TaskContext 中设置
context = TaskContext(
    book_name="三体",
    base_dir="./output",
    run_tests=False,  # 禁用自动测试
)
```

---

## 爬虫反检测功能

### Cookie 自动获取

系统支持自动从本机浏览器获取豆瓣 Cookie，无需手动导出：

```python
# 自动从 Chrome/Firefox/Edge 获取 Cookie
# 优先级: browser_cookie3 > cookies.json > 无Cookie

from vv.crawler.middlewares.cookie import get_browser_cookies

cookies = get_browser_cookies(domain="douban.com")
# 自动尝试: Chrome → Firefox → Edge
```

**支持的浏览器:**
- Google Chrome
- Firefox
- Microsoft Edge
- Safari (macOS)

### Selenium 隐身模式

隐藏自动化特征，避免被检测为 bot：

```python
from vv.crawler.core.selenium_downloader import SeleniumDownloader, SeleniumDownloaderConfig

config = SeleniumDownloaderConfig(
    stealth_mode=True,      # 启用隐身模式
    min_delay=2.0,          # 最小延迟
    max_delay=5.0,          # 最大延迟（随机）
    auto_cookie=True,       # 自动获取浏览器 Cookie
)

downloader = SeleniumDownloader(config)
```

**隐身特性:**
- 禁用 webdriver 标志 (`navigator.webdriver`)
- 随机窗口大小
- 真实浏览器请求头
- 随机访问节奏

### 风控检测

自动检测豆瓣风控页面并处理：

```python
if "sec.douban.com" in driver.current_url:
    logger.warning("触发豆瓣风控，尝试刷新或更换策略")
    # 自动重试或切换策略
```

---

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| HTTP | requests |
| HTML 解析 | BeautifulSoup4 + lxml |
| 浏览器自动化 | Selenium + webdriver-manager |
| Cookie 获取 | browser-cookie3 |
| LLM | OpenAI SDK (兼容通义千问) |
| TTS | 阶跃星辰 Step-TTS API |
| 视频处理 | FFmpeg + libass |
| 图像处理 | Pillow |
| 字幕格式 | ASS (Advanced SubStation Alpha) |

### 外部 API

| API | 用途 | 提供商 |
|-----|------|--------|
| 通义千问 API | 内容生成 | 阿里云 |
| Step-TTS API | 语音合成 | 阶跃星辰 |

---

## 关键问题与解决方案

### 1. ASS 字幕显示问题

**问题现象:**
- 红点/乱码字符
- 字幕倾斜/旋转
- 字体无法加载

**根本原因:**
- libass 不支持多字体回退（font1,font2 格式）
- 某些字体在 libass 中渲染异常
- ASS Style 格式需要严格遵守 22 个字段

**解决方案:**
```python
# ❌ 错误：多字体格式（libass 不支持）
font_name: str = "PingFang SC,Arial Unicode MS"

# ✅ 正确：单一字体
font_name: str = "Arial Unicode MS"

# 必须添加 fontsdir 参数
vf_filter = f"ass={ass_escaped}:fontsdir=/System/Library/Fonts"
```

### 2. 中文路径问题

**问题现象:**
- FFmpeg 无法找到 ASS 文件
- 路径解析错误

**解决方案:**
```python
def get_safe_ass_path(ass_path: str) -> str:
    """如果是中文路径，复制到临时英文路径"""
    if has_chinese_chars(ass_path):
        temp_ass = Path(tempfile.gettempdir()) / "vv_ass_temp" / "subtitle.ass"
        shutil.copy2(ass_path, temp_ass)
        return str(temp_ass)
    return ass_path

def escape_ass_path(path: str) -> str:
    """转义 FFmpeg 特殊字符"""
    path = path.replace("\\", "/")
    path = path.replace(":", "\\:")
    return path
```

### 3. 语义文本拆分无限递归

**问题现象:**
- 长文本拆分时递归调用栈溢出
- 程序卡死

**解决方案:**
```python
# 使用队列实现非递归拆分
def _semantic_split_queue(self, text: str) -> List[str]:
    queue = [(text, False, False)]  # (text, tried_strong, tried_weak)
    max_iterations = 100

    while queue and iteration < max_iterations:
        current, tried_strong, tried_weak = queue.pop(0)
        # ... 拆分逻辑
```

### 4. TTS 速率限制

**问题现象:**
- API 请求过于频繁被限流
- 429 Too Many Requests

**解决方案:**
```python
class RateLimiter:
    """令牌桶算法"""
    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm
        self.last_time = 0

    def wait(self):
        elapsed = time.time() - self.last_time
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_time = time.time()
```

### 5. 情绪标签频繁切换

**问题现象:**
- 每句话情绪标签都不同
- TTS 合成效果不自然

**解决方案:**
```python
class EmotionSmoother:
    """滑动窗口平滑"""
    def smooth(self, emotions: List[str]) -> List[str]:
        for i in range(len(emotions)):
            window = emotions[max(0, i-1):min(len(emotions), i+2)]
            # 如果当前情绪在窗口中只出现一次，替换为窗口中最常见的情绪
            if window.count(emotions[i]) == 1:
                emotions[i] = most_common(window)

class AutoTagger:
    MAX_EMOTION_DURATION = 2  # 情绪最多持续2句
    NARRATIVE_MARKERS = ["没哭", "没有", "开始", "然后", ...]  # 叙述性语言标志
```

---

## CLI 命令参考

### 全局参数

```bash
python main.py [command] [options]

--config, -c    配置文件路径
--debug, -d     启用调试模式
```

### crawler - 爬取书评

```bash
python main.py crawler -b "书名" [options]

-b, --book          书名（必需）
-o, --output        输出目录（默认: ./output）
--concurrency       并发数（默认: 3）
--rate-limit        请求间隔秒数（默认: 2.0）
--use-selenium      使用 Selenium（绕过反爬）
--download-cover    下载高清封面图片（默认: 开启）
```

**特性:**
- 自动从本机浏览器获取 Cookie（支持 Chrome/Firefox/Edge）
- 高清封面自动下载（/s/ → /l/ 升级）
- Selenium 隐身模式（`--use-selenium` 时自动启用）
- 随机访问节奏（2-5秒）

### filter - 评论筛选

```bash
python main.py filter -b "书名" [options]

-b, --book          书名（必需）
--bad-count         差评数量（默认: 5）
--good-count        好评数量（默认: 3）
--neutral-count     中评数量（默认: 2）
--quotes-count      摘录数量（默认: 3）
--max-length        最大总长度（默认: 3000）
--use-llm           使用 LLM 语义评分
```

### content - 内容生成

```bash
python main.py content -b "书名" [options]

-b, --book          书名（必需）
--step              执行步骤: outline/chapters/full/episodes/all（默认: all）
--force             强制重新生成（忽略缓存）
--model             LLM 模型（默认: qwen-plus）
```

### tag - 标签注入

```bash
python main.py tag -b "书名" [options]

-b, --book          书名（必需）
--voice             默认音色（默认: 磁性男声）
--frequency         每 N 句插入标签（默认: 3）
--debug             打印每句情绪
```

### tts - 语音合成

```bash
python main.py tts -b "书名" [options]

-b, --book          书名（必需）
--voice             默认音色（默认: 磁性男声）
--model             TTS 模型（默认: step-tts-2）
--workers           并发数（默认: 3）
--rpm               每分钟请求限制（默认: 8）
--no-cache          禁用缓存

# 分集筛选（三选一，互斥）
--episode N         只生成指定分集（如：--episode 1）
--episodes LIST     生成多个指定分集（如：--episodes 1,3,5）
--range START-END   生成分集范围（如：--range 1-3）

# 调试
--dry-run           试运行，只显示计划，不调用API
```

**分集筛选示例:**

```bash
# 只生成第1集（测试用）
python main.py tts -b "三体" --episode 1

# 生成多个指定分集
python main.py tts -b "三体" --episodes 1,3,5

# 生成分集范围
python main.py tts -b "三体" --range 1-3

# 试运行（查看将执行的分集，不消耗API额度）
python main.py tts -b "三体" --episode 1 --dry-run
```

**输出示例:**

```
🔊 TTS语音合成：《三体》
  默认音色: 磁性男声
  📋 指定分集: [1]

============================================================
🔊 TTS Executor
============================================================
  Input: output/三体/episodes_tagged.json
  Output: output/三体/audio
  📋 Selected episodes: [1]
  ⏭️  Skipping 9 episodes: [2, 3, 4, 5, 6, 7, 8, 9, 10]
  Episodes to process: 1
```

### align - 时间轴对齐

```bash
python main.py align -b "书名" [options]

-b, --book          书名（必需）
--max-chars         每行最大字符（默认: 20）
--buffer            结束时间缓冲秒数（默认: 0.1）
--format            输出格式: ass/srt/vtt/json/both（默认: ass）
```

> ⚠️ **推荐使用 `whisper` 命令替代 `align`**，以获得更准确的字幕时间轴。

### whisper - Whisper 音频驱动字幕生成（推荐）

使用 Whisper 进行音频识别，生成精确时间轴的字幕，解决录音非线性导致的字幕错位问题。

```bash
python main.py whisper [options]

# 单个音频文件
python main.py whisper -a "output/三体/audio/episode_1.mp3" -o "output/三体/subtitles/"

# 批量处理书籍
python main.py whisper -b "三体" -o "./output"

# 自定义参数
python main.py whisper -a "audio.mp3" \
    --model large-v3 \      # 使用更大的模型（更准确）
    --max-chars 12 \        # 每行最多12字符
    --time-offset 0.3       # 字幕延后0.3秒
```

**参数说明:**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-a, --audio` | 单个音频文件路径 | - |
| `-b, --book` | 书名（批量处理）| - |
| `-o, --output` | 输出目录 | `./output` |
| `-m, --model` | Whisper 模型大小 (tiny/base/small/medium/large/large-v3) | `large-v3` |
| `--max-chars` | 每行最大字符数 | `12` |
| `--font-size` | 字体大小 | `72` |
| `--lead-time` | 字幕提前显示时间（秒），正值提前 | `0.0` |
| `--time-offset` | 时间偏移校正（秒），正值延后 | `0.0` |
| `--debug` | 调试模式 | `False` |

**模型选择建议:**

| 模型 | 速度 | 准确度 | 显存需求 | 推荐场景 |
|------|------|--------|----------|----------|
| `tiny` | 最快 | 一般 | ~1GB | 快速预览 |
| `base` | 快 | 较好 | ~1GB | 测试调试 |
| `small` | 中等 | 好 | ~2GB | 一般使用 |
| `medium` | 较慢 | 很好 | ~5GB | 一般发布 |
| `large-v3` | 最慢 | 最好 | ~10GB | **正式发布** |

**时间调整指南:**

| 问题 | 解决方案 | 命令 |
|------|----------|------|
| 字幕比音频快（字幕消失后声音才出）| 延后字幕 | `--time-offset 0.3` |
| 字幕比音频慢（声音先出，字幕后出）| 提前字幕 | `--time-offset -0.3` |
| 字幕需要提前显示便于阅读 | 提前显示 | `--lead-time 0.5` |

**工作流程:**

```
[1/4] 音频预处理 - FFmpeg (16kHz, 单声道, 去静音)
[2/4] Whisper 识别 - 获取词级别时间戳
[3/4] 构建字幕片段 - 语义断句 (max 12 chars/line)
[4/4] 生成 ASS 文件 - 带时间偏移校正
```

### render - 视频渲染

```bash
python main.py render -b "书名" [options]

-b, --book          书名（必需）
--bg-type           背景类型: solid/gradient/image（默认: gradient）
--bg-image          背景图片路径（优先级最高）
--use-ai-image      使用 AI 生成背景图片
--image-prompt      AI 图片生成提示词（不指定则根据书名自动生成）
--ai-provider       AI 图片提供商: volcengine/dashscope（默认: volcengine）
--max-chars         每行最大字符（默认: 15）
--no-ken-burns      禁用 Ken Burns 效果
--use-moviepy       使用 MoviePy 渲染（默认: FFmpeg）
```

**背景图片优先级:**
1. `--bg-image` 指定的图片
2. 爬虫下载的封面（自动处理为模糊背景+居中封面）
3. AI 生成的背景（`--use-ai-image`）
4. 默认渐变背景

---

## 输出目录结构

```
output/{书名}/
├── {书名}_douban_书评.json           # 爬虫：书评
├── {书名}_douban_短评_好评.json       # 爬虫：好评短评
├── {书名}_douban_短评_一般.json       # 爬虫：一般短评
├── {书名}_douban_短评_差评.json       # 爬虫：差评短评
├── {书名}_douban_原文摘录.json       # 爬虫：原文摘录
├── images/                          # 图片资源
│   ├── cover.jpg                   # 爬虫下载的高清封面
│   ├── bg_processed.jpg            # 处理后的背景图（模糊+居中）
│   └── ai_background.jpg           # AI 生成的背景图（可选）
├── filtered.json                    # 筛选：高质量评论
├── 脚本/                            # 内容生成
│   ├── outline.txt                 # 大纲
│   ├── chapters/                   # 章节
│   │   ├── chapter_01.txt
│   │   └── ...
│   ├── full_script.txt             # 完整脚本
│   ├── episodes.json               # 分集元数据
│   ├── episodes_tagged.json        # 标记后的分集
│   └── episodes/                   # 分集文件
│       ├── ep_01.txt
│       └── ...
├── audio/                          # TTS 音频
│   ├── episode_1.mp3
│   ├── episode_2.mp3
│   └── ...
├── subtitles/                      # 字幕
│   ├── episode_1.ass              # ASS 字幕（默认）
│   ├── episode_1.srt              # SRT 字幕（可选）
│   └── ...
├── ass/                            # ASS 文件（渲染用）
│   ├── episode_1.ass
│   └── ...
└── videos/                         # 最终视频
    ├── episode_1.mp4
    ├── episode_2.mp4
    └── ...
```

---

## 常见问题

### FFmpeg 不支持 ASS 字幕

```bash
# 检查是否支持
ffmpeg -filters 2>&1 | grep ass

# 如果没有输出，需要重新安装
# macOS:
brew uninstall ffmpeg
brew install ffmpeg-full

# Ubuntu:
sudo apt install ffmpeg libass-dev
```

### LLM API 调用失败

```bash
# 检查环境变量
echo $LLM_API_KEY
echo $LLM_PROVIDER

# 测试 API 连接
curl https://dashscope.aliyuncs.com/compatible-mode/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY"
```

### TTS 合成失败

```bash
# 检查 API Key
echo $STEP_API_KEY

# 查看支持的音色
python main.py audio --help

# 列出所有音色
python -c "from vv.audio.step_tts import VOICE_NAME_TO_ID; print('\n'.join(VOICE_NAME_TO_ID.keys()))"
```

### 视频渲染中文路径问题

系统会自动处理中文路径，将 ASS 文件复制到临时英文路径。如果仍有问题，请检查：
1. FFmpeg 版本是否支持中文
2. 系统编码是否为 UTF-8

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 Pull Request！
