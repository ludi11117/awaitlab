import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class VSCodeLauncherTests(unittest.TestCase):
    def test_native_cmd_opens_demo_with_d_drive_profile_and_extensions(self):
        repo=Path(__file__).resolve().parents[1];source=(repo/'Start-AwaitLab-VSCode.cmd').read_bytes()
        self.assertNotIn(b'\n',source.replace(b'\r\n',b''),'Windows entry must use CRLF')
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab',prefix='vscode 启动-') as directory:
            root=Path(directory);script=root/'Start-AwaitLab-VSCode.cmd';script.write_bytes(source)
            examples=root/'examples';examples.mkdir();(examples/'defensive_vscode_sample.py').write_text('value=1\n',encoding='utf-8')
            binary=root/'appdata/Programs/Microsoft VS Code/bin';binary.mkdir(parents=True)
            recorder=root/'record.py';calls=root/'calls.jsonl'
            recorder.write_text('import json,os,sys\nfrom pathlib import Path\nwith Path(os.environ["AWAITLAB_TEST_CALLS"]).open("a",encoding="utf-8") as f:\n f.write(json.dumps({"args":sys.argv[1:],"temp":os.environ["TEMP"]})+"\\n")\n',encoding='utf-8')
            (binary/'code.cmd').write_bytes(f'@echo off\r\n"{sys.executable}" "{recorder}" %*\r\n'.encode('utf-8'))
            env={**os.environ,'LOCALAPPDATA':str(root/'appdata'),'AWAITLAB_TEST_CALLS':str(calls)}
            result=subprocess.run(f'cmd.exe /d /c ""{script}""',cwd=root,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout.decode('utf-8',errors='replace'))
            rows=[json.loads(line) for line in calls.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertEqual(row['temp'],'D:\\CodexWork\\temp\\awaitlab')
                self.assertEqual(row['args'][row['args'].index('--extensions-dir')+1],'D:\\CodexWork\\cache\\awaitlab-vscode-extensions')
            self.assertIn('--install-extension',rows[0]['args']);self.assertIn('--new-window',rows[1]['args'])
            self.assertEqual((root/'artifacts/vscode-demo/review_me.py').read_text(encoding='utf-8'),'value=1\n')


if __name__=='__main__':unittest.main()
