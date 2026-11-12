import argparse
import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from audio_metadata import timestamp_for_file


AUDIO_EXTENSIONS = {".flac", ".wav"}
SHARED_COLUMNS = (
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "seconds",
    "raw_seconds",
    "seconds_to_next",
    "day_of_week",
    "day_of_week_str",
    "timestamp",
    "file_path",
)
CSV_COLUMNS = SHARED_COLUMNS
EVERY_DAY_COLUMNS = SHARED_COLUMNS


def _audio_rows(audio_directory):
    audio_directory = Path(audio_directory)
    if not audio_directory.is_dir():
        raise NotADirectoryError(f"Audio directory does not exist: {audio_directory}")

    return [
        (timestamp_for_file(path), path.name)
        for path in audio_directory.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]


def _timestamp_row(timestamp, file_path=None, seconds_to_next="None"):
    row = {
        "timestamp": timestamp.isoformat(),
        "seconds_to_next": seconds_to_next,
        "year": timestamp.year,
        "month": f"{timestamp.month:02d}",
        "day": f"{timestamp.day:02d}",
        "hour": f"{timestamp.hour:02d}",
        "minute": f"{timestamp.minute:02d}",
        "seconds": f"{timestamp.second:02d}",
        "raw_seconds": int(
            timestamp.replace(tzinfo=ZoneInfo("America/Denver")).timestamp()
        ),
        "day_of_week": f"{(timestamp.weekday() + 1) % 7:02d}",
        "day_of_week_str": timestamp.strftime("%A"),
    }
    if file_path is not None:
        row["file_path"] = file_path
    return row


def _year_for_audio_rows(audio_rows, audio_directory):
    years = {timestamp.year for timestamp, _ in audio_rows}
    if len(years) > 1:
        raise ValueError(
            f"Audio files in {audio_directory} span multiple years: "
            f"{', '.join(map(str, sorted(years)))}"
        )
    if not years:
        raise ValueError(f"No WAV or FLAC audio files found in {audio_directory}")
    return next(iter(years))


def create_audio_csv(audio_directory):
    audio_directory = Path(audio_directory)
    audio_rows = _audio_rows(audio_directory)
    if audio_rows:
        _year_for_audio_rows(audio_rows, audio_directory)

    audio_rows.sort(key=lambda row: (row[0], row[1]))

    output_file = Path(__file__).resolve().parent / f"{audio_directory.name}.csv"

    with output_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for index, (timestamp, file_path) in enumerate(audio_rows):
            seconds_to_next = (
                int((audio_rows[index + 1][0] - timestamp).total_seconds())
                if index + 1 < len(audio_rows)
                else "None"
            )
            writer.writerow(
                _timestamp_row(timestamp, file_path, seconds_to_next)
            )

    return output_file


def create_every_day_csv(audio_directory):
    audio_directory = Path(audio_directory)
    audio_rows = _audio_rows(audio_directory)
    year = _year_for_audio_rows(audio_rows, audio_directory)
    output_file = (
        Path(__file__).resolve().parent
        / f"{audio_directory.name}_every_day.csv"
    )

    with output_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EVERY_DAY_COLUMNS)
        writer.writeheader()
        day = date(year, 1, 1)
        while day.year == year:
            timestamp = datetime.combine(day, time.min)
            next_day = day + timedelta(days=1)
            seconds_to_next = (
                int(
                    (
                        datetime.combine(next_day, time.min) - timestamp
                    ).total_seconds()
                )
                if next_day.year == year
                else "None"
            )
            writer.writerow(
                _timestamp_row(
                    timestamp,
                    file_path="None",
                    seconds_to_next=seconds_to_next,
                )
            )
            day += timedelta(days=1)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Create a CSV index of audio files and timestamps in their names."
    )
    parser.add_argument(
        "audio_directory",
        type=Path,
        help="Directory to search for WAV and FLAC files",
    )
    args = parser.parse_args()

    output_file = create_audio_csv(args.audio_directory)
    print(f"Wrote audio timestamp CSV: {output_file}")
    every_day_file = create_every_day_csv(args.audio_directory)
    print(f"Wrote daily timestamp CSV: {every_day_file}")


if __name__ == "__main__":
    main()
