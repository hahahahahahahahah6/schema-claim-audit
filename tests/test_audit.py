import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from schema_claim_audit.audit import audit, claims, evidence, RULES
from schema_claim_audit.cli import main

BASE = Path(__file__).parent / 'fixtures'


class AuditTests(unittest.TestCase):
    def project(self, docs='', source='', name='app.py'):
        tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent.parent / '.tmp')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'README.md').write_text(docs)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        return root

    def test_good(self):
        r = audit(BASE / 'good')
        self.assertEqual(r['findings'], [])
        self.assertEqual(r['verified_fields'], {'input': ['request'], 'output': ['result']})

    def test_bad(self):
        r = audit(BASE / 'bad')
        self.assertEqual([f['rule'] for f in r['findings']], list(RULES.values()))
        self.assertEqual([f['line'] for f in r['findings']], [2, 6])

    def test_env_never_opened(self):
        original = io.open
        def guarded(path, *a, **kw):
            self.assertNotEqual(Path(path).name, '.env')
            return original(path, *a, **kw)
        with patch('io.open', guarded):
            result = audit(BASE / 'bad')
        self.assertNotIn('ENV_MUST_NEVER_BE_OPENED_MARKER', json.dumps(result))

    def test_docs_recursive(self):
        root = self.project()
        (root / 'docs' / 'nested').mkdir(parents=True)
        (root / 'docs' / 'nested' / 'guide.md').write_text('# Input\n```json\n{"x":1}\n```')
        self.assertEqual(audit(root)['findings'][0]['file'], 'docs/nested/guide.md')

    def test_other_markdown_ignored(self):
        root = self.project()
        (root / 'OTHER.md').write_text('# Input\n```json\n{"x":1}\n```')
        self.assertEqual(audit(root)['findings'], [])

    def test_dedup_per_kind(self):
        root = self.project('# Input\n```json\n{"x":1}\n```\n```json\n{"x":2}\n```\n# Output\n```json\n{"x":3}\n```')
        self.assertEqual(len(audit(root)['findings']), 2)

    def test_verified_sorted(self):
        root = self.project('# Input\n```json\n{"z":1,"a":2}\n```', 'd.get("z"); d.get("a")')
        self.assertEqual(audit(root)['verified_fields']['input'], ['a', 'z'])

    def test_asymmetry_input(self):
        self.assertEqual(len(audit(self.project('# Input\n```json\n{"x":1}\n```', '{"x":1}'))['findings']), 1)

    def test_asymmetry_output(self):
        self.assertEqual(len(audit(self.project('# Output\n```json\n{"x":1}\n```', 'd["x"]'))['findings']), 1)

    def test_no_source(self):
        root = self.project('# Input\n```json\n{"x":1,"y":2}\n```')
        (root / 'app.py').unlink()
        self.assertEqual(len(audit(root)['findings']), 2)

    def test_no_claims(self):
        self.assertEqual(audit(self.project('', 'd["internal"]'))['findings'], [])

    def test_missing_root(self):
        with self.assertRaises(ValueError):
            audit(BASE / 'missing')


def claim_test(text, expected):
    def test(self):
        self.assertEqual([(k, f) for k, f, _ in claims(text)], expected)
    return test

claim_cases = [
('# Input\n```json\n{"a":1}\n```', [('input','a')]),
('# Output\n```json\n{"a":1}\n```', [('output','a')]),
('Input\n=====\n```json\n{"a":1}\n```', [('input','a')]),
('Output\n------\n```json\n{"a":1}\n```', [('output','a')]),
('Example input record:\n```JSON\n{"a":1}\n```', [('input','a')]),
('Output:\n```JsOnL\n{"a":1}\n\n{"b":2}\n```', [('output','a'),('output','b')]),
('# Input\nOutput record:\n```json\n{"a":1}\n```', [('output','a')]),
('# Output\nInput record:\n```json\n{"a":1}\n```', [('input','a')]),
('# General\n```json\n{"a":1}\n```', []),
('# Input\n```python\n{"a":1}\n```', []),
('# Input\n```json\n{"outer":{"inner":1}}\n```', [('input','outer')]),
('# Input\n```json\ninvalid\n```', []),
('# Input\n```jsonl\n{"a":1}\nbroken\n```', []),
('# Input\n```json\n[1,2]\n```', []),
('# Input\n```jsonl\n{"a":1}\n[]\n```', []),
('# Input\n```json\n{"a":1}\n', []),
('# Input\n~~~json\n{"a":1}\n~~~', [('input','a')]),
('# Input\n````json\n{"a":1}\n`````', [('input','a')]),
('# Input\n```json extra\n{"a":1}\n```', []),
('# Input\n`a`', []),
('# Input\n\n\n\n\n\n\n```json\n{"a":1}\n```', [('input','a')]),
('Input\n\n\n\n\n\n```json\n{"a":1}\n```', []),
('Input\n\n\n\n\n```json\n{"a":1}\n```', [('input','a')]),
('input output\n```json\n{"a":1}\n```', [('output','a')]),
('output input\n```json\n{"a":1}\n```', [('input','a')]),
('# Inputting\n```json\n{"a":1}\n```', []),
('# Input\n```json\n{}\n```', []),
('# Input\n```jsonl\n\n```', []),
('# Input\n```json\n{"a":1,}\n```', []),
('# Input\n```json\nnull\n```', []),
]
for i, (doc, expected) in enumerate(claim_cases):
    setattr(AuditTests, 'test_claim_%02d' % i, claim_test(doc, expected))


