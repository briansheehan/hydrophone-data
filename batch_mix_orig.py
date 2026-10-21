import json
import shutil
import struct
import subprocess
import wave
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import numpy as np


CHUNK_FRAMES = 65_536
HEADROOM = 0.99
BASE_DIR = Path(__file__).resolve().parent
INPUT_FOLDER = BASE_DIR
OUTPUT_DIR = BASE_DIR / "mixed_outputs"
OUTPUT_PREFIX = "mixed_stereo"
METADATA_CACHE_PATH = BASE_DIR / "audio_metadata_cache.txt"
METADATA_CACHE_VERSION = 1
_AUDIO_INFO_CACHE: dict[Path, "AudioInfo"] = {}


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    frame_rate: int
    channels: int
    n_frames: int
    sample_width: int = 0
    is_flac: bool = False


def _read_pcm_samples(raw_data: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float64) - 128) / 128
    if sample_width == 2:
        return np.frombuffer(raw_data, dtype="<i2").astype(np.float64) / 32768
    if sample_width == 3:
        raw_bytes = np.frombuffer(raw_data, dtype=np.uint8).reshape(-1, 3)
        samples = (
            raw_bytes[:, 0].astype(np.int32)
            | (raw_bytes[:, 1].astype(np.int32) << 8)
            | (raw_bytes[:, 2].astype(np.int32) << 16)
        )
        samples = np.where(samples & 0x800000, samples - 0x1000000, samples)
        return samples.astype(np.float64) / 8388608
    if sample_width == 4:
        return np.frombuffer(raw_data, dtype="<i4").astype(np.float64) / 2147483648
    raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")


def _probe_flac(path: Path) -> AudioInfo:
    if shutil.which("ffprobe") is None:
        raise FileNotFoundError("ffprobe is required to read FLAC metadata")

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,duration_ts,time_base,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"{path.name}: ffprobe failed: {result.stderr.strip()}")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise ValueError(f"{path.name}: no audio stream found")

    stream = streams[0]
    frame_rate = int(stream["sample_rate"])
    channels = int(stream["channels"])
    if frame_rate <= 0 or channels <= 0:
        raise ValueError(
            f"{path.name}: ffprobe found invalid audio metadata "
            f"(sample_rate={frame_rate}, channels={channels}); "
            "the file may be corrupted or incomplete"
        )
    if "duration_ts" in stream and "time_base" in stream:
        duration_ts = int(stream["duration_ts"])
        time_base_num, time_base_den = map(int, stream["time_base"].split("/"))
        frame_count_num = duration_ts * time_base_num * frame_rate
        if frame_count_num % time_base_den:
            raise ValueError(
                f"{path.name}: audio duration does not resolve to whole frames"
            )
        n_frames = frame_count_num // time_base_den
    elif "duration" in stream:
        try:
            exact_frame_count = Decimal(stream["duration"]) * frame_rate
        except (InvalidOperation, TypeError) as error:
            raise ValueError(
                f"{path.name}: ffprobe returned an invalid audio duration"
            ) from error
        rounded_frame_count = exact_frame_count.to_integral_value(
            rounding=ROUND_HALF_UP
        )
        if abs(exact_frame_count - rounded_frame_count) > Decimal("0.5"):
            raise ValueError(
                f"{path.name}: audio duration does not resolve to whole frames"
            )
        n_frames = int(rounded_frame_count)
    else:
        raise ValueError(
            f"{path.name}: ffprobe returned neither duration_ts nor duration"
        )

    return AudioInfo(
        path=path,
        frame_rate=frame_rate,
        channels=channels,
        n_frames=n_frames,
        is_flac=True,
    )


def _inspect_audio(path: Path) -> AudioInfo:
    path = path.resolve()
    if path in _AUDIO_INFO_CACHE:
        return _AUDIO_INFO_CACHE[path]

    if path.suffix.lower() == ".flac":
        info = _probe_flac(path)
    else:
        with wave.open(str(path), "rb") as audio_file:
            if audio_file.getcomptype() != "NONE":
                raise ValueError(f"{path.name}: compressed WAV audio is not supported")
            sample_width = audio_file.getsampwidth()
            if sample_width not in (1, 2, 3, 4):
                raise ValueError(f"{path.name}: unsupported sample width ({sample_width} bytes)")
            info = AudioInfo(
                path=path,
                frame_rate=audio_file.getframerate(),
                channels=audio_file.getnchannels(),
                n_frames=audio_file.getnframes(),
                sample_width=sample_width,
            )

    _AUDIO_INFO_CACHE[path] = info
    return info


