# schema-claim-audit

Version 0.1.0. A Python >=3.9, standard-library-only static auditor of documented JSON field names against Python source. No runtime dependencies. It never executes scanned code, accesses the network, or opens `.env` files. Only Markdown documentation and Python source are read.

## Usage

```sh
pip install schema-claim-audit
schema-claim-audit ./project
python -m schema_claim_audit ./project --verbose
schema-claim-audit ./project --json --fail-on HIGH
schema-claim-audit ./project --ignore documented-input-field-unread,documented-output-field-unwritten
schema-claim-audit --version
```

The path defaults to the current directory. Exit codes: 0 PASS, 2 FAIL, 1 usage/input error. The default failure threshold is MEDIUM; HIGH and MEDIUM findings fail. `--fail-on HIGH` still displays MEDIUM findings but only HIGH fails. Both current rules are HIGH. `--ignore RULE,...` removes those findings entirely.

Human findings use `SEVERITY rule file:line field`; paths are relative to the scanned root and lines identify the opening fence. A final PASS/FAIL line reports the result. `--verbose` adds `verified: input <name>` and `verified: output <name>` lines.

`--json` emits one JSON object with `version`, `path` (the supplied scan directory), `findings`, and `verified_fields`. Each finding has `severity`, `rule`, `file`, `line`, and `field`. `verified_fields` has `input` and `output` arrays, each sorted and deduplicated. Ignored missing fields are not verified. `--version` prints `0.1.0`.

## Rules

- `documented-input-field-unread` (HIGH): a documented input field lacks read evidence.
- `documented-output-field-unwritten` (HIGH): a documented output field lacks write evidence.

Claims come only from fenced `json` or `jsonl` blocks (case insensitive) in root `README.md` and recursively in `docs/*.md`. Top-level object keys are claims. JSONL unions keys of all nonempty object lines. Duplicates are deduplicated separately for input and output; the first occurrence supplies the location.

Context uses whole words input/output, case insensitive. Check the five preceding lines from nearest to farthest first, then the nearest preceding ATX or Setext heading. If both words occur on one line, the last word wins. A heading in that window participates like any other line. Blocks with neither context are ignored.

Source evidence comes from AST parsing of Python files recursively, including `examples/`. Excluded: `tests/` directories, hidden directories, `__pycache__/`, `test_*.py`, `*_test.py`, and `conftest.py`. Symlink files and directories are skipped.

Input evidence is string-literal subscript reads and first positional string arguments to `.get`, `.pop`, or `.setdefault`. Chained subscripts count each literal key. Assignment/deletion targets do not count as reads. Output evidence is string keys of any dictionary literal anywhere in scanned source, including returns and arguments to `json.dump`/`json.dumps`. This is deliberately broad: any dictionary literal can be a shape under construction. Input and output evidence are asymmetric: dictionary literals alone do not verify input; subscript reads alone do not verify output.

## Limitations

This is static pattern matching, not semantic judgement or a guarantee of behavior. It does not track variable types, data flow, reachability, actual serialization, dynamic keys, or whether a method belongs to a dictionary. Unrelated code can supply matching evidence.

Only top-level documented keys count; nested documented keys, prose backtick names, non-JSON blocks, and non-Python source are out of scope. Examples outside input/output context are not claims. Malformed JSON/JSONL blocks (including non-object records) are silently skipped as a whole. Unparseable Python files are silently skipped. Files must be UTF-8; other read failures produce input errors.

There are no reverse-direction rules: undocumented code keys are not findings because internal keys would be noisy. A project with no claims passes: silence is not a lie. With no Python source, every documented field is a finding because evidence is empty.

## Differentiation

- **jsonschema / pydantic** validate data against schemas at runtime. This tool compares docs against code statically without data.
- **schemathesis** tests live APIs at runtime; this tool runs offline without calling an API.
- **dataclasses-json / marshmallow** are serialization frameworks. This tool is schema-agnostic and counts dictionary-key patterns without requiring a framework.
- **readme-claim-audit** checks install, flag, link and version claims, rather than JSON field names.
- **api-claim-audit** checks documented importable symbols and signatures, rather than data-field names.
- **config-claim-audit** checks documented default values, rather than field names.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python -m build
```
