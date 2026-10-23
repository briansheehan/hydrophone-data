# Auto generated code originating from this google query:
# https://www.google.com/search?q=python+sum+thousands+of+audio+files+without+clipping+with+64-bit+math&sxsrf=APpeQntPYCR3SHNzHzGXOQNZs_5251pSkw%3A1791904986724
# Added to using Co-pilot in VSCODE
import csv
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import soundfile as sf


OUTPUT_METADATA_FILENAME = "output_metadata"
OUTPUT_METADATA_COLUMNS = (
    "output_file_name",
    "number_of_wavs_summed",
    "period_start_timestamp",
    "period_end_timestamp",
    "integrated_lufs",
    "normalization_factor",
)


def timestamp_for_file(path):
    match = re.search(r'(?<!\d)(\d{6}-\d{6})(?!\d)', os.path.basename(path))
    if not match:
        raise ValueError(f"No MMDDYY-HHMMSS timestamp found in filename: {path}")

    try:
        timestamp = datetime.strptime(match.group(1), "%m%d%y-%H%M%S")
    except ValueError as error:
        raise ValueError(f"Invalid timestamp in filename: {path}") from error

    return timestamp


def period_for_file(path, reference_timestamp, latest_timestamp, period_days, period_label):
    timestamp = timestamp_for_file(path)
    period_index = (timestamp - reference_timestamp) // timedelta(days=period_days)
    period_start = reference_timestamp + timedelta(days=period_index * period_days)
    if period_start + timedelta(days=period_days) > latest_timestamp:
        return None
    return f"{period_start.year}-{period_label}{period_index + 1:02d}"


def timestamp_range_suffix(file_paths):
    timestamps = [timestamp_for_file(path) for path in file_paths]
    first_timestamp = min(timestamps)
    last_timestamp = max(timestamps)
    return (
        f"_{first_timestamp:%Y-%m-%dT%H:%M}"
        f"_{last_timestamp:%Y-%m-%dT%H:%M}"
    )


def file_count_suffix(file_paths):
    return f"_{len(file_paths):05d}"


def _integrated_lufs(output_path, ffmpeg_path):
    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-nostats",
            "-i",
            output_path,
            "-filter_complex",
            "ebur128=framelog=quiet",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not measure integrated loudness for {output_path}: "
            f"{result.stderr.strip()}"
        )

    match = re.search(
        r"Integrated loudness:\s*\n\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS",
        result.stderr,
    )
    if match is None:
        raise RuntimeError(
            f"FFmpeg did not report integrated loudness for {output_path}"
        )
    return float(match.group(1))


def _metadata_output_order(output_file):
    filename = os.path.basename(output_file)
    match = re.match(r"(full|half|quarter|eighth)(\d*)_", filename)
    if match is None:
        return 4, 0

    group_order = {"full": 0, "half": 1, "quarter": 2, "eighth": 3}
    return group_order[match.group(1)], int(match.group(2) or 0)


def _write_output_metadata(output_directory, output_files, audio_files):
    ffmpeg_path = shutil.which("ffmpeg")
    if output_files and ffmpeg_path is None:
        raise FileNotFoundError(
            "ffmpeg is required to measure integrated loudness for output WAVs"
        )

    os.makedirs(output_directory, exist_ok=True)
    if audio_files:
        timestamps = [timestamp_for_file(path) for path in audio_files]
        metadata_filename = (
            f"{OUTPUT_METADATA_FILENAME}_"
            f"{min(timestamps):%Y-%m-%d}_"
            f"{max(timestamps):%Y-%m-%d}.csv"
        )
    else:
        metadata_filename = f"{OUTPUT_METADATA_FILENAME}.csv"
    metadata_path = os.path.join(output_directory, metadata_filename)
    with open(metadata_path, "w", newline="", encoding="utf-8") as metadata_file:
        writer = csv.DictWriter(metadata_file, fieldnames=OUTPUT_METADATA_COLUMNS)
        writer.writeheader()
        ordered_output_files = sorted(
            output_files,
            key=lambda output: _metadata_output_order(output[0]),
        )
        for output_path, input_paths, normalization_factor in ordered_output_files:
            timestamps = [timestamp_for_file(path) for path in input_paths]
            writer.writerow(
                {
                    "output_file_name": os.path.basename(output_path),
                    "number_of_wavs_summed": len(input_paths),
                    "period_start_timestamp": min(timestamps).isoformat(),
                    "period_end_timestamp": max(timestamps).isoformat(),
                    "integrated_lufs": _integrated_lufs(
                        output_path,
                        ffmpeg_path,
                    ),
                    "normalization_factor": normalization_factor,
                }
            )