def _as_stereo(samples: np.ndarray, channels: int) -> np.ndarray:
    if channels == 1:
        return np.repeat(samples, 2, axis=1)
    if channels == 2:
        return samples
    raise ValueError(f"Expected mono or stereo audio, got {channels} channels")


def _parse_audio_timestamp(path: Path) -> datetime | None:
    stem = path.stem
    suffix = stem.rsplit("_", 1)[-1]
    try:
        return datetime.strptime(suffix, "%m%d%y-%H%M%S")
    except ValueError:
        return None


def _collect_audio_files(folder_path: Path) -> list[Path]:
    folder_path = folder_path.resolve()
    return sorted(
        path
        for path in folder_path.iterdir()
        if path.is_file() and path.suffix.lower() in (".wav", ".flac")
    )


def _group_audio_files_by_day(audio_files: list[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in audio_files:
        timestamp = _parse_audio_timestamp(path)
        if timestamp is None:
            continue
        grouped[timestamp.date().isoformat()].append(path)
    return dict(sorted(grouped.items()))


def _group_audio_files_by_week(audio_files: list[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in audio_files:
        timestamp = _parse_audio_timestamp(path)
        if timestamp is None:
            continue
        iso_year, iso_week, _ = timestamp.isocalendar()
        grouped[f"{iso_year}-W{iso_week:02d}"].append(path)
    return dict(sorted(grouped.items()))


def _group_audio_files_by_fortnight(audio_files: list[Path]) -> dict[str, list[Path]]:
    timestamps = []
    for path in audio_files:
        timestamp = _parse_audio_timestamp(path)
        if timestamp is not None:
            timestamps.append(timestamp)
    if not timestamps:
        return {}
    start_day = min(timestamp.date() for timestamp in timestamps)
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in audio_files:
        timestamp = _parse_audio_timestamp(path)
        if timestamp is None:
            continue
        offset_days = (timestamp.date() - start_day).days
        period_index = offset_days // 14
        period_start = start_day + timedelta(days=period_index * 14)
        period_end = period_start + timedelta(days=13)
        grouped[f"{period_start.isoformat()}_to_{period_end.isoformat()}"].append(path)
    return dict(sorted(grouped.items()))


def _build_output_path(name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{OUTPUT_PREFIX}_{name}.wav"


def _write_stereo_mix(output_path: Path, accumulator: np.ndarray, frame_rate: int) -> None:
    peak = np.max(np.abs(accumulator), initial=0.0)
    if peak > 0:
        accumulator *= HEADROOM / peak
    output_samples = accumulator.astype("<f4")
    data_size = output_samples.nbytes
    if data_size > 0xFFFFFFFF - 36:
        raise ValueError("Output is too large for a standard RIFF WAV file")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        output_file.write(
            struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF",
                data_size + 36,
                b"WAVE",
                b"fmt ",
                16,
                3,
                2,
                frame_rate,
                frame_rate * 8,
                8,
                32,
                b"data",
                data_size,
            )
        )
        output_file.write(output_samples.tobytes())
    print(f"Saved stereo mix to {output_path}", flush=True)


def _mix_audio_groups(
    audio_info: list[AudioInfo],
    output_groups: dict[str, list[Path]],
    frame_rate: int,
) -> None:
    info_by_path = {info.path: info for info in audio_info}
    group_names_by_path: dict[Path, list[str]] = defaultdict(list)
    accumulators: dict[str, np.ndarray] = {}
    group_frame_counts: dict[str, int] = {}
    remaining_files: dict[str, int] = {}
    mixed_files: dict[str, int] = defaultdict(int)

    for group_name, paths in output_groups.items():
        group_infos = [info_by_path[path.resolve()] for path in paths]
        group_frame_counts[group_name] = max(info.n_frames for info in group_infos)
        remaining_files[group_name] = len(paths)
        for path in paths:
            group_names_by_path[path.resolve()].append(group_name)

    def finish_groups(group_names: list[str]) -> None:
        for group_name in group_names:
            accumulator = accumulators.pop(group_name, None)
            if mixed_files[group_name]:
                if accumulator is None:
                    raise RuntimeError(
                        f"Missing accumulator for non-empty mix {group_name}"
                    )
                _write_stereo_mix(
                    _build_output_path(group_name),
                    accumulator,
                    frame_rate,
                )
            else:
                print(
                    f"Skipping empty mix {group_name}: all its input files were invalid.",
                    flush=True,
                )

    print(
        f"Decoding {len(audio_info)} input files once for "
        f"{len(output_groups)} stereo mixes at {frame_rate} Hz...",
        flush=True,
    )
    ordered_audio_info = sorted(
        audio_info,
        key=lambda info: (
            _parse_audio_timestamp(info.path) or datetime.min,
            str(info.path),
        ),
    )
    for index, info in enumerate(ordered_audio_info, start=1):
        group_names = group_names_by_path[info.path]
        for group_name in group_names:
            if group_name not in accumulators:
                accumulators[group_name] = np.zeros(
                    (group_frame_counts[group_name], 2),
                    dtype=np.float64,
                )
        decode_error = None

        def accumulate(samples: np.ndarray, frame_offset: int) -> None:
            stereo_samples = _as_stereo(samples, info.channels)
            end = frame_offset + len(stereo_samples)
            for group_name in group_names:
                accumulators[group_name][frame_offset:end] += stereo_samples

        if info.is_flac:
            if shutil.which("ffmpeg") is None:
                raise FileNotFoundError("ffmpeg is required to decode FLAC audio")
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(info.path),
                    "-map",
                    "0:a:0",
                    "-f",
                    "f32le",
                    "-acodec",
                    "pcm_f32le",
                    "-",
                ],
                capture_output=True,
                check=False,
            )
            error_message = result.stderr.decode(errors="replace").strip()
            if result.returncode != 0:
                decode_error = (
                    f"ffmpeg exited with status {result.returncode}"
                    + (f": {error_message}" if error_message else "")
                )
            elif error_message:
                decode_error = f"ffmpeg reported a decoding error: {error_message}"
            else:
                samples = np.frombuffer(result.stdout, dtype="<f4")
                if samples.size != info.n_frames * info.channels:
                    decode_error = (
                        f"decoded {samples.size} samples, expected "
                        f"{info.n_frames * info.channels} from metadata"
                    )
                else:
                    accumulate(samples.reshape(-1, info.channels), 0)
        else:
            with wave.open(str(info.path), "rb") as audio_file:
                frame_offset = 0
                while raw_data := audio_file.readframes(CHUNK_FRAMES):
                    samples = _read_pcm_samples(raw_data, info.sample_width)
                    samples = samples.reshape(-1, info.channels)
                    accumulate(samples, frame_offset)
                    frame_offset += len(samples)

        if decode_error is not None:
            print(
                f"Skipping invalid input file {info.path.name}: {decode_error}",
                flush=True,
            )
            _record_invalid_audio_file(info.path, decode_error)
        else:
            for group_name in group_names:
                mixed_files[group_name] += 1

        completed_groups = []
        for group_name in group_names:
            remaining_files[group_name] -= 1
            if remaining_files[group_name] == 0:
                completed_groups.append(group_name)
        finish_groups(completed_groups)

        if index % 100 == 0 or index == len(audio_info):
            print(
                f"Decoded and mixed {index}/{len(audio_info)} files "
                f"({len(accumulators)} mixes still accumulating)...",
                flush=True,
            )


def _load_metadata_cache() -> dict[str, dict]:
    if not METADATA_CACHE_PATH.exists():
        return {}
    try:
        cache_data = json.loads(METADATA_CACHE_PATH.read_text(encoding="utf-8"))
        if (
            cache_data.get("version") != METADATA_CACHE_VERSION
            or not isinstance(cache_data.get("files"), dict)
        ):
            raise ValueError("unsupported metadata cache format")
        return cache_data["files"]
    except (OSError, json.JSONDecodeError, AttributeError, ValueError) as error:
        print(
            f"Could not use metadata cache {METADATA_CACHE_PATH}: {error}. "
            "Rechecking input files.",
            flush=True,
        )
        return {}


def _save_metadata_cache(cache: dict[str, dict]) -> None:
    cache_data = {
        "version": METADATA_CACHE_VERSION,
        "files": cache,
    }
    temporary_path = METADATA_CACHE_PATH.with_suffix(".txt.tmp")
    temporary_path.write_text(
        json.dumps(cache_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(METADATA_CACHE_PATH)


def _record_invalid_audio_file(path: Path, error: str) -> None:
    path = path.resolve()
    file_size, modified_ns = _cache_file_signature(path)
    cache = _load_metadata_cache()
    cache[str(path)] = {
        "size": file_size,
        "modified_ns": modified_ns,
        "status": "invalid",
        "error": error,
    }
    _save_metadata_cache(cache)
    _AUDIO_INFO_CACHE.pop(path, None)


def _cache_file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _filter_invalid_flac_files(audio_files: list[Path]) -> list[Path]:
    valid_files = []
    cache = _load_metadata_cache()
    cache_changed = False
    for index, path in enumerate(audio_files, start=1):
        path = path.resolve()
        cache_key = str(path)
        file_size, modified_ns = _cache_file_signature(path)
        entry = cache.get(cache_key)
        if (
            entry is not None
            and entry.get("size") == file_size
            and entry.get("modified_ns") == modified_ns
        ):
            if entry.get("status") == "invalid":
                print(
                    f"Skipping invalid FLAC file {path.name}: "
                    f"{entry.get('error', 'previously failed metadata check')}",
                    flush=True,
                )
                continue
            if entry.get("status") == "valid" and all(
                key in entry
                for key in (
                    "frame_rate",
                    "channels",
                    "n_frames",
                    "sample_width",
                    "is_flac",
                )
            ):
                _AUDIO_INFO_CACHE[path] = AudioInfo(
                    path=path,
                    frame_rate=entry["frame_rate"],
                    channels=entry["channels"],
                    n_frames=entry["n_frames"],
                    sample_width=entry["sample_width"],
                    is_flac=entry["is_flac"],
                )
                valid_files.append(path)
                continue

        try:
            info = _inspect_audio(path)
        except ValueError as error:
            if path.suffix.lower() != ".flac":
                raise
            print(f"Skipping invalid FLAC file {path.name}: {error}", flush=True)
            cache[cache_key] = {
                "size": file_size,
                "modified_ns": modified_ns,
                "status": "invalid",
                "error": str(error),
            }
        else:
            valid_files.append(path)
            cache[cache_key] = {
                "size": file_size,
                "modified_ns": modified_ns,
                "status": "valid",
                "frame_rate": info.frame_rate,
                "channels": info.channels,
                "n_frames": info.n_frames,
                "sample_width": info.sample_width,
                "is_flac": info.is_flac,
            }
        cache_changed = True

        if index % 100 == 0 or index == len(audio_files):
            print(f"Checked {index}/{len(audio_files)} input files...", flush=True)

    if cache_changed:
        _save_metadata_cache(cache)

    if not valid_files:
        raise FileNotFoundError("No valid audio files remain after checking the inputs")
    return valid_files


def main() -> None:
    folder_path = Path(INPUT_FOLDER)
    all_audio_files = _collect_audio_files(folder_path)
    if not all_audio_files:
        raise FileNotFoundError(f"No input WAV or FLAC files found in {folder_path}")
    print(f"Checking {len(all_audio_files)} input files...", flush=True)
    all_audio_files = _filter_invalid_flac_files(all_audio_files)
    print(f"Using {len(all_audio_files)} valid input files.", flush=True)

    audio_info = [_inspect_audio(path) for path in all_audio_files]
    frame_rate = audio_info[0].frame_rate
    for info in audio_info:
        if info.frame_rate != frame_rate:
            raise ValueError(
                f"{info.path.name}: sample rate {info.frame_rate} Hz does not "
                f"match {frame_rate} Hz"
            )
        if info.channels not in (1, 2):
            raise ValueError(
                f"{info.path.name}: expected mono or stereo audio, got "
                f"{info.channels} channels"
            )

    output_groups = {"all": all_audio_files}
    output_groups.update(
        {
            f"day_{label}": paths
            for label, paths in _group_audio_files_by_day(all_audio_files).items()
        }
    )
    output_groups.update(
        {
            f"week_{label}": paths
            for label, paths in _group_audio_files_by_week(all_audio_files).items()
        }
    )
    output_groups.update(
        {
            f"fortnight_{label}": paths
            for label, paths in _group_audio_files_by_fortnight(all_audio_files).items()
        }
    )
    _mix_audio_groups(audio_info, output_groups, frame_rate)


if __name__ == "__main__":
    main()
