from pathlib import Path
import tempfile
import textwrap
import unittest

from awaitlab.code_audit import audit_path,audit_source


class AuditPatchTests(unittest.TestCase):
    def scan(self,source):return audit_source(textwrap.dedent(source).lstrip(),'patches.py')

    def test_live_branch_retains_header_leading_and_trailing_comments(self):
        findings,patched=self.scan('''
            def read(value):
                if value is None:
                    return None
                if value is not None:  # already checked
                    # keep business explanation
                    return value
                    # keep trailing explanation
        ''')
        self.assertTrue(findings[0]['patch_available'])
        for comment in ('# already checked','# keep business explanation','# keep trailing explanation'):
            self.assertIn('    '+comment,patched)
        self.assertNotIn('if value is not None:',patched)

    def test_rejected_edit_does_not_cancel_an_independent_patch(self):
        source='''
            def blocked(value):
                if value is not None:
                    if value is None:
                        return 1

            def useful(value):
                if value is None:
                    return None
                if value is None:
                    return 'dead'
                return value
        '''
        findings,patched=self.scan(source)
        self.assertEqual([item['patch_available'] for item in findings],[False,True])
        self.assertNotIn("return 'dead'",patched)
        self.assertIn('if value is None:\n            return 1',patched)

    def test_false_if_keeps_else_and_its_comments(self):
        source='''
            def read(value):
                if value is None:
                    return None
                if value is None:  # repeated guard
                    return 'dead'
                else:  # reachable branch
                    # original explanation
                    return {'value':value}
        '''
        findings,patched=self.scan(source)
        self.assertTrue(findings[0]['patch_available'])
        self.assertNotIn('else:',patched)
        for comment in ('# repeated guard','# reachable branch','# original explanation'):self.assertIn(comment,patched)
        before={};after={};exec(textwrap.dedent(source),before);exec(patched,after)
        for value in (None,0,False,'',[],{'a':1}):self.assertEqual(before['read'](value),after['read'](value))

    def test_true_if_removes_plain_else(self):
        findings,patched=self.scan('''
            def read(value):
                if value is None:
                    return None
                if value is not None:
                    return value
                else:
                    return 'dead'


            def another():
                return 2
        ''')
        self.assertTrue(findings[0]['patch_available'])
        self.assertNotIn('else:',patched)
        self.assertNotIn("return 'dead'",patched)
        self.assertIn('return value\n\n\ndef another',patched)

    def test_discarded_bindings_comments_and_elif_stay_manual(self):
        for dead in ('stored=1\n        return stored','# keep this rationale\n        return 1',
                     'yield 1'):
            source=f'def read(value):\n    if value is None:\n        return None\n    if value is not None:\n        return value\n    else:\n        {dead}\n'
            findings,patched=audit_source(source)
            self.assertFalse(findings[0]['patch_available'])
            self.assertEqual(patched,source)
        source='def read(value):\n    if value is None:\n        return None\n    if value is None:\n        return 1\n    elif value is True:\n        return 2\n    return value\n'
        findings,patched=audit_source(source)
        self.assertFalse(findings[0]['patch_available']);self.assertEqual(patched,source)

    def test_hash_in_dead_string_is_not_a_comment(self):
        findings,patched=self.scan('''
            def read(value):
                if value is None:
                    return None
                if value is None:
                    return '# not a comment'
                return value
        ''')
        self.assertTrue(findings[0]['patch_available'])
        self.assertNotIn('not a comment',patched)

    def test_unrelated_docstring_change_does_not_cancel_safe_patch(self):
        source='''
            def blocked(value):
                if value is None or value is not None:
                    "not a docstring"
                return 1

            def useful(value):
                if value is None:
                    return None
                if value is not None:
                    return value
        '''
        findings,patched=self.scan(source)
        self.assertEqual([item['patch_available'] for item in findings],[False,True])
        self.assertIn('文档字符串',findings[0]['patch_note'])
        self.assertNotIn('    if value is not None:\n        return value',patched)

    def test_latin1_keeps_diagnostics_but_does_not_propose_utf8_patch(self):
        source='# coding: latin-1\ndef read(value):\n    if value is None:\n        return None\n    if value is None:\n        return "caf\xe9"\n    return value\n'
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as directory:
            path=Path(directory)/'case.py';path.write_bytes(source.encode('latin-1'))
            report=audit_path(path)
            self.assertEqual(report['errors'],[])
            self.assertEqual(len(report['findings']),1)
            self.assertFalse(report['findings'][0]['patch_available']);self.assertEqual(report['patch'],'')


if __name__=='__main__':unittest.main()
