import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from awaitlab.code_audit import audit_path,run_cli
from awaitlab.code_audit_report import write_audit_report


class AuditOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'case.py'
        self.original=b'def read(value):\n    return value\n';self.source.write_bytes(self.original)

    def test_cli_failed_replace_preserves_each_previous_output(self):
        for option,suffix in (('output','.json'),('patch','.patch'),('html','.html')):
            with self.subTest(option=option):
                destination=self.root/('previous'+suffix);destination.write_bytes(b'previous complete result')
                with patch('os.replace',side_effect=PermissionError('destination busy')),contextlib.redirect_stdout(io.StringIO()):
                    code=run_cli(self.source,**{option:str(destination)})
                self.assertEqual(code,2)
                self.assertEqual(destination.read_bytes(),b'previous complete result')
                self.assertFalse(list(self.root.glob('*.tmp')))
                self.assertEqual(self.source.read_bytes(),self.original)

    def test_library_html_failed_replace_preserves_previous_report(self):
        report=audit_path(self.source);destination=self.root/'report.html';destination.write_bytes(b'previous report')
        with patch('os.replace',side_effect=PermissionError('busy')):
            with self.assertRaises(PermissionError):write_audit_report(report,destination)
        self.assertEqual(destination.read_bytes(),b'previous report')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_mid_write_failure_does_not_truncate_previous_json(self):
        destination=self.root/'report.json';destination.write_bytes(b'previous complete JSON')
        real_fdopen=os.fdopen
        class FullDisk:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):return self
            def __exit__(self,*args):self.stream.close()
            def write(self,text):
                self.stream.write(text[:12])
                raise OSError('simulated disk full after partial write')
        def failing_open(*args,**kwargs):return FullDisk(real_fdopen(*args,**kwargs))
        with patch('os.fdopen',side_effect=failing_open),contextlib.redirect_stdout(io.StringIO()):
            code=run_cli(self.source,output=str(destination))
        self.assertEqual(code,2);self.assertEqual(destination.read_bytes(),b'previous complete JSON')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_success_replaces_existing_utf8_report_and_cleans_temporary_files(self):
        destination=self.root/'中文 report.html';destination.write_bytes(b'old')
        write_audit_report(audit_path(self.source),destination)
        content=destination.read_text(encoding='utf-8')
        self.assertIn('防御代码审查',content)
        self.assertFalse(list(self.root.glob('*.tmp')))


if __name__=='__main__':unittest.main()