def _sum_audio_files(file_paths, output_path, normalization_factor=None):
    """
    Sums thousands of audio files using 64-bit float math to prevent clipping.
    Assumes all files have the same sample rate and channel count.
    """
    if not file_paths:
        print("No files provided.")
        return

    # 1. Get metadata from the first file to initialize our master buffer
    info = sf.info(file_paths[0])
    sample_rate = info.samplerate
    channels = info.channels
    
    # Find the maximum duration among all files to allocate enough space
    max_frames = max(sf.info(f).frames for f in file_paths)
    
    # 2. Allocate a 64-bit float buffer initialized to zeros
    # Shape is (frames, channels) for multi-channel audio
    master_buffer = np.zeros((max_frames, channels), dtype=np.float64)
    
    #print(dtype=np.float64) # Explictly tracking 64-bit precision
    print(f"Accumulating {len(file_paths)} files into 64-bit mix bus...")

    # 3. Accumulate all audio files into the 64-bit buffer
    for path in file_paths:
        # Read file directly into float64; soundfile automatically scales 
        # integer PCM (16/24-bit) to [-1.0, 1.0] float values.
        data, data_sr = sf.read(path, dtype='float64', always_2d=True)
        if data_sr != sample_rate: print(f"Sample rate of {path} is {data_sr}, not {sample_rate} as expected")
        # Add to master buffer (handles mismatched lengths safely)
        master_buffer[:len(data), :] += data

    return _write_normalized_mix(
        master_buffer,
        sample_rate,
        output_path,
        normalization_factor,
    )


def _write_normalized_mix(
    mix_buffer,
    sample_rate,
    output_path,
    normalization_factor=None,
):
    peak = np.max(np.abs(mix_buffer))
    if normalization_factor is None:
        normalization_factor = 1.0 / peak if peak > 1.0 else 1.0

    normalized_peak = peak * normalization_factor
    if normalized_peak > 1.0:
        print(
            f"Warning: peak {normalized_peak:.2f} exceeds 1.0 after applying "
            "the shared normalization factor."
        )
    elif normalization_factor < 1.0:
        print(
            f"Applying normalization factor {normalization_factor:.6f} "
            "from the all-files mix."
        )
    else:
        print("No peak clipping detected. Keeping original headroom.")

    sf.write(
        output_path,
        mix_buffer * normalization_factor,
        sample_rate,
        subtype="PCM_24",
    )
    print(f"Successfully saved combined mix to: {output_path}")
    return normalization_factor


def _combine_mix_buffers(mix_buffers):
    nonempty_buffers = [buffer for buffer in mix_buffers if buffer is not None]
    max_frames = max(len(buffer) for buffer in nonempty_buffers)
    channels = nonempty_buffers[0].shape[1]
    combined_buffer = np.zeros((max_frames, channels), dtype=np.float64)
    for buffer in nonempty_buffers:
        combined_buffer[:len(buffer), :] += buffer
    return combined_buffer


def sum_audio_files(file_paths, normalization_factor=None):
    if not file_paths:
        return _sum_audio_files(file_paths, "", normalization_factor)
    output_path = (
        f"{timestamp_range_suffix(file_paths).lstrip('_')}"
        f"{file_count_suffix(file_paths)}.wav"
    )
    return _sum_audio_files(file_paths, output_path, normalization_factor)


