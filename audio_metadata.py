import os
import re
from datetime import datetime


def timestamp_for_file(path):
    match = re.search(
        r"(?<!\d)(\d{6}-\d{6})(?!\d)",
        os.path.basename(path),
    )
    if match is None:
        raise ValueError(f"No MMDDYY-HHMMSS timestamp found in filename: {path}")

    try:
        return datetime.strptime(match.group(1), "%m%d%y-%H%M%S")
    except ValueError as error:
        raise ValueError(f"Invalid timestamp in filename: {path}") from error
