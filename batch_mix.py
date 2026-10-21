# Auto generated code originating from this google query:
# https://www.google.com/search?q=python+sum+thousands+of+audio+files+without+clipping+with+64-bit+math&sxsrf=APpeQntPYCR3SHNzHzGXOQNZs_5251pSkw%3A1791904986724
# Added to using Co-pilot in VSCODE
import os
import re
import tempfile
from datetime import datetime

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


def iso_week_for_file(path):
    iso_year, iso_week, _ = timestamp_for_file(path).isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def four_week_period_for_file(path):
    iso_year, iso_week, _ = timestamp_for_file(path).isocalendar()
    period = min((iso_week - 1) // 4 + 1, 13)
    return f"{iso_year}-4W{period:02d}"


def fortnightly_period_for_file(path):
    iso_year, iso_week, _ = timestamp_for_file(path).isocalendar()
    period = min((iso_week - 1) // 2 + 1, 27)
    return f"{iso_year}-2W{period:02d}"


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

    files_by_four_week_period = {}
    files_by_fortnightly_period = {}
    files_by_week = {}
    for path in audio_files:
        period = four_week_period_for_file(path)
        files_by_four_week_period.setdefault(period, []).append(path)
        fortnight = fortnightly_period_for_file(path)
        files_by_fortnightly_period.setdefault(fortnight, []).append(path)
        week = iso_week_for_file(path)
        files_by_week.setdefault(week, []).append(path)

    first_date = min(timestamp_for_file(path).date() for path in audio_files)
    last_date = max(timestamp_for_file(path).date() for path in audio_files)
    output_root, output_extension = os.path.splitext(output_path)
    dated_output_path = (
        f"{output_root}_{first_date.isoformat()}_{last_date.isoformat()}"
        f"{output_extension}"
    )
    normalization_factor = sum_audio_files(audio_files, dated_output_path)
    for period, period_files in sorted(files_by_four_week_period.items()):
        sum_audio_files(
            period_files,
            f"{output_root}_{period}{output_extension}",
            normalization_factor,
        )
    for fortnight, fortnight_files in sorted(files_by_fortnightly_period.items()):
        sum_audio_files(
            fortnight_files,
            f"{output_root}_{fortnight}{output_extension}",
            normalization_factor,
        )
    for week, week_files in sorted(files_by_week.items()):
        sum_audio_files(
            week_files,
            f"{output_root}_{week}{output_extension}",
            normalization_factor,
        )


def test_four_week_and_weekly_mixes():
    """Verify total, fortnightly, four-week, and ISO-week mix outputs."""
    sample_rate = 8000
    test_files = {
        "CATA01_070121-120000.wav": 0.2,
        "CATA01_070221-120000.wav": 0.1,
        "CATA01_072121-120000.wav": 0.3,
        "CATA01_080121-120000.wav": 0.4,
        "CATA01_123120-120000.wav": 0.05,
        "CATA01_010121-120000.wav": 0.06,
        "CATA01_010421-120000.wav": 0.07,
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
            "master_output_2020-12-31_2021-08-01.wav",
            "master_output_2021-4W07.wav",
            "master_output_2021-4W08.wav",
            "master_output_2020-4W13.wav",
            "master_output_2021-4W01.wav",
            "master_output_2021-2W01.wav",
            "master_output_2021-2W13.wav",
            "master_output_2021-2W15.wav",
            "master_output_2020-2W27.wav",
            "master_output_2021-W26.wav",
            "master_output_2021-W29.wav",
            "master_output_2021-W30.wav",
            "master_output_2020-W53.wav",
            "master_output_2021-W01.wav",
        }
        actual_outputs = {
            filename
            for filename in os.listdir(temp_dir)
            if filename.startswith("master_output") and filename.endswith(".wav")
        }
        assert actual_outputs == expected_outputs, actual_outputs

        normalization_factor = 1.0 / 1.18
        expected_values = {
            "master_output_2020-12-31_2021-08-01.wav": 1.0,
            "master_output_2021-4W07.wav": 0.3 * normalization_factor,
            "master_output_2021-4W08.wav": 0.7 * normalization_factor,
            "master_output_2020-4W13.wav": 0.11 * normalization_factor,
            "master_output_2021-4W01.wav": 0.07 * normalization_factor,
            "master_output_2021-2W01.wav": 0.07 * normalization_factor,
            "master_output_2021-2W13.wav": 0.3 * normalization_factor,
            "master_output_2021-2W15.wav": 0.7 * normalization_factor,
            "master_output_2020-2W27.wav": 0.11 * normalization_factor,
            "master_output_2021-W26.wav": 0.3 * normalization_factor,
            "master_output_2021-W29.wav": 0.3 * normalization_factor,
            "master_output_2021-W30.wav": 0.4 * normalization_factor,
            "master_output_2020-W53.wav": 0.11 * normalization_factor,
            "master_output_2021-W01.wav": 0.07 * normalization_factor,
        }
        for filename, expected_value in expected_values.items():
            data, output_rate = sf.read(os.path.join(temp_dir, filename))
            assert output_rate == sample_rate, (filename, output_rate)
            assert np.allclose(data, expected_value, atol=1e-6), (filename, data)

    print("PASS: total, fortnightly, four-week, and ISO-week mixes contain expected sums")


def main():
    test_four_week_and_weekly_mixes()
    mix_audio_directory('wavs/', "summed.wav")



if __name__ == "__main__":
    main()
