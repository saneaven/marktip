"""Local performance smoke test with a large mixed Markdown document.

Run after building/installing the package:

    PYTHONPATH=python python scripts/benchmark.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import timeit
import tracemalloc
from collections.abc import Callable

import marktip as tm


LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Praesent vitae augue sed neque efficitur vulputate. "
    "Integer non sem at orci pretium aliquet. "
    "Suspendisse potenti, sed fermentum risus sagittis in. "
    "Curabitur blandit, nibh in dignissim gravida, sapien risus feugiat arcu, "
    "vel pretium erat sem vitae erat. "
)


def lorem_words(repetitions: int) -> str:
    return LOREM * repetitions


def make_fixture(sections: int = 1_200, lorem_repetitions: int = 4) -> str:
    chunks: list[str] = ["# Synthetic Lorem Markdown Corpus\n\n"]
    long_lorem = lorem_words(lorem_repetitions)

    for index in range(sections):
        checked = "x" if index % 2 == 0 else " "
        chunks.append(
            f"## Section {index}: Lorem Throughput\n\n"
            f"{long_lorem}"
            f"This paragraph mixes **bold emphasis {index}**, *italic phrasing*, "
            f"~~deleted context~~, `inline_code_{index}`, "
            f"[reference link](https://example.com/docs/{index}), and <span data-i=\"{index}\">inline HTML</span>.  \n"
            f"It also keeps a hard break before continuing with more prose. {long_lorem}\n\n"
            f"> {long_lorem}"
            f"> Nested quotation with **strong text**, [a citation](https://example.com/cite/{index}), "
            f"> and enough lorem ipsum to look like a real imported document.\n\n"
            f"- [{checked}] Review generated section {index}\n"
            f"- [ ] Normalize serializer output for section {index}\n"
            f"- [ ] Compare parse and serialization latency\n\n"
            f"1. Ordered item alpha for section {index}\n"
            f"2. Ordered item beta with `code` and **marks**\n"
            f"   - Nested bullet carries {long_lorem[:180]}\n\n"
            "| Metric | Value | Notes |\n"
            "| :--- | ---: | :--- |\n"
            f"| section | {index} | lorem table cell with **markdown** and pipes escaped later |\n"
            f"| bytes | {len(long_lorem)} | [source](https://example.com/bench/{index}) |\n\n"
            "```cpp\n"
            f"// synthetic code block for section {index}\n"
            "int accumulate_markdown_nodes(int base) {\n"
            "    int total = base;\n"
            "    for (int i = 0; i < 32; ++i) {\n"
            "        total += i * 3;\n"
            "    }\n"
            "    return total;\n"
            "}\n"
            "```\n\n"
        )

        if index % 10 == 0:
            chunks.append(f"<section data-benchmark=\"{index}\">raw html block</section>\n\n")

    return "".join(chunks)


def count_nodes(node: dict) -> int:
    return 1 + sum(count_nodes(child) for child in node.get("content", []))


def mib(value: int) -> float:
    return value / (1024 * 1024)


def best_seconds(operation: Callable[[], object], repetitions: int) -> float:
    return min(timeit.repeat(operation, number=1, repeat=repetitions))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sections", type=int, default=1_200)
    parser.add_argument("--lorem-repetitions", type=int, default=4)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()

    markdown = make_fixture(args.sections, args.lorem_repetitions)
    input_bytes = len(markdown.encode("utf-8"))
    size_mb = mib(input_bytes)

    doc = tm.from_markdown(markdown)
    parse_seconds = best_seconds(lambda: tm.from_markdown(markdown), args.repetitions)

    ast = doc.to_dict()
    to_dict_seconds = best_seconds(doc.to_dict, args.repetitions)
    node_count = count_nodes(ast)
    from_dict_seconds = {
        level: best_seconds(lambda: tm.from_dict(ast, strict=level), args.repetitions)
        for level in ("off", "content", "exact")
    }

    tracemalloc.start()
    tm.from_markdown(markdown)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    serialized = doc.to_markdown()
    serialize_seconds = best_seconds(doc.to_markdown, args.repetitions)
    output_bytes = len(serialized.encode("utf-8"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as pool:
        threaded_seconds = best_seconds(
            lambda: list(pool.map(tm.from_markdown, [markdown] * args.threads)), args.repetitions
        )

    print(f"sections: {args.sections}")
    print(f"timings: best of {args.repetitions} repetitions")
    print(f"input: {size_mb:.2f} MiB")
    print(f"output: {mib(output_bytes):.2f} MiB")
    print(f"ast nodes: {node_count:,}")
    print(f"markdown -> Document: {size_mb / parse_seconds:.2f} MiB/s ({parse_seconds:.3f}s)")
    print(f"python peak during parse: {peak_bytes / (1024 * 1024):.2f} MiB")
    print(f"Document -> Markdown: {size_mb / serialize_seconds:.2f} MiB/s ({serialize_seconds:.3f}s)")
    print(f"Document -> dict: {node_count / to_dict_seconds:.0f} nodes/s ({to_dict_seconds:.3f}s)")
    for level, seconds in from_dict_seconds.items():
        print(f"dict -> Document (strict={level}): {node_count / seconds:.0f} nodes/s ({seconds:.3f}s)")
    print(f"{args.threads} threaded parses: {(size_mb * args.threads) / threaded_seconds:.2f} MiB/s ({threaded_seconds:.3f}s)")


if __name__ == "__main__":
    main()
