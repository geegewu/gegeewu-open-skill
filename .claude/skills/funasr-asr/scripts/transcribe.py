#!/usr/bin/env python3
"""语音识别工具 - FunASR（中文）/ mlx-whisper（多语言）"""

import argparse
import json
import datetime
import os
import subprocess
import sys
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────
MODEL_CACHE = Path.home() / ".cache/modelscope/hub/models/iic"
REQUIRED_MODELS = [
    "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc_ct-transformer_cn-en-common-vocab471067-large",
    "speech_campplus_sv_zh-cn_16k-common",
]
WHISPER_MODEL_SIZE = "medium"  # Faster-Whisper 模型规格
MLX_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"  # MLX 模型（Apple Silicon 默认）
SCRIPT_PATH = str(Path(__file__).resolve())
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".aac", ".ogg"}
TRANSCRIPT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def _write_transcript_log(
    audio_path: Path,
    output_path: Path,
    engine: str,
    segments: int,
    duration: str,
) -> None:
    """将转录过程和结果写入每日 log 文件。"""
    try:
        import logging as _logging
        TRANSCRIPT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = TRANSCRIPT_LOG_DIR / f"transcribe_{datetime.date.today().strftime('%Y-%m-%d')}.log"
        logger = _logging.getLogger("transcribe")
        if not logger.handlers:
            fmt = _logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            fh = _logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            logger.setLevel(_logging.INFO)
        audio_size_mb = audio_path.stat().st_size / 1024 / 1024 if audio_path.exists() else 0
        logger.info(
            f"转录完成 | engine={engine} | audio={audio_path.name} "
            f"({audio_size_mb:.1f}MB) | segments={segments} | duration={duration} | output={output_path}"
        )
    except Exception:
        pass  # log 写入失败不影响主流程


def check_models() -> tuple[bool, list[str]]:
    """检查模型是否存在"""
    missing = []
    for model_name in REQUIRED_MODELS:
        model_path = MODEL_CACHE / model_name
        if not model_path.exists():
            missing.append(model_name)
    return (len(missing) == 0, missing)


def select_engine() -> str:
    """交互式选择 ASR 引擎，返回 'mlx'、'funasr' 或 'whisper'"""
    print()
    print("请选择 ASR 引擎：")
    print("  1. MLX Whisper large-v3-turbo（默认，Apple Silicon，~12x realtime）")
    print("  2. FunASR（中文优先，带说话人分离）")
    print("  3. Faster-Whisper medium（CPU，兼容模式）")
    print()
    while True:
        choice = input("请输入 1/2/3（默认 1）：").strip() or "1"
        if choice == "1":
            return "mlx"
        elif choice == "2":
            return "funasr"
        elif choice == "3":
            return "whisper"
        else:
            print("❌ 无效输入，请输入 1、2 或 3")


def format_time(ms: int) -> str:
    """毫秒转换为 MM:SS.f 格式"""
    seconds = ms / 1000
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:04.1f}"


