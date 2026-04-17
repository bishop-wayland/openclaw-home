#!/usr/bin/env python3
"""Count word occurrences in a text file."""

import argparse
import re
from collections import Counter
from pathlib import Path


def count_words(text: str) -> Counter:
    """Extract and count words, case-insensitive, ignoring punctuation."""
    words = re.findall(r"\b[a-z']+\b", text.lower())
    return Counter(words)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count word occurrences in a .txt file."
    )
    parser.add_argument("file", type=Path, help="Path to the input .txt file")
    parser.add_argument(
        "-n",
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Show only the top N most common words",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        metavar="N",
        help="Only show words that appear at least N times (default: 1)",
    )
    parser.add_argument(
        "--sort",
        choices=["count", "alpha"],
        default="count",
        help="Sort by frequency (default) or alphabetically",
    )
    args = parser.parse_args()

    if not args.file.exists():
        parser.error(f"File not found: {args.file}")
    if args.file.suffix.lower() != ".txt":
        parser.error(f"Expected a .txt file, got: {args.file.suffix}")

    text = args.file.read_text(encoding="utf-8")
    counts = count_words(text)

    # Filter by minimum count
    filtered = {w: c for w, c in counts.items() if c >= args.min_count}

    # Sort
    if args.sort == "alpha":
        results = sorted(filtered.items(), key=lambda x: x[0])
    else:
        results = sorted(filtered.items(), key=lambda x: (-x[1], x[0]))

    # Limit to top N
    if args.top is not None:
        results = results[: args.top]

    if not results:
        print("No words found matching the given criteria.")
        return

    # Print table
    max_word_len = max(len(w) for w, _ in results)
    col_width = max(max_word_len, 4)
    header = f"{'WORD':<{col_width}}  COUNT"
    print(header)
    print("-" * len(header))
    for word, count in results:
        print(f"{word:<{col_width}}  {count}")

    print(f"\nTotal unique words: {len(counts):,}")
    print(f"Total word tokens:  {sum(counts.values()):,}")


if __name__ == "__main__":
    main()