def mix_audio_directory(audio_path, output_directory="."):
    audio_files = [
        os.path.join(audio_path, filename)
        for filename in os.listdir(audio_path)
        if filename.endswith(".wav")
    ]
    if not audio_files:
        sum_audio_files(audio_files)
        _write_output_metadata(output_directory, [], audio_files)
        return

    output_files = []
    timestamps_by_file = {
        path: timestamp_for_file(path)
        for path in audio_files
    }
    reference_timestamp = min(timestamps_by_file.values())
    latest_timestamp = max(timestamps_by_file.values())
    files_by_four_week_period = {}
    files_by_fortnightly_period = {}
    files_by_week = {}
    for path in audio_files:
        period = period_for_file(
            path, reference_timestamp, latest_timestamp, 28, "4W"
        )
        if period is not None:
            files_by_four_week_period.setdefault(period, []).append(path)
        fortnight = period_for_file(
            path, reference_timestamp, latest_timestamp, 14, "2W"
        )
        if fortnight is not None:
            files_by_fortnightly_period.setdefault(fortnight, []).append(path)
        week = period_for_file(
            path, reference_timestamp, latest_timestamp, 7, "W"
        )
        if week is not None:
            files_by_week.setdefault(week, []).append(path)

    dated_output_path = os.path.join(
        output_directory,
        f"{timestamp_range_suffix(audio_files).lstrip('_')}"
        f"{file_count_suffix(audio_files)}.wav",
    )
    normalization_factor = _sum_audio_files(audio_files, dated_output_path)
    output_files.append((dated_output_path, audio_files, normalization_factor))
    for period, period_files in sorted(files_by_four_week_period.items()):
        output_path = os.path.join(
            output_directory,
            f"{period}{timestamp_range_suffix(period_files)}"
            f"{file_count_suffix(period_files)}.wav",
        )
        period_normalization_factor = _sum_audio_files(
            period_files,
            output_path,
            normalization_factor,
        )
        output_files.append(
            (output_path, period_files, period_normalization_factor)
        )
    for fortnight, fortnight_files in sorted(files_by_fortnightly_period.items()):
        output_path = os.path.join(
            output_directory,
            f"{fortnight}{timestamp_range_suffix(fortnight_files)}"
            f"{file_count_suffix(fortnight_files)}.wav",
        )
        fortnight_normalization_factor = _sum_audio_files(
            fortnight_files,
            output_path,
            normalization_factor,
        )
        output_files.append(
            (output_path, fortnight_files, fortnight_normalization_factor)
        )
    for week, week_files in sorted(files_by_week.items()):
        output_path = os.path.join(
            output_directory,
            f"{week}{timestamp_range_suffix(week_files)}"
            f"{file_count_suffix(week_files)}.wav",
        )
        week_normalization_factor = _sum_audio_files(
            week_files,
            output_path,
            normalization_factor,
        )
        output_files.append((output_path, week_files, week_normalization_factor))
    _write_output_metadata(output_directory, output_files, audio_files)


