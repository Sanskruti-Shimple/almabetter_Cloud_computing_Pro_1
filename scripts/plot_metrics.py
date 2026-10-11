"""Plot Locust's *_stats_history.csv output without inventing benchmark data."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="Locust *_stats_history.csv file")
    parser.add_argument("--output", type=Path, default=Path("performance-metrics.png"))
    args = parser.parse_args()

    if not args.csv_file.is_file():
        raise FileNotFoundError(f"Locust history CSV not found: {args.csv_file}")
    data = pd.read_csv(args.csv_file)
    time_column = "Timestamp" if "Timestamp" in data.columns else "Date"
    required = {time_column, "Requests/s", "Failures/s", "95%", "User Count"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Locust history CSV is missing columns: {', '.join(sorted(missing))}")

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    axes[0].plot(data[time_column], data["Requests/s"], label="Requests per second")
    axes[0].plot(data[time_column], data["Failures/s"], label="Failures per second")
    axes[0].set_ylabel("Throughput")
    axes[0].legend()
    axes[1].plot(data[time_column], data["95%"], color="darkorange")
    axes[1].set_ylabel("95th percentile latency (ms)")
    axes[2].plot(data[time_column], data["User Count"], color="seagreen")
    axes[2].set_ylabel("Concurrent users")
    axes[2].set_xlabel("Locust timestamp")
    fig.suptitle("Measured Streamify load test")
    fig.tight_layout()
    fig.savefig(args.output, dpi=160)
    print(f"Saved graph using {len(data)} measured rows to {args.output}")


if __name__ == "__main__":
    main()
