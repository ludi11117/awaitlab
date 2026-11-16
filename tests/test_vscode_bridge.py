import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]
EXTENSION=ROOT/'extensions/vscode'
BAD='def read(value):\n    if value is None:\n        return None\n    if value is None:\n        return 1\n    return value\n'


class EditorBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable,'-B',str(EXTENSION/'build_engine.py')],capture_output=True,check=True)

    def analyze(self,source,filename='unsaved.py'):
        result=subprocess.run([sys.executable,'-I','-S','-B',str(EXTENSION/'bridge.py')],
            input=json.dumps({'text':source,'filename':filename}).encode('utf-8'),capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        return json.loads(result.stdout)

    def test_buffer_is_used_without_reading_or_executing_named_file(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as directory:
            root=Path(directory);target=root/'case.py';marker=root/'executed'
            target.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n',encoding='utf-8')
            result=self.analyze("raise RuntimeError('must not execute')\n"+BAD,str(target))
            self.assertEqual(len(result['findings']),1);self.assertFalse(marker.exists())
            self.assertIn('raise RuntimeError',result['patched'])

    def test_utf16_header_range_preserves_unicode_and_emoji(self):
        source=BAD.replace('value','参数').replace('    if 参数 is None:\n        return 1','    if 参数 is None:  # 🙂\n        return 1')
        result=self.analyze(source);finding=result['findings'][0]
        header=source.splitlines()[3]
        self.assertEqual(finding['character'],4)
        self.assertEqual(finding['endCharacter'],len(header.encode('utf-16-le'))//2)

    def test_syntax_errors_are_structured(self):
        result=self.analyze('def broken(:\n')
        self.assertEqual(result['errors'][0]['line'],0);self.assertEqual(result['findings'],[])

    def test_reasoned_ignore_does_not_propose_a_fix(self):
        source=BAD.replace('    if value is None:\n        return 1',
            '    if value is None:  # awaitlab: ignore[ALD001] -- historical contract\n        return 1')
        result=self.analyze(source)
        self.assertEqual(result['findings'],[]);self.assertEqual(result['patched'],source)

    def test_invalid_ignore_is_an_error(self):
        source=BAD.replace('    if value is None:\n        return 1','    if value is None:  # awaitlab: ignore[ALD001]\n        return 1')
        self.assertEqual(len(self.analyze(source)['errors']),1)

    def test_crlf_buffer_stays_crlf(self):
        result=self.analyze(BAD.replace('\n','\r\n'))
        self.assertNotIn('return 1',result['patched'])
        self.assertNotIn('\n',result['patched'].replace('\r\n',''))


if __name__=='__main__':unittest.main()