def mix_audio_directory_by_time_span(audio_path, output_directory="."):
    audio_files = [
        os.path.join(audio_path, filename)
        for filename in os.listdir(audio_path)
        if filename.endswith(".wav")
    ]
    if not audio_files:
        sum_audio_files(audio_files)
        _write_output_metadata(output_directory, [], audio_files)
        return

    output_files = []
    timestamps_by_file = {
        path: timestamp_for_file(path)
        for path in audio_files
    }
    first_timestamp = min(timestamps_by_file.values())
    last_timestamp = max(timestamps_by_file.values())
    span_microseconds = (last_timestamp - first_timestamp) // timedelta(microseconds=1)
    files_by_eighth = [[] for _ in range(8)]
    eighth_index_by_path = {}
    for path, timestamp in timestamps_by_file.items():
        elapsed_microseconds = (
            (timestamp - first_timestamp) // timedelta(microseconds=1)
        )
        if span_microseconds == 0:
            period_index = 0
        else:
            period_index = min(
                elapsed_microseconds * 8 // span_microseconds,
                7,
            )
        files_by_eighth[period_index].append(path)
        eighth_index_by_path[path] = period_index

    file_info = {
        path: sf.info(path)
        for path in audio_files
    }
    sample_rate = file_info[audio_files[0]].samplerate
    channels = file_info[audio_files[0]].channels
    max_frames = max(info.frames for info in file_info.values())
    total_buffer = np.zeros((max_frames, channels), dtype=np.float64)
    eighth_buffers = []
    for eighth_files in files_by_eighth:
        if not eighth_files:
            eighth_buffers.append(None)
            continue
        eighth_frames = max(file_info[path].frames for path in eighth_files)
        eighth_buffers.append(
            np.zeros((eighth_frames, channels), dtype=np.float64)
        )

    print(f"Accumulating {len(audio_files)} files into 64-bit mix buses...")
    for path in audio_files:
        eighth_index = eighth_index_by_path[path]
        data, data_sr = sf.read(path, dtype="float64", always_2d=True)
        if data_sr != sample_rate:
            print(
                f"Sample rate of {path} is {data_sr}, not {sample_rate} as expected"
            )
        total_buffer[:len(data), :] += data
        eighth_buffers[eighth_index][:len(data), :] += data

    full_span_output_path = os.path.join(
        output_directory,
        f"full{timestamp_range_suffix(audio_files)}"
        f"{file_count_suffix(audio_files)}.wav",
    )
    normalization_factor = _write_normalized_mix(
        total_buffer,
        sample_rate,
        full_span_output_path,
    )
    output_files.append(
        (full_span_output_path, audio_files, normalization_factor)
    )
    del total_buffer

    # Write eighths before reducing their buffers into quarters and halves.
    for period_index, period_files in enumerate(files_by_eighth, start=1):
        if not period_files:
            continue
        output_path = os.path.join(
            output_directory,
            f"eighth{period_index:02d}"
            f"{timestamp_range_suffix(period_files)}"
            f"{file_count_suffix(period_files)}.wav",
        )
        period_normalization_factor = _write_normalized_mix(
            eighth_buffers[period_index - 1],
            sample_rate,
            output_path,
            normalization_factor,
        )
        output_files.append(
            (output_path, period_files, period_normalization_factor)
        )

    def write_group_mixes(period_label, files_by_period, period_buffers):
        for period_index, period_files in enumerate(files_by_period, start=1):
            if not period_files:
                continue
            output_path = os.path.join(
                output_directory,
                f"{period_label}{period_index:02d}"
                f"{timestamp_range_suffix(period_files)}"
                f"{file_count_suffix(period_files)}.wav",
            )
            period_normalization_factor = _write_normalized_mix(
                period_buffers[period_index - 1],
                sample_rate,
                output_path,
                normalization_factor,
            )
            output_files.append(
                (output_path, period_files, period_normalization_factor)
            )

    quarter_files = []
    quarter_buffers = []
    for index in range(0, 8, 2):
        period_files = files_by_eighth[index] + files_by_eighth[index + 1]
        quarter_files.append(period_files)
        quarter_buffers.append(
            _combine_mix_buffers(eighth_buffers[index:index + 2])
            if period_files
            else None
        )
        eighth_buffers[index] = None
        eighth_buffers[index + 1] = None
    write_group_mixes("quarter", quarter_files, quarter_buffers)

    half_files = []
    half_buffers = []
    for index in range(0, 4, 2):
        period_files = quarter_files[index] + quarter_files[index + 1]
        half_files.append(period_files)
        half_buffers.append(
            _combine_mix_buffers(quarter_buffers[index:index + 2])
            if period_files
            else None
        )
        quarter_buffers[index] = None
        quarter_buffers[index + 1] = None
    write_group_mixes("half", half_files, half_buffers)
    _write_output_metadata(output_directory, output_files, audio_files)


