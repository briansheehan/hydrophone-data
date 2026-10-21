# Auto generated code originating from this google query:
# https://www.google.com/search?q=python+sum+thousands+of+audio+files+without+clipping+with+64-bit+math&sxsrf=APpeQntPYCR3SHNzHzGXOQNZs_5251pSkw%3A1791904986724
# Added to using Co-pilot in VSCODE
import os
import re
import tempfile
from datetime import datetime, timedelta

import numpy as np
import soundfile as sf


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
        f"_{first_timestamp:%m%d%y-%H%M%S}"
        f"_{last_timestamp:%m%d%y-%H%M%S}"
    )


def sum_audio_files(file_paths, output_path, normalization_factor=None):
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

    # 4. Prevent clipping by normalizing the final mix
    # Find the absolute peak amplitude across all channels
    peak = np.max(np.abs(master_buffer))

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
    master_buffer *= normalization_factor

    # 5. Export back to disk (e.g., 24-bit PCM WAV)
    sf.write(output_path, master_buffer, sample_rate, subtype='PCM_24')
    #sf.write(output_path, master_buffer, sample_rate, format='WAV', subtype='64 bit float')
    print(f"Successfully saved combined mix to: {output_path}")
    return normalization_factor

def mix_audio_directory(audio_path, output_path):
    audio_files = [
        os.path.join(audio_path, filename)
        for filename in os.listdir(audio_path)
        if filename.endswith(".wav")
    ]
    if not audio_files:
        sum_audio_files(audio_files, output_path)
        return

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

    output_root, output_extension = os.path.splitext(output_path)
    dated_output_path = (
        f"{output_root}{timestamp_range_suffix(audio_files)}{output_extension}"
    )
    normalization_factor = sum_audio_files(audio_files, dated_output_path)
    for period, period_files in sorted(files_by_four_week_period.items()):
        sum_audio_files(
            period_files,
            f"{output_root}_{period}{timestamp_range_suffix(period_files)}{output_extension}",
            normalization_factor,
        )
    for fortnight, fortnight_files in sorted(files_by_fortnightly_period.items()):
        sum_audio_files(
            fortnight_files,
            f"{output_root}_{fortnight}{timestamp_range_suffix(fortnight_files)}{output_extension}",
            normalization_factor,
        )
    for week, week_files in sorted(files_by_week.items()):
        sum_audio_files(
            week_files,
            f"{output_root}_{week}{timestamp_range_suffix(week_files)}{output_extension}",
            normalization_factor,
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

        output_path = os.path.join(temp_dir, "master_output.wav")
        mix_audio_directory(audio_path, output_path)

        expected_outputs = {
            "master_output_123120-120000_080121-120000.wav",
            "master_output_2020-4W01_123120-120000_010721-120000.wav",
            "master_output_2021-4W07_070121-120000_070221-120000.wav",
            "master_output_2020-2W01_123120-120000_010721-120000.wav",
            "master_output_2021-2W14_070121-120000_070221-120000.wav",
            "master_output_2021-2W15_072121-120000_072121-120000.wav",
            "master_output_2020-W01_123120-120000_010721-115959.wav",
            "master_output_2021-W02_010721-120000_010721-120000.wav",
            "master_output_2021-W27_070121-120000_070221-120000.wav",
            "master_output_2021-W29_072121-120000_072121-120000.wav",
        }
        actual_outputs = {
            filename
            for filename in os.listdir(temp_dir)
            if filename.startswith("master_output") and filename.endswith(".wav")
        }
        assert actual_outputs == expected_outputs, actual_outputs

        normalization_factor = 1.0 / 1.35
        expected_values = {
            "master_output_123120-120000_080121-120000.wav": 1.0,
            "master_output_2020-4W01_123120-120000_010721-120000.wav": 0.35 * normalization_factor,
            "master_output_2021-4W07_070121-120000_070221-120000.wav": 0.3 * normalization_factor,
            "master_output_2020-2W01_123120-120000_010721-120000.wav": 0.35 * normalization_factor,
            "master_output_2021-2W14_070121-120000_070221-120000.wav": 0.3 * normalization_factor,
            "master_output_2021-2W15_072121-120000_072121-120000.wav": 0.3 * normalization_factor,
            "master_output_2020-W01_123120-120000_010721-115959.wav": 0.26 * normalization_factor,
            "master_output_2021-W02_010721-120000_010721-120000.wav": 0.09 * normalization_factor,
            "master_output_2021-W27_070121-120000_070221-120000.wav": 0.3 * normalization_factor,
            "master_output_2021-W29_072121-120000_072121-120000.wav": 0.3 * normalization_factor,
        }
        for filename, expected_value in expected_values.items():
            data, output_rate = sf.read(os.path.join(temp_dir, filename))
            assert output_rate == sample_rate, (filename, output_rate)
            assert np.allclose(data, expected_value, atol=1e-6), (filename, data)

    print("PASS: total, anchored weekly, fortnightly, and four-week mixes contain expected sums")


def main():
    test_four_week_and_weekly_mixes()
    #mix_audio_directory('2021_CATA_01_US/wavs', "summed.wav")



if __name__ == "__main__":
    main()