def run_local(audio_path: Path, output_path: Path) -> None:
    """本地运行语音识别"""
    # 延迟导入，避免无模型时 import 失败
    try:
        from funasr import AutoModel
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请安装依赖: pip install funasr>=1.0.14 modelscope>=1.9.0")
        sys.exit(1)

    print("🎙️ 正在加载模型...")
    model = AutoModel(
        model="paraformer-zh",
        model_revision="v2.0.4",
        vad_model="fsmn-vad",
        vad_model_revision="v2.0.4",
        punc_model="ct-punc",
        punc_model_revision="v2.0.4",
        spk_model="cam++",
        spk_model_revision="v2.0.2",
        device="cpu",
        ncpu=4,
        disable_update=True,
    )

    print(f"📝 正在处理: {audio_path.name}")
    result = model.generate(
        input=str(audio_path),
        sentence_timestamp=True,
        use_itn=True,
        batch_size_s=300,
    )

    if not result or not isinstance(result, list) or len(result) == 0:
        print("❌ 识别失败: 返回结果为空")
        sys.exit(1)

    res = result[0]
    sentence_info = res.get("sentence_info", [])

    # 收集说话人信息
    speakers = set()
    for sent in sentence_info:
        spk_id = sent.get("spk", 0)
        speakers.add(spk_id)

    # 计算总时长（取最后一个句子的结束时间）
    total_duration_ms = 0
    if sentence_info:
        last_sent = sentence_info[-1]
        total_duration_ms = last_sent.get("end", 0)
        if total_duration_ms == 0 and "timestamp" in last_sent:
            timestamps = last_sent["timestamp"]
            if timestamps:
                total_duration_ms = timestamps[-1][1]

    total_seconds = int(total_duration_ms / 1000)
    duration_str = f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    # 构建转录内容
    transcript_lines = []
    full_text_parts = []

    for sent in sentence_info:
        # 获取时间戳
        start_ms = sent.get("start", 0)
        end_ms = sent.get("end", 0)

        # fallback: 从 timestamp 字段提取
        if start_ms == 0 and "timestamp" in sent:
            timestamps = sent["timestamp"]
            if timestamps:
                start_ms = timestamps[0][0]
        if end_ms == 0 and "timestamp" in sent:
            timestamps = sent["timestamp"]
            if timestamps:
                end_ms = timestamps[-1][1]

        start_str = format_time(start_ms)
        end_str = format_time(end_ms)

        spk_id = sent.get("spk", 0)
        speaker = f"说话人{spk_id}"
        text = sent.get("text", "").strip()

        transcript_lines.append(f"[{start_str} - {end_str}] {speaker}: {text}")
        full_text_parts.append(text)

    # 写入文件
    output_content = f"""# 转录结果

**文件**：{audio_path.name}
**时长**：{duration_str}
**说话人数**：{len(speakers)}
**句子数**：{len(sentence_info)}

## 转录

{chr(10).join(transcript_lines)}

## 纯文本

{''.join(full_text_parts)}
"""

    output_path.write_text(output_content, encoding="utf-8")

    _write_transcript_log(audio_path, output_path, engine="funasr", segments=len(sentence_info), duration=duration_str)

    print(f"✅ 识别完成")
    print(f"   句子数: {len(sentence_info)}")
    print(f"   总时长: {duration_str}")
    print(f"   输出: {output_path}")


def run_local_whisper(audio_path: Path, output_path: Path) -> None:
    """使用 Faster-Whisper 本地运行语音识别"""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请安装依赖: pip install faster-whisper")
        sys.exit(1)

    print(f"🎙️ 正在加载 Whisper {WHISPER_MODEL_SIZE} 模型...")
    model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device="cpu",
        compute_type="int8",
        cpu_threads=8,
    )

    print(f"📝 正在处理: {audio_path.name}")
    segments, info = model.transcribe(
        str(audio_path),
        language=None,        # 自动检测语言
        word_timestamps=True,
        beam_size=1,
        vad_filter=True,
    )

    # 收集句子级段落
    sentence_list = []
    full_text_parts = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        start_ms = int(segment.start * 1000)
        end_ms = int(segment.end * 1000)
        sentence_list.append({
            "text": text,
            "start": start_ms,
            "end": end_ms,
        })
        full_text_parts.append(text)

    # 计算总时长
    total_duration_ms = sentence_list[-1]["end"] if sentence_list else 0
    total_seconds = int(total_duration_ms / 1000)
    duration_str = f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    # 构建转录内容
    transcript_lines = []
    for sent in sentence_list:
        start_str = format_time(sent["start"])
        end_str = format_time(sent["end"])
        text = sent["text"]
        transcript_lines.append(f"[{start_str} - {end_str}] {text}")

    output_content = f"""# 转录结果

**文件**：{audio_path.name}
**引擎**：Faster-Whisper {WHISPER_MODEL_SIZE}
**检测语言**：{info.language}
**时长**：{duration_str}
**句子数**：{len(sentence_list)}

## 转录

{chr(10).join(transcript_lines)}

## 纯文本

{''.join(full_text_parts)}
"""

    output_path.write_text(output_content, encoding="utf-8")

    _write_transcript_log(audio_path, output_path, engine="faster-whisper", segments=len(sentence_list), duration=duration_str)

    print(f"✅ 识别完成")
    print(f"   语言: {info.language}")
    print(f"   句子数: {len(sentence_list)}")
    print(f"   总时长: {duration_str}")
    print(f"   输出: {output_path}")