def _assert_output_metadata(
    output_directory,
    expected_outputs,
    expected_normalization_factor,
):
    metadata_paths = [
        filename
        for filename in os.listdir(output_directory)
        if filename.startswith(f"{OUTPUT_METADATA_FILENAME}_")
        and filename.endswith(".csv")
    ]
    assert len(metadata_paths) == 1, metadata_paths
    metadata_path = os.path.join(output_directory, metadata_paths[0])
    with open(metadata_path, newline="", encoding="utf-8") as metadata_file:
        rows = list(csv.DictReader(metadata_file))

    assert set(row["output_file_name"] for row in rows) == expected_outputs
    output_names = [row["output_file_name"] for row in rows]
    assert output_names == sorted(output_names, key=_metadata_output_order)
    assert all(
        set(row) == set(OUTPUT_METADATA_COLUMNS)
        for row in rows
    )
    for row in rows:
        filename = row["output_file_name"]
        count_match = re.search(r"_(\d{5})\.wav$", filename)
        timestamps = re.findall(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",
            filename,
        )
        assert count_match is not None, filename
        assert len(timestamps) == 2, filename
        assert int(row["number_of_wavs_summed"]) == int(count_match.group(1))
        assert datetime.fromisoformat(
            row["period_start_timestamp"]
        ).strftime("%Y-%m-%dT%H:%M") == timestamps[0]
        assert datetime.fromisoformat(
            row["period_end_timestamp"]
        ).strftime("%Y-%m-%dT%H:%M") == timestamps[1]
        assert np.isfinite(float(row["integrated_lufs"]))
        assert np.isclose(
            float(row["normalization_factor"]),
            expected_normalization_factor,
        )

    start_timestamp = min(
        datetime.fromisoformat(row["period_start_timestamp"])
        for row in rows
    )
    end_timestamp = max(
        datetime.fromisoformat(row["period_end_timestamp"])
        for row in rows
    )
    assert metadata_paths[0] == (
        f"{OUTPUT_METADATA_FILENAME}_"
        f"{start_timestamp:%Y-%m-%d}_"
        f"{end_timestamp:%Y-%m-%d}.csv"
    )


