import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from awaitlab.code_audit import audit_path,audit_source


class CodeAuditTests(unittest.TestCase):
    def scan(self,source):
        return audit_source(textwrap.dedent(source).lstrip(),'case.py')

    def test_early_exit_explains_and_removes_dead_guard(self):
        findings,patched=self.scan('''
            def read(value):
                if value is None:
                    return 'missing'
                if value is None:
                    return 'unreachable'
                return value
        ''')
        self.assertEqual(len(findings),1)
        self.assertIn('第 2 行',findings[0]['evidence'])
        self.assertTrue(findings[0]['patch_available'])
        self.assertNotIn('unreachable',patched)

    def test_nested_true_guard_patch_preserves_results(self):
        source='''
            def read(value):
                if value is not None:
                    if value is not None:
                        return {'value': value}
                return None
        '''
        findings,patched=self.scan(source)
        before={};after={}
        exec(textwrap.dedent(source),before);exec(patched,after)
        for value in (None,0,'',[],{'a':1}):self.assertEqual(before['read'](value),after['read'](value))
        self.assertTrue(findings[0]['patch_available'])

    def test_call_assignment_and_await_stop_path_facts(self):
        for statement in ('value=None','other=1','touch()','await touch()','value.attr','assert value'):
            with self.subTest(statement=statement):
                findings,_=self.scan(f'''
                    async def read(value):
                        if value is None:
                            return None
                        {statement}
                        if value is None:
                            return 'maybe'
                ''')
                self.assertEqual(findings,[])

    def test_globals_nonlocals_and_free_names_are_not_inferred(self):
        for prefix in ('global value','nonlocal value','pass'):
            source=f'''def outer():
    value=1
    def read():
        {prefix}
        if value is None:
            return None
        if value is None:
            return 1
    return read
'''
            findings,_=audit_source(source)
            self.assertEqual(findings,[])

    def test_branch_merge_keeps_only_facts_on_continuing_paths(self):
        findings,_=self.scan('''
            def read(value,flag):
                if value is None:
                    if flag:
                        return 0
                if value is None:
                    return 1
                return value
        ''')
        self.assertEqual(findings,[])
        findings,_=self.scan('''
            def read(value):
                if value is None:
                    raise ValueError('missing')
                else:
                    pass
                if value is not None:
                    return value
        ''')
        self.assertEqual(len(findings),1)

    def test_silent_broad_exception_is_review_only(self):
        for clause,result in (('Exception','pass'),('BaseException','return None'),('','return 0')):
            findings,patched=self.scan(f'''
                def read():
                    try:
                        return run()
                    except {clause}:
                        {result}
            ''')
            self.assertEqual(len(findings),1)
            self.assertEqual(findings[0]['confidence'],'needs_review')
            self.assertFalse(findings[0]['patch_available'])
        findings,_=self.scan('''
            def read():
                try:
                    return run()
                except ValueError:
                    return None
                except Exception:
                    raise
        ''')
        self.assertEqual(findings,[])

    def test_empty_parent_and_multiline_string_do_not_get_patches(self):
        source='def read(value):\n    if value is not None:\n        if value is None:\n            return 1\n'
        findings,patched=audit_source(source)
        self.assertEqual(patched,source)
        self.assertFalse(findings[0]['patch_available'])
        for prefix in ('','f'):
            source=f'def read(value):\n    if value is not None:\n        if value is not None:\n            return {prefix}"""first\n            keep these spaces"""\n'
            findings,patched=audit_source(source)
            self.assertEqual(patched,source)
            self.assertIn('多行字符串',findings[0]['patch_note'])

    def test_dead_binding_and_yield_preserve_function_semantics(self):
        for body in ('missing=1','yield 1','import math','del value','match value:\n            case captured:\n                pass'):
            with self.subTest(body=body):
                source=f'def read(value):\n    if value is None:\n        return None\n    if value is None:\n        {body}\n    return value\n'
                findings,patched=audit_source(source)
                self.assertEqual(patched,source)
                self.assertFalse(findings[0]['patch_available'])
                before={};after={};exec(source,before);exec(patched,after)
                self.assertEqual(inspect.isgeneratorfunction(before['read']),inspect.isgeneratorfunction(after['read']))

    def test_directory_skips_dependencies_and_does_not_import_target(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as folder:
            root=Path(folder);(root/'node_modules').mkdir()
            (root/'node_modules'/'bad.py').write_text('invalid syntax!!',encoding='utf-8')
            source="raise AssertionError('must not execute')\ndef read(v):\n    if v is None:\n        return 0\n    if v is None:\n        return 1\n    return v\n"
            target=root/'case.py';target.write_text(source,encoding='utf-8')
            report=audit_path(root)
            self.assertEqual(report['files_scanned'],1)
            self.assertEqual(len(report['findings']),1)
            self.assertEqual(report['errors'],[])
            self.assertEqual(target.read_text(encoding='utf-8'),source)
            self.assertIn('--- a/case.py',report['patch'])

    def test_cli_check_json_patch_and_parse_error(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as folder:
            root=Path(folder);target=root/'case.py'
            target.write_text('def read(v):\n    if v is None:\n        return 0\n    if v is None:\n        return 1\n    return v',encoding='utf-8')
            report=root/'audit.json';patch=root/'audit.patch'
            command=[sys.executable,'-m','awaitlab','audit',str(root),'--check','--output',str(report),'--patch',str(patch)]
            result=subprocess.run(command,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,1,result.stderr)
            data=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(data['findings'][0]['rule'],'ALD001')
            self.assertIn('\\ No newline at end of file',patch.read_text(encoding='utf-8'))
            applied=subprocess.run(['git','apply','--check',str(patch)],cwd=root,capture_output=True,encoding='utf-8')
            self.assertEqual(applied.returncode,0,applied.stderr)
            (root/'bad.py').write_text('def nope(',encoding='utf-8')
            result=subprocess.run(command,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertEqual(len(json.loads(report.read_text(encoding='utf-8'))['errors']),1)


if __name__=='__main__':unittest.main()
