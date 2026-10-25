"""Static, deliberately broad field-name evidence and documentation claims."""
import ast
import json
import os
import re
from pathlib import Path

from . import __version__

RULES = {"input": "documented-input-field-unread", "output": "documented-output-field-unwritten"}


def context(text):
    matches = list(re.finditer(r"\b(input|output)\b", text, re.I))
    return matches[-1].group(1).lower() if matches else None


def claims(text):
    """Yield (kind, field, opening line); window wins over heading."""
    lines = text.splitlines()
    heading = None
    i = 0
    while i < len(lines):
        line = lines[i]
        atx = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if atx:
            heading = atx.group(1)
        elif i + 1 < len(lines) and line.strip() and re.match(r"^ {0,3}(?:=+|-+)\s*$", lines[i + 1]):
            heading = line
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not fence:
            i += 1
            continue
        marker, info = fence.groups()
        start = i
        kind = next((context(lines[j]) for j in range(i - 1, max(-1, i - 6), -1) if context(lines[j])), None)
        kind = kind or context(heading or "")
        i += 1
        body = []
        while i < len(lines) and not re.match(r"^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}\s*$", lines[i]):
            body.append(lines[i])
            i += 1
        closed = i < len(lines)
        i += 1
        if not closed or not kind or info.strip().lower() not in ("json", "jsonl"):
            continue
        try:
            objects = ([json.loads(s) for s in body if s.strip()] if info.strip().lower() == "jsonl" else [json.loads("\n".join(body))])
            if not all(isinstance(obj, dict) for obj in objects):
                continue
        except (ValueError, TypeError):
            continue
        for obj in objects:
            for field in obj:
                yield kind, field, start + 1


def evidence(root):
    reads, writes = set(), set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("tests", "__pycache__") and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if not name.endswith(".py") or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or path.is_symlink():
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError):
                continue
            for node in ast.walk(tree):
                key = None
                if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                    key = node.slice
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("get", "pop", "setdefault") and node.args:
                    key = node.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    reads.add(key.value)
                if isinstance(node, ast.Dict):
                    writes.update(k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
    return reads, writes


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("path must be an existing directory")
    docs = []
    if (root / "README.md").is_file() and not (root / "README.md").is_symlink():
        docs.append(root / "README.md")
    if (root / "docs").is_dir() and not (root / "docs").is_symlink():
        for directory, dirs, names in os.walk(root / "docs", followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            docs.extend(Path(directory) / n for n in sorted(names) if n.endswith(".md") and not (Path(directory) / n).is_symlink())
    read, write = evidence(root)
    findings = []
    verified = {"input": [], "output": []}
    seen = set()
    for doc in docs:
        for kind, field, line in claims(doc.read_text(encoding="utf-8")):
            if (kind, field) in seen:
                continue
            seen.add((kind, field))
            if field in (read if kind == "input" else write):
                verified[kind].append(field)
            elif RULES[kind] not in ignore:
                findings.append(dict(severity="HIGH", rule=RULES[kind], file=doc.relative_to(root).as_posix(), line=line, field=field))
    return dict(version=__version__, path=str(root), findings=findings, verified_fields={k: sorted(v) for k, v in verified.items()})