def test_four_week_and_weekly_mixes():
    """Verify total and anchored weekly, fortnightly, and four-week mix outputs."""
    sample_rate = 8000
    test_files = {
        "CATA01_070121-120000.wav": 0.2,
        "CATA01_070221-120000.wav": 0.1,
        "CATA01_072121-120000.wav": 0.3,
        "CATA01_080121-120000.wav": 0.4,
        "CATA01_123120-120000.wav": 0.05,
        "CATA01_010121-120000.wav": 0.06,
        "CATA01_010421-120000.wav": 0.07,
        "CATA01_010721-115959.wav": 0.08,
        "CATA01_010721-120000.wav": 0.09,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = os.path.join(temp_dir, "wavs", "test")
        os.makedirs(audio_path)

        for filename, value in test_files.items():
            samples = np.full((8, 1), value)
            sf.write(
                os.path.join(audio_path, filename),
                samples,
                sample_rate,
                subtype="PCM_24",
            )

        mix_audio_directory(audio_path, temp_dir)

        expected_outputs = {
            "2020-12-31T12:00_2021-08-01T12:00_00009.wav",
            "2020-4W01_2020-12-31T12:00_2021-01-07T12:00_00005.wav",
            "2021-4W07_2021-07-01T12:00_2021-07-02T12:00_00002.wav",
            "2020-2W01_2020-12-31T12:00_2021-01-07T12:00_00005.wav",
            "2021-2W14_2021-07-01T12:00_2021-07-02T12:00_00002.wav",
            "2021-2W15_2021-07-21T12:00_2021-07-21T12:00_00001.wav",
            "2020-W01_2020-12-31T12:00_2021-01-07T11:59_00004.wav",
            "2021-W02_2021-01-07T12:00_2021-01-07T12:00_00001.wav",
            "2021-W27_2021-07-01T12:00_2021-07-02T12:00_00002.wav",
            "2021-W29_2021-07-21T12:00_2021-07-21T12:00_00001.wav",
        }
        actual_outputs = {
            filename
            for filename in os.listdir(temp_dir)
            if filename.endswith(".wav")
        }
        assert actual_outputs == expected_outputs, actual_outputs
        normalization_factor = 1.0 / 1.35
        _assert_output_metadata(
            temp_dir,
            expected_outputs,
            normalization_factor,
        )
        expected_values = {
            "2020-12-31T12:00_2021-08-01T12:00_00009.wav": 1.0,
            "2020-4W01_2020-12-31T12:00_2021-01-07T12:00_00005.wav": 0.35 * normalization_factor,
            "2021-4W07_2021-07-01T12:00_2021-07-02T12:00_00002.wav": 0.3 * normalization_factor,
            "2020-2W01_2020-12-31T12:00_2021-01-07T12:00_00005.wav": 0.35 * normalization_factor,
            "2021-2W14_2021-07-01T12:00_2021-07-02T12:00_00002.wav": 0.3 * normalization_factor,
            "2021-2W15_2021-07-21T12:00_2021-07-21T12:00_00001.wav": 0.3 * normalization_factor,
            "2020-W01_2020-12-31T12:00_2021-01-07T11:59_00004.wav": 0.26 * normalization_factor,
            "2021-W02_2021-01-07T12:00_2021-01-07T12:00_00001.wav": 0.09 * normalization_factor,
            "2021-W27_2021-07-01T12:00_2021-07-02T12:00_00002.wav": 0.3 * normalization_factor,
            "2021-W29_2021-07-21T12:00_2021-07-21T12:00_00001.wav": 0.3 * normalization_factor,
        }
        for filename, expected_value in expected_values.items():
            data, output_rate = sf.read(os.path.join(temp_dir, filename))
            assert output_rate == sample_rate, (filename, output_rate)
            assert np.allclose(data, expected_value, atol=1e-6), (filename, data)

    print("PASS: total, anchored weekly, fortnightly, and four-week mixes contain expected sums")


def test_time_span_mixes():
    """Verify full-span, half, quarter, and eighth mix outputs."""
    sample_rate = 8000
    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = os.path.join(temp_dir, "wavs")
        os.makedirs(audio_path)
        for day in range(1, 10):
            filename = f"CATA01_01{day:02d}21-000000.wav"
            samples = np.full((8, 1), day / 10)
            sf.write(
                os.path.join(audio_path, filename),
                samples,
                sample_rate,
                subtype="PCM_24",
            )

        with patch.object(sf, "read", wraps=sf.read) as read_audio:
            mix_audio_directory_by_time_span(audio_path, temp_dir)
            assert read_audio.call_count == len(range(1, 10)), read_audio.call_count

        expected_values = {
            "full_2021-01-01T00:00_2021-01-09T00:00_00009.wav": 0.45,
            "half01_2021-01-01T00:00_2021-01-04T00:00_00004.wav": 0.10,
            "half02_2021-01-05T00:00_2021-01-09T00:00_00005.wav": 0.35,
            "quarter01_2021-01-01T00:00_2021-01-02T00:00_00002.wav": 0.03,
            "quarter02_2021-01-03T00:00_2021-01-04T00:00_00002.wav": 0.07,
            "quarter03_2021-01-05T00:00_2021-01-06T00:00_00002.wav": 0.11,
            "quarter04_2021-01-07T00:00_2021-01-09T00:00_00003.wav": 0.24,
            "eighth01_2021-01-01T00:00_2021-01-01T00:00_00001.wav": 0.01,
            "eighth02_2021-01-02T00:00_2021-01-02T00:00_00001.wav": 0.02,
            "eighth03_2021-01-03T00:00_2021-01-03T00:00_00001.wav": 0.03,
            "eighth04_2021-01-04T00:00_2021-01-04T00:00_00001.wav": 0.04,
            "eighth05_2021-01-05T00:00_2021-01-05T00:00_00001.wav": 0.05,
            "eighth06_2021-01-06T00:00_2021-01-06T00:00_00001.wav": 0.06,
            "eighth07_2021-01-07T00:00_2021-01-07T00:00_00001.wav": 0.07,
            "eighth08_2021-01-08T00:00_2021-01-09T00:00_00002.wav": 0.17,
        }
        actual_outputs = {
            filename
            for filename in os.listdir(temp_dir)
            if filename.endswith(".wav")
        }
        assert actual_outputs == set(expected_values), actual_outputs
        normalization_factor = 1.0 / 4.5
        _assert_output_metadata(
            temp_dir,
            set(expected_values),
            normalization_factor,
        )
        for filename, expected_value in expected_values.items():
            data, output_rate = sf.read(os.path.join(temp_dir, filename))
            assert output_rate == sample_rate, (filename, output_rate)
            assert np.allclose(
                data,
                expected_value * 10 * normalization_factor,
                atol=1e-6,
            ), (filename, data)

    print("PASS: full-span, half, quarter, and eighth mixes contain expected sums")


def main():
    test_four_week_and_weekly_mixes()
    test_time_span_mixes()
    mix_audio_directory_by_time_span('2022_CATA_01_US/wavs')
    #mix_audio_directory('2021_CATA_01_US/wavs/test')



if __name__ == "__main__":
    main()