def evidence_test(source, name, expected):
    def test(self):
        self.assertEqual(evidence(self.project(source=source, name=name)), expected)
    return test

cases = [
('d["x"]', 'app.py', ({'x'}, set())),
('d["a"]["b"]', 'app.py', ({'a','b'}, set())),
('d.get("x")', 'app.py', ({'x'}, set())),
('d.pop("x")', 'app.py', ({'x'}, set())),
('d.setdefault("x", 1)', 'app.py', ({'x'}, set())),
('{"x": 1}', 'app.py', (set(), {'x'})),
('def f():\n return {"x":1}', 'app.py', (set(), {'x'})),
('json.dumps({"x":1})', 'app.py', (set(), {'x'})),
('{"a":{"b":2}}', 'app.py', (set(), {'a','b'})),
('d["x"] = 2', 'app.py', (set(), set())),
('del d["x"]', 'app.py', (set(), set())),
('d[key]', 'app.py', (set(), set())),
('d.get(key)', 'app.py', (set(), set())),
('d.get()', 'app.py', (set(), set())),
('d.other("x")', 'app.py', (set(), set())),
('{1:2, **other}', 'app.py', (set(), set())),
('invalid !!!', 'app.py', (set(), set())),
('d["x"]', 'tests/helper.py', (set(), set())),
('d["x"]', 'test_app.py', (set(), set())),
('d["x"]', 'app_test.py', (set(), set())),
('d["x"]', 'conftest.py', (set(), set())),
('d["x"]', '.hidden/app.py', (set(), set())),
('d["x"]', '__pycache__/app.py', (set(), set())),
('d["x"]', 'examples/app.py', ({'x'}, set())),
('d["x"]', 'pkg/app.py', ({'x'}, set())),
]
for i, args in enumerate(cases):
    setattr(AuditTests, 'test_evidence_%02d' % i, evidence_test(*args))


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(args)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_good(self):
        self.assertEqual(self.run_cli([str(BASE/'good')])[:2], (0, 'PASS\n'))

    def test_bad(self):
        code, out, _ = self.run_cli([str(BASE/'bad')])
        self.assertEqual(code, 2)
        self.assertIn('HIGH documented-input-field-unread README.md:2 missing_input', out)
        self.assertTrue(out.endswith('FAIL\n'))

    def test_high(self):
        self.assertEqual(self.run_cli([str(BASE/'bad'), '--fail-on', 'HIGH'])[0], 2)

    def test_ignore_both(self):
        self.assertEqual(self.run_cli([str(BASE/'bad'), '--ignore', ','.join(RULES.values())])[0], 0)

    def test_ignore_one(self):
        code, out, _ = self.run_cli([str(BASE/'bad'), '--ignore', RULES['input'], '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(len(json.loads(out)['findings']), 1)

    def test_json(self):
        code, out, _ = self.run_cli([str(BASE/'good'), '--json'])
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertEqual(set(obj), {'version','path','findings','verified_fields'})
        self.assertEqual(obj['verified_fields']['input'], ['request'])

    def test_verbose(self):
        self.assertIn('verified: output result', self.run_cli([str(BASE/'good'), '--verbose'])[1])

    def test_version(self):
        self.assertEqual(self.run_cli(['--version'])[:2], (0, '0.1.0\n'))

    def test_missing(self):
        self.assertEqual(self.run_cli([str(BASE/'missing')])[0], 1)

    def test_invalid_option(self):
        self.assertEqual(self.run_cli(['--unknown'])[0], 1)

    def test_invalid_threshold(self):
        self.assertEqual(self.run_cli(['--fail-on', 'LOW'])[0], 1)


if __name__ == '__main__':
    unittest.main()
