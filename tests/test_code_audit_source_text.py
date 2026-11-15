from pathlib import Path
import subprocess
import tempfile
import unittest

from awaitlab.code_audit import audit_path,audit_source


def fixture(payload,ending='\n'):
    return (f"banner='left{payload}right'\n"
        'def read(value):\n'
        '    if value is None:\n'
        '        return None\n'
        '    if value is not None:\n'
        '        return value\n').replace('\n',ending)


class AuditSourceTextTests(unittest.TestCase):
    def test_string_separator_characters_are_not_source_line_breaks(self):
        for codepoint in (0x0b,0x0c,0x1c,0x1d,0x1e,0x85,0x2028,0x2029):
            with self.subTest(codepoint=codepoint):
                source=fixture(chr(codepoint));findings,patched=audit_source(source)
                self.assertEqual(len(findings),1)
                self.assertEqual(findings[0]['line'],5)
                self.assertTrue(findings[0]['patch_available'])
                before={};after={};exec(source,before);exec(patched,after)
                self.assertEqual(before['banner'],after['banner'])
                self.assertEqual(after['read'](0),0);self.assertIsNone(after['read'](None))

    def test_unicode_identifiers_use_utf8_byte_offsets_for_messages(self):
        source='def 读取(参数):\n    if 参数 is None:\n        return None\n    if 参数 is not None:\n        return 参数\n'
        findings,patched=audit_source(source)
        self.assertEqual(findings[0]['message'],'参数 is not None 在当前路径恒为 True')
        self.assertTrue(findings[0]['patch_available'])
        scope={};exec(patched,scope);self.assertEqual(scope['读取']('原文'),'原文')

    def test_crlf_and_no_final_newline_preserve_payload(self):
        for ending in ('\n','\r\n','\r'):
            source=fixture(chr(0x2028),ending).rstrip('\r\n')
            findings,patched=audit_source(source)
            self.assertTrue(findings[0]['patch_available'])
            before={};after={};exec(source,before);exec(patched,after)
            self.assertEqual(before['banner'],after['banner'])
            self.assertFalse(patched.endswith(('\n','\r')))

    def test_git_patch_applies_with_literal_unicode_separator(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as directory:
            root=Path(directory);target=root/'case.py';source=fixture(chr(0x2028))
            target.write_bytes(source.encode('utf-8'))
            report=audit_path(target)
            self.assertTrue(report['findings'][0]['patch_available'])
            patch=root/'review.patch';patch.write_bytes(report['patch'].encode('utf-8'))
            checked=subprocess.run(['git','apply','--check',str(patch)],cwd=root,capture_output=True,encoding='utf-8')
            self.assertEqual(checked.returncode,0,checked.stderr)
            subprocess.run(['git','apply',str(patch)],cwd=root,capture_output=True,check=True)
            before={};after={};exec(source,before);exec(target.read_bytes(),after)
            self.assertEqual(before['banner'],after['banner'])

    def test_form_feed_indentation_stays_manual(self):
        source='def read(value):\n    if value is None:\n        return None\n \f    if value is not None:\n        return value\n'
        findings,patched=audit_source(source)
        self.assertFalse(findings[0]['patch_available'])
        self.assertEqual(patched,source)


if __name__=='__main__':unittest.main()