def run_local_mlx_whisper(audio_path: Path, output_path: Path) -> None:
    """使用 mlx-whisper（Apple Silicon MLX）运行语音识别"""
    try:
        import mlx.core as mx
        import mlx_whisper
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请安装依赖: pip install mlx mlx-whisper")
        sys.exit(1)

    # 限制 Metal cache，防止长音频 OOM
    mx.set_cache_limit(100 * 1024 * 1024)  # 100MB

    print(f"🎙️ 正在转录（mlx-whisper {MLX_WHISPER_MODEL}）...")
    print(f"📝 正在处理: {audio_path.name}")

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=MLX_WHISPER_MODEL,
        language="en" if audio_path.suffix.lower() in {".mp3", ".m4a", ".wav"} else None,
        fp16=True,
        word_timestamps=False,
        beam_size=None,                        # greedy decoding，更快更省内存
        condition_on_previous_text=True,       # 播客连贯性
        hallucination_silence_threshold=0.5,   # 防幻觉
        no_speech_threshold=0.6,
        verbose=False,
    )

    mx.clear_cache()

    segs = result.get("segments", [])
    if not segs:
        print("❌ 转录失败：无输出段落")
        sys.exit(1)

    lines = []
    for s in segs:
        start = f"{int(s['start']//60):02d}:{s['start']%60:05.2f}"
        end = f"{int(s['end']//60):02d}:{s['end']%60:05.2f}"
        lines.append(f"[{start} - {end}] {s['text'].strip()}")

    total_s = segs[-1]["end"] if segs else 0
    dur = f"{int(total_s//60):02d}:{int(total_s%60):02d}"
    full_text = " ".join(s["text"].strip() for s in segs)

    output_content = f"""# 转录结果

**文件**：{audio_path.name}
**引擎**：mlx-whisper large-v3-turbo
**时长**：{dur}
**句子数**：{len(segs)}

## 转录

{chr(10).join(lines)}

## 纯文本

{full_text}
"""
    output_path.write_text(output_content, encoding="utf-8")

    # 写转录 log
    _write_transcript_log(audio_path, output_path, engine="mlx-whisper", segments=len(segs), duration=dur)

    print(f"✅ 识别完成")
    print(f"   句子数: {len(segs)}")
    print(f"   总时长: {dur}")
    print(f"   输出: {output_path}")



def get_cache_path(audio_path: Path, engine: str) -> Path:
    """返回缓存文件路径：audio同级目录下的 .asr_cache/{stem}_{engine}.json"""
    cache_dir = audio_path.parent / ".asr_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{audio_path.stem}_{engine}.json"


def load_cache(audio_path: Path, engine: str) -> str | None:
    """
    尝试加载缓存，返回 transcript.md 内容字符串，验证失败或不存在返回 None。
    验证条件：文件大小 + mtime + engine 三者完全匹配。
    """
    cache_path = get_cache_path(audio_path, engine)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        meta = cache.get("meta", {})
        stat = audio_path.stat()
        if (
            meta.get("file_size") == stat.st_size
            and abs(meta.get("mtime", 0) - stat.st_mtime) < 1.0
            and meta.get("engine") == engine
        ):
            return cache.get("content", None)
    except Exception:
        pass
    return None


def save_cache(audio_path: Path, engine: str, output_path: Path) -> None:
    """将已生成的 transcript.md 内容保存到缓存文件。"""
    try:
        content = output_path.read_text(encoding="utf-8")
        stat = audio_path.stat()
        cache = {
            "meta": {
                "file_size": stat.st_size,
                "mtime": stat.st_mtime,
                "engine": engine,
                "cached_at": datetime.datetime.now().isoformat(),
            },
            "content": content,
        }
        cache_path = get_cache_path(audio_path, engine)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"💾 结果已缓存: {cache_path.name}")
    except Exception as e:
        print(f"⚠️ 缓存写入失败（不影响转录结果）: {e}")


def transcribe_single(audio_path: Path, output_path: Path, engine: str, no_cache: bool, delete_audio: bool = False) -> None:
    """转录单个音频文件（供单文件模式和文件夹模式共用）"""
    engine_label = {
        "mlx": "MLX Whisper（Apple Silicon）",
        "funasr": "FunASR（中文）",
        "whisper": "Faster-Whisper（多语言）",
    }.get(engine, engine)
    print(f"🔧 使用引擎: {engine_label}")

    # 缓存检查
    if not no_cache:
        cached = load_cache(audio_path, engine)
        if cached is not None:
            output_path.write_text(cached, encoding="utf-8")
            print(f"⚡ 命中缓存，跳过转录，直接返回结果")
            print(f"   输出: {output_path}")
            print(f"   （使用 --no-cache 强制重新转录）")
            return

    # 检查本地模型
    models_exist, missing_models = check_models()

    # 路由逻辑
    if engine == "mlx":
        run_local_mlx_whisper(audio_path, output_path)
        save_cache(audio_path, engine, output_path)
    elif engine == "whisper":
        run_local_whisper(audio_path, output_path)
        save_cache(audio_path, engine, output_path)
    elif engine == "funasr":
        if models_exist:
            run_local(audio_path, output_path)
            save_cache(audio_path, engine, output_path)
        else:
            print("❌ FunASR 模型缺失，请先安装模型：")
            print("  pip install funasr>=1.0.14 modelscope>=1.9.0")
            print(f"  缺失: {', '.join(missing_models)}")
            sys.exit(1)


    if delete_audio and audio_path.exists():
        audio_path.unlink()
        print(f"🗑️  音频已删除: {audio_path.name}")

