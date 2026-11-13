import argparse
import csv
from datetime import date, timedelta
from zoneinfo import ZoneInfo

def main():
    parser = argparse.ArgumentParser(
        description="Calculate daily sunrise and sunset times for one or more years."
    )
    parser.add_argument(
        "years",
        nargs="+",
        help="one or more four-digit years",
    )
    args = parser.parse_args()

    years = []
    for year in args.years:
        if len(year) != 4 or not year.isascii() or not year.isdigit():
            parser.error(f"{year!r} is not a four-digit year")
        if int(year) == 0:
            parser.error("year must be between 0001 and 9999")
        years.append((year, int(year)))

    from astral import LocationInfo
    from astral.sun import sun

    # Set up Colorado reference location (McCoy) and Mountain Timezone
    city = LocationInfo(
        name="McCoy",
        region="Colorado, USA",
        timezone="US/Mountain",
        latitude=39.9144,
        longitude=-106.7258
    )

    tz = ZoneInfo(city.timezone)
    for year_text, year in years:
        current_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        output_file = f"{city.name}_sunrise_sunset_{year_text}.csv"
        rows = []

        while current_date <= end_date:
            s = sun(city.observer, date=current_date, tzinfo=tz)

            sunrise = s["sunrise"]
            sunset = s["sunset"]
            daylight = sunset - sunrise

            rows.append({
                "sunrise": sunrise.isoformat(),
                "sunset": sunset.isoformat(),
                "seconds_of_light": daylight.total_seconds(),
            })

            current_date += timedelta(days=1)

        with open(output_file, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=rows[0].keys()
            )
            writer.writeheader()
            writer.writerows(rows)

        print(f"Successfully saved {len(rows)} days of data to {output_file}")


if __name__ == "__main__":
    main()