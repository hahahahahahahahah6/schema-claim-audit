"""Command line interface."""
import argparse
import json
import sys
from . import __version__
from .audit import audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, "error: " + message + "\n")


def main(argv=None):
    parser = Parser(description="Audit documented JSON fields against Python source offline.")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--fail-on", choices=("HIGH", "MEDIUM"), default="MEDIUM")
    parser.add_argument("--ignore", default="", metavar="RULE,...")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(args.path, {r.strip() for r in args.ignore.split(",") if r.strip()})
    except (OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1
    failed = any(f["severity"] == "HIGH" or args.fail_on == "MEDIUM" for f in result["findings"])
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        for f in result["findings"]:
            print("{severity} {rule} {file}:{line} {field}".format(**f))
        if args.verbose:
            for kind, fields in result["verified_fields"].items():
                for field in fields:
                    print("verified: {} {}".format(kind, field))
        print("FAIL" if failed else "PASS")
    return 2 if failed else 0
