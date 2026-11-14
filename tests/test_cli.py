import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CLITests(unittest.TestCase):
    def setUp(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def run_cli(self,*args):
        return subprocess.run([sys.executable,'-m','awaitlab','demo',*args],capture_output=True,encoding='utf-8',
            env={**os.environ,'PYTHONUTF8':'1'},timeout=20)

    def test_output_html_cannot_overwrite_itself_with_json(self):
        path=self.root/'existing.html';path.write_text('keep previous report',encoding='utf-8')
        result=self.run_cli('--output',str(path))
        self.assertEqual(result.returncode,2)
        self.assertIn('--output must end in .json',result.stderr)
        self.assertEqual(path.read_text(encoding='utf-8'),'keep previous report')

    def test_invalid_settings_fail_before_workload(self):
        path=self.root/'never.json'
        result=self.run_cli('--blocks','1','--output',str(path))
        self.assertEqual(result.returncode,2)
        self.assertFalse(path.exists());self.assertFalse(path.with_suffix('.checkpoint.json').exists())

    def test_resume_mismatch_exits_clearly_and_keeps_old_complete_files(self):
        path=self.root/'old.json';path.write_text('{"previous":"complete"}',encoding='utf-8')
        html=path.with_suffix('.html');html.write_text('previous HTML',encoding='utf-8')
        checkpoint=path.with_suffix('.checkpoint.json');checkpoint.write_text(json.dumps({'identity':{}}),encoding='utf-8')
        result=self.run_cli('--output',str(path),'--resume')
        self.assertEqual(result.returncode,1)
        self.assertIn('Checkpoint identity differs',result.stderr)
        self.assertIn('上一次完整数据未替换',result.stderr)
        self.assertNotIn('Traceback',result.stderr)
        self.assertEqual(json.loads(path.read_text())['previous'],'complete')
        self.assertEqual(html.read_text(),'previous HTML')
        self.assertEqual(json.loads(checkpoint.read_text()),{'identity':{}})

    def test_completed_measurement_resumes_after_html_save_failure(self):
        path=self.root/'recover.json';html=path.with_suffix('.html')
        # A directory in the HTML destination makes replacement fail while the
        # independently saved JSON and completed checkpoint remain recoverable.
        html.mkdir()
        args=('--scenario','sqlite','--blocks','2','--requests','2','--concurrency','1','--output',str(path))
        failed=self.run_cli(*args)
        self.assertEqual(failed.returncode,1,failed.stderr)
        self.assertIn('测量已完成，但保存报告失败',failed.stderr)
        before=json.loads(path.read_text(encoding='utf-8'))
        checkpoint=json.loads(path.with_suffix('.checkpoint.json').read_text(encoding='utf-8'))
        self.assertEqual(checkpoint['status'],'complete')
        self.assertTrue(all(c['output_equivalence'] for c in before['comparisons']))
        html.rmdir()  # only the empty directory created above, within this D: temp
        resumed=self.run_cli(*args,'--resume')
        self.assertEqual(resumed.returncode,0,resumed.stderr)
        after=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(after['run']['resumed_pairs'],4)
        self.assertEqual(before['comparisons'],after['comparisons'])
        self.assertEqual(before['run']['started_at'],after['run']['started_at'])
        self.assertNotIn('[1/',resumed.stdout)
        self.assertIn('function coverageView',html.read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
