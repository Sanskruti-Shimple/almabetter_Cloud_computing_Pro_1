"""Batch aggregation for the JSON event archive, using Apache Spark."""

import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Archive directory or Spark-readable URI")
    parser.add_argument("--output", required=True, help="Output directory or Spark-writable URI")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("streamify-music-event-rollup").getOrCreate()
    try:
        events = spark.read.option("recursiveFileLookup", "true").json(args.input)
        if not {"event_type", "track_id"}.issubset(events.columns):
            raise ValueError("Input archive must contain event_type and track_id fields")
        result = events.groupBy("track_id", "event_type").agg(count("*").alias("event_count"))
        result.write.mode("overwrite").parquet(args.output)
        result.show(20, truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
