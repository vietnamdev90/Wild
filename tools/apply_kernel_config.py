#!/usr/bin/env python3
"""Apply and verify a strict Kconfig fragment against a generated .config."""

import argparse
import re
import sys
from pathlib import Path

SYMBOL = r"CONFIG_[A-Za-z0-9_]+"
ASSIGNMENT = re.compile(rf'^({SYMBOL})=(y|m|n|-?[0-9]+|0[xX][0-9a-fA-F]+|"(?:[^"\\]|\\.)*")$')
DISABLED = re.compile(rf'^# ({SYMBOL}) is not set$')
CURRENT_ASSIGNMENT = re.compile(rf'^({SYMBOL})=(.*)$')


def parse_fragment(path):
    options = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        disabled = DISABLED.fullmatch(line)
        assignment = ASSIGNMENT.fullmatch(line)
        if disabled:
            name, value = disabled.group(1), "n"
        elif assignment:
            name, value = assignment.groups()
        elif line.startswith("#"):
            continue
        else:
            raise ValueError(f"{path}:{number}: invalid Kconfig line: {line}")
        if name in options:
            raise ValueError(f"{path}:{number}: duplicate option {name}")
        options[name] = value
    return options


def read_config(path):
    options = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        disabled = DISABLED.fullmatch(line)
        assignment = CURRENT_ASSIGNMENT.fullmatch(line)
        if disabled:
            options[disabled.group(1)] = "n"
        elif assignment:
            options[assignment.group(1)] = assignment.group(2)
    return options


def apply(path, overrides):
    if not overrides:
        print("config.txt contains no active options; keeping generated .config")
        return
    remaining = []
    for line in path.read_text(encoding="utf-8").splitlines():
        disabled = DISABLED.fullmatch(line)
        assignment = CURRENT_ASSIGNMENT.fullmatch(line)
        name = disabled.group(1) if disabled else assignment.group(1) if assignment else None
        if name not in overrides:
            remaining.append(line)
    remaining.append("# User overrides from config.txt")
    for name, value in overrides.items():
        remaining.append(f"# {name} is not set" if value == "n" else f"{name}={value}")
    path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    print(f"Applied {len(overrides)} Kconfig override(s) from config.txt")


def verify(path, overrides):
    if not overrides:
        print("No active config.txt overrides to verify")
        return True
    actual = read_config(path)
    failures = []
    for name, wanted in overrides.items():
        got = actual.get(name)
        if wanted == "n" and got is None:
            # Kconfig may omit a disabled symbol with unmet dependencies.
            continue
        if got != wanted:
            failures.append(f"{name}: requested {wanted!r}, final {got if got is not None else '<missing>'!r}")
    if failures:
        for failure in failures:
            print(f"::error::{failure}", file=sys.stderr)
        return False
    print(f"Verified {len(overrides)} Kconfig override(s) after olddefconfig/syncconfig")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("apply", "verify"))
    parser.add_argument("--fragment", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        options = parse_fragment(args.fragment)
        if not args.config.is_file():
            raise ValueError(f"kernel .config missing: {args.config}")
        if args.mode == "apply":
            apply(args.config, options)
        elif not verify(args.config, options):
            return 1
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
