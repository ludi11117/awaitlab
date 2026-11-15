import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from awaitlab.code_audit import audit_path
from awaitlab.code_audit_report import render_audit_report


GUARD='def read(value):\n    if value is None:\n        return None\n    if value is None:\n        return 1\n    return value\n'


class AuditPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def write(self,name,source):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(source,encoding='utf-8');return path

    def test_exclusion_prunes_unparseable_directory_and_records_decision(self):
        self.write('app.py',GUARD);self.write('generated/broken.py','not valid python!!')
        report=audit_path(self.root,exclude=['generated/**'])
        self.assertEqual(report['files_scanned'],1);self.assertEqual(report['errors'],[])
        self.assertEqual(report['excluded_paths'],['generated/'])
        self.assertEqual(len(report['findings']),1)

    def test_windows_separator_and_file_patterns_are_scan_root_relative(self):
        self.write('src/app.py',GUARD);self.write('src/legacy.py',GUARD)
        report=audit_path(self.root,exclude=['src\\legacy.py'])
        self.assertEqual(report['files_scanned'],1)
        self.assertEqual(report['excluded_paths'],['src/legacy.py'])
        self.assertTrue(report['findings'][0]['path'].endswith('src/app.py'))

    def test_explicit_file_can_be_excluded(self):
        path=self.write('case.py',GUARD)
        report=audit_path(path,exclude=['case.py'])
        self.assertEqual(report['files_scanned'],0)
        self.assertEqual(report['excluded_paths'],['case.py'])
        self.assertEqual(report['findings'],[])

    def test_ignored_guard_is_not_patched_and_other_guard_remains_active(self):
        source='''def read(value):
    if value is None:
        return None
    if value is None:  # awaitlab: ignore[ALD001] -- retained for branch instrumentation
        return 'retained'
    if value is None:
        return 'active'
    return value
'''
        self.write('case.py',source);report=audit_path(self.root)
        self.assertEqual(len(report['findings']),1);self.assertEqual(len(report['ignored_findings']),1)
        ignored=report['ignored_findings'][0]
        self.assertEqual(ignored['suppression_reason'],'retained for branch instrumentation')
        self.assertFalse(ignored['patch_available'])
        self.assertNotIn("-        return 'retained'",report['patch'])
        self.assertIn("-        return 'active'",report['patch'])

    def test_review_ignore_reason_is_visible_and_html_escaped(self):
        self.write('case.py','''def optional(loader):
    try:
        return loader()
    except Exception:  # awaitlab: ignore[ALD002] -- optional plugin <script> remains disabled
        return None
''')
        report=audit_path(self.root)
        self.assertEqual(report['findings'],[]);self.assertEqual(len(report['ignored_findings']),1)
        html=render_audit_report(report)
        self.assertIn('扫描范围与保留决定',html)
        self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html)
        self.assertIn('当前没有未忽略的规则提示',html)

    def test_missing_reason_or_unknown_rule_makes_scan_incomplete(self):
        for comment in ('# awaitlab: ignore[ALD001]','# awaitlab: ignore[ALD999] -- unknown',
                        '# awaitlab: ignore[ALD001,] -- empty rule'):
            with self.subTest(comment=comment):
                self.write('case.py',GUARD.replace('    if value is None:\n        return 1',f'    if value is None: {comment}\n        return 1'))
                report=audit_path(self.root)
                self.assertEqual(len(report['errors']),1)
                self.assertIn('扫描不完整',render_audit_report(report))
                result=subprocess.run([sys.executable,'-m','awaitlab','audit',str(self.root),'--check'],capture_output=True,encoding='utf-8')
                self.assertEqual(result.returncode,2,result.stderr)

    def test_directive_inside_string_cannot_suppress_a_finding(self):
        self.write('case.py','note="# awaitlab: ignore[ALD001] -- not a comment"\n'+GUARD)
        report=audit_path(self.root)
        self.assertEqual(len(report['findings']),1);self.assertEqual(report['ignored_findings'],[])

    def test_cli_repeatable_excludes_and_ignored_only_check_succeeds(self):
        self.write('app.py','''def optional(loader):
    try:
        return loader()
    except Exception:  # awaitlab: ignore[ALD002] -- optional plugin fallback is intended
        return None
''')
        self.write('generated/bad.py','bad syntax!!');self.write('legacy/old.py',GUARD)
        target=self.root/'report.json'
        result=subprocess.run([sys.executable,'-m','awaitlab','audit',str(self.root),'--check',
            '--exclude','generated/**','--exclude','legacy/**','--output',str(target)],capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(report['files_scanned'],1);self.assertEqual(len(report['ignored_findings']),1)
        self.assertEqual(report['excluded_paths'],['generated/','legacy/'])


if __name__=='__main__':unittest.main()