def _notify_telegram(output_path: Path) -> None:
    """转录完成后推送 Telegram 通知（单文件）"""
    import urllib.request, urllib.parse, os
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    text = f"✅ 转录完成：{output_path}"
    data = urllib.parse.urlencode({"chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""), "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=10)
    except Exception:
        pass


def _notify_telegram_batch(outputs: list, folder: Path) -> None:
    """转录完成后推送 Telegram 通知（文件夹批量）"""
    import urllib.request, urllib.parse, os
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    lines = [f"✅ 批量转录完成：{folder.name}（共 {len(outputs)} 个文件）\n"]
    lines.append("💡 下一步建议：")
    lines.append(f"`合并转录 {folder}`")
    text = "\n".join(lines)
    data = urllib.parse.urlencode({"chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""), "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=10)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="语音识别（FunASR / Faster-Whisper）")
    parser.add_argument("audio", help="音频文件路径或文件夹路径")
    parser.add_argument("--output", default=None,
                        help="输出文件路径（单文件模式，默认: 与音频同目录的 {stem}_transcript.md）")
    parser.add_argument("--engine", choices=["1", "2", "3", "mlx", "funasr", "whisper"], default=None,
                        help="ASR 引擎：1/mlx（默认，Apple Silicon）、2/funasr（中文）、3/whisper（CPU），不指定则交互选择")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略缓存，强制重新转录")
    parser.add_argument("--output-dir", default=None,
                        help="转录结果存档目录（按日期存储 YYYY-MM-DD/{stem}_transcript.md），与 --output 互斥")
    parser.add_argument("--delete-audio", action="store_true",
                        help="转录完成后删除原始音频文件")
    args = parser.parse_args()

    audio_path = Path(args.audio)

    # ── 文件夹模式 ──────────────────────────────────────────────────────────────
    if audio_path.is_dir():
        audio_files = sorted([f for f in audio_path.iterdir() if f.suffix.lower() in AUDIO_EXTS])
        if not audio_files:
            print(f"❌ 文件夹中未找到音频文件: {audio_path}")
            sys.exit(1)
        _raw = args.engine if args.engine else select_engine()
        engine = {"1": "mlx", "2": "funasr", "3": "whisper"}.get(_raw, _raw)
        print(f"\n📁 文件夹模式：发现 {len(audio_files)} 个音频文件")
        outputs = []
        for i, af in enumerate(audio_files, 1):
            out = af.parent / f"{af.stem}_transcript.md"
            print(f"\n[{i}/{len(audio_files)}] 正在转录：{af.name}")
            transcribe_single(af, out, engine, args.no_cache, args.delete_audio)
            outputs.append(out)
        print(f"\n✅ 全部转录完成，共 {len(outputs)} 个文件：")
        for o in outputs:
            print(f"   {o}")
        print("\n💡 下一步建议：")
        print(f"\n如需将分段录音合并后统一处理（同一场会议）：")
        print(f"`合并转录 {audio_path}`")
        print(f"\n如需分别处理每段：")
        for o in outputs:
            print(f"`meeting-summary {o}`")
        _notify_telegram_batch(outputs, audio_path)
        return

    # ── 单文件模式 ─────────────────────────────────────────────────────────────
    if not audio_path.exists():
        print(f"❌ 音频文件不存在: {audio_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    elif args.output_dir:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        archive_dir = Path(args.output_dir) / today
        archive_dir.mkdir(parents=True, exist_ok=True)
        output_path = archive_dir / f"{audio_path.stem}_transcript.md"
    else:
        output_path = audio_path.parent / f"{audio_path.stem}_transcript.md"
    _raw = args.engine if args.engine else select_engine()
    engine = {"1": "mlx", "2": "funasr", "3": "whisper"}.get(_raw, _raw)
    transcribe_single(audio_path, output_path, engine, args.no_cache, args.delete_audio)
    print(f"\n✅ 转录完成：{output_path}")
    print(f"\n💡 下一步建议：")
    print(f"`meeting-summary {output_path}`")
    _notify_telegram(output_path)


if __name__ == "__main__":
    main()
