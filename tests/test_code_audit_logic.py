import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from awaitlab.code_audit import audit_source
from awaitlab.code_audit_report import render_audit_report


class AuditLogicTests(unittest.TestCase):
    def scan(self,source):return audit_source(textwrap.dedent(source).lstrip(),'logic.py')

    def test_or_exit_proves_both_conditions_and_cross_singleton_facts(self):
        findings,patched=self.scan('''
            def read(value,ready):
                if value is None or ready is not True:
                    return None
                if None is value:
                    return 'dead'
                if not (ready is True):
                    return 'dead too'
                return value
        ''')
        self.assertEqual(len(findings),2)
        self.assertTrue(all(f['patch_available'] for f in findings))
        self.assertNotIn('dead',patched)
        self.assertTrue(all(f['related_conditions'] for f in findings))
        findings,_=self.scan('''
            def read(flag):
                if flag is True or flag is False:
                    if flag is None:
                        return 'dead'
                return flag
        ''')
        self.assertEqual(len(findings),1)

    def test_and_failure_and_or_success_do_not_invent_individual_facts(self):
        for source in ('''
            def read(x,y):
                if x is None and y is None:
                    return 0
                if x is None:
                    return 1
                return 2
        ''','''
            def read(x,y):
                if x is None or y is None:
                    if x is None:
                        return 1
                return 2
        '''):
            findings,_=self.scan(source)
            self.assertEqual(findings,[])

    def test_not_and_reversed_boolean_identity(self):
        findings,patched=self.scan('''
            def read(flag):
                if not (True is flag):
                    return 'off'
                if flag is True:
                    return 'on'
        ''')
        self.assertEqual(len(findings),1)
        self.assertTrue(findings[0]['patch_available'])
        self.assertIn("    return 'on'",patched)

    def test_calls_truthiness_and_numeric_equality_are_not_pure_identity_conditions(self):
        for guard in ('x is None or touch()','x is None and x.ready','x','x == None','x is 0'):
            source=f'def read(x):\n    if {guard}:\n        return 0\n    if x is None:\n        return 1\n    return 2\n'
            # Numeric identity is deliberately not recognized; avoid its compile warning here.
            if guard=='x is 0':
                source='def read(x):\n    if x is 0:\n        if x is None:\n            return 1\n    return 2\n'
            with self.subTest(guard=guard):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',SyntaxWarning)
                    findings,_=audit_source(source)
                self.assertEqual(findings,[])

    def test_unbound_local_read_is_not_removed_with_contradictory_condition(self):
        source='def read():\n    if x is None and x is not None:\n        return 1\n    x=2\n    return x\n'
        findings,patched=audit_source(source)
        self.assertEqual(findings,[]);self.assertEqual(patched,source)
        scope={};exec(patched,scope)
        with self.assertRaises(UnboundLocalError):scope['read']()

    def test_first_guard_edits_do_not_create_function_docstrings(self):
        for body in ('if x is None or x is not None:\n        "not a docstring"',
                     'if x is None and x is not None:\n        return 1\n    "not a docstring"'):
            source=f'def read(x):\n    {body}\n    return 2\n'
            findings,patched=audit_source(source)
            self.assertEqual(len(findings),1)
            self.assertEqual(patched,source)
            self.assertFalse(findings[0]['patch_available'])
            self.assertIn('文档字符串',findings[0]['patch_note'])

    def test_finite_runtime_differential_for_compound_guard_patches(self):
        guards=['x is None','x is True','not (x is False)','x is None or y is None',
            'x is not None and y is True','not (x is None or y is False)',
            'x is True or x is False','x is None and x is not None']
        checks=['x is None','x is not None','True is x','not (y is False)',
            'x is None or y is None','x is True and y is not None']
        class IdentityOnly:
            def __bool__(self):raise AssertionError('identity checks must not call __bool__')
            def __eq__(self,other):raise AssertionError('identity checks must not call __eq__')
        values=[None,True,False,0,'',[],IdentityOnly()]
        changed=0
        for guard,check in itertools.product(guards,checks):
            source=f'def read(x,y):\n    if {guard}:\n        return "stop"\n    if {check}:\n        return "match"\n    return "rest"\n'
            _,patched=audit_source(source)
            changed+=patched!=source
            before={};after={};exec(source,before);exec(patched,after)
            for x,y in itertools.product(values,repeat=2):
                self.assertEqual(before['read'](x,y),after['read'](x,y),(guard,check))
        self.assertGreater(changed,10)

    def test_html_escapes_source_paths_errors_and_patch(self):
        payload='<script>alert("test")</script>'
        report={'files_scanned':1,'findings':[{'rule':'ALD002','confidence':'needs_review','path':payload,
            'line':1,'column':1,'message':payload,'evidence':payload,'suggestion':payload,'code':payload,
            'patch_available':False}], 'errors':[{'path':payload,'error':payload}],
            'patch_root':payload,'patch':payload,'scope':payload,'ignored_findings':[],'excluded_paths':[],'source_scope':'worktree'}
        html=render_audit_report(report)
        self.assertNotIn(payload,html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('未完成的扫描',html)
        self.assertNotIn('<script',html)
        report['source_scope']='git_index'
        report['index_snapshot']={'base_head':payload,'selected_blobs':{payload:payload},
            'skipped_nonregular_paths':[payload],'deleted_python_paths':[payload]}
        html=render_audit_report(report)
        self.assertNotIn(payload,html);self.assertIn('&lt;script&gt;',html)

    def test_cli_writes_offline_html_without_changing_source(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as folder:
            root=Path(folder);source=root/'case.py';html=root/'audit.html';data=root/'audit.json'
            text='def read(x):\n    if x is None or x is False:\n        return None\n    if None is x:\n        return 0\n    return x\n'
            source.write_text(text,encoding='utf-8')
            result=subprocess.run([sys.executable,'-m','awaitlab','audit',str(source),'--html',str(html),'--output',str(data)],
                capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_text(encoding='utf-8'),text)
            self.assertIn('判断依据',html.read_text(encoding='utf-8'))
            self.assertIn('补丁建议',html.read_text(encoding='utf-8'))
            self.assertEqual(len(json.loads(data.read_text(encoding='utf-8'))['findings']),1)


if __name__=='__main__':unittest.main()
