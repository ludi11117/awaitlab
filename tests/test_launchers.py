"""Exercise real cmd routing; only GUI opening and pause are substituted."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='nt','Windows cmd launchers')
class LauncherTests(unittest.TestCase):
    def run_launcher(self,name,*,existing=False,fail_scenario=''):
        temp_root=Path('D:/CodexWork/temp/awaitlab');temp_root.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=temp_root);self.addCleanup(temp.cleanup)
        base=Path(temp.name);project=base/'项目 & launcher space';project.mkdir()
        caller=base/'caller space';caller.mkdir();(caller/'temp').mkdir()
        source=(ROOT/name).read_text(encoding='utf-8')
        lines=[];open_count=0;pause_count=0
        for line in source.splitlines():
            if line.lower().startswith('start "" '):
                target=line[len('start "" '):]
                lines.append(f'>> "%~dp0opened.log" echo {target}');open_count+=1
            elif line.lower()=='pause':lines.append('rem UI pause suppressed in launcher test');pause_count+=1
            else:lines.append(line)
        self.assertEqual(open_count,1);self.assertEqual(pause_count,1)
        launcher=project/name;launcher.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\r\n')
        package=project/'awaitlab';package.mkdir();(package/'__init__.py').write_text('',encoding='utf-8')
        (package/'__main__.py').write_text('''import json,os,sys
from pathlib import Path
root=Path.cwd();args=sys.argv[1:];scenario=args[args.index('--scenario')+1]
with (root/'sdk.log').open('a',encoding='utf-8') as f:
 f.write(json.dumps({'args':args,'cwd':str(root),'env':{k:os.environ.get(k) for k in ['TEMP','TMP','PYTHONUTF8','PYTHONDONTWRITEBYTECODE']}})+'\\n')
if scenario==os.environ.get('AWAITLAB_TEST_FAIL_SCENARIO'):raise SystemExit(9)
target=root/args[args.index('--output')+1];target.parent.mkdir(parents=True,exist_ok=True)
target.write_text('{}',encoding='utf-8');target.with_suffix('.html').write_text('new '+scenario,encoding='utf-8')
''',encoding='utf-8')
        if existing:
            (project/'artifacts').mkdir();(project/'artifacts/sqlite-latest.html').write_text('old report',encoding='utf-8')
        observer=base/'observe.py'
        observer.write_text('''import json,os
from pathlib import Path
Path('after.json').write_text(json.dumps({'cwd':str(Path.cwd()),'env':{k:os.environ.get(k) for k in ['TEMP','TMP','PYTHONUTF8','PYTHONDONTWRITEBYTECODE']}}),encoding='utf-8')
''',encoding='utf-8')
        wrapper=caller/'invoke.cmd'
        wrapper.write_text(f'@echo off\ncall "{launcher}"\nset "LAUNCHER_CODE=%errorlevel%"\npython -B "{observer}"\nexit /b %LAUNCHER_CODE%\n',encoding='utf-8',newline='\r\n')
        original_env={'TEMP':str(caller/'temp'),'TMP':str(caller/'temp'),'PYTHONUTF8':'0','PYTHONDONTWRITEBYTECODE':'1'}
        env={**os.environ,**original_env,'PYTHONPATH':'','AWAITLAB_TEST_FAIL_SCENARIO':fail_scenario}
        run=subprocess.run([os.environ['COMSPEC'],'/d','/c','call',str(wrapper)],cwd=caller,env=env,
            capture_output=True,encoding='utf-8',errors='replace',timeout=15)
        # A leaking cwd can cause the observer to write in the project instead.
        after_path=caller/'after.json'
        self.assertTrue(after_path.exists(),f'Caller cwd was not restored; {run.stdout} {run.stderr}')
        after=json.loads(after_path.read_text(encoding='utf-8'))
        self.assertEqual(after['cwd'],str(caller));self.assertEqual(after['env'],original_env)
        log=project/'sdk.log'
        calls=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
        for call in calls:
            self.assertEqual(call['cwd'],str(project))
            self.assertEqual(call['env'],{'TEMP':'D:\\CodexWork\\temp\\awaitlab','TMP':'D:\\CodexWork\\temp\\awaitlab',
                'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'})
        opened=project/'opened.log'
        targets=[line.strip().strip('"') for line in opened.read_text(encoding='utf-8').splitlines()] if opened.exists() else []
        return run,calls,targets,project

    def test_cached_start_does_not_measure_or_leak_environment(self):
        run,calls,targets,project=self.run_launcher('Start-AwaitLab.cmd',existing=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(calls,[])
        self.assertEqual(targets,[str(project/'artifacts/sqlite-latest.html')])

    def test_missing_report_uses_same_sqlite_target(self):
        run,calls,targets,project=self.run_launcher('Start-AwaitLab.cmd')
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual([c['args'] for c in calls],[['demo','--scenario','sqlite','--output','artifacts/sqlite-latest.json']])
        self.assertEqual(targets,[str(project/'artifacts/sqlite-latest.html')])

    def test_sqlite_rerun_always_measures(self):
        run,calls,targets,project=self.run_launcher('Run-SQLite-Experiments.cmd',existing=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(len(calls),1)
        self.assertEqual((project/'artifacts/sqlite-latest.html').read_text(),'new sqlite')
        self.assertEqual(targets,[str(project/'artifacts/sqlite-latest.html')])

    def test_sqlite_failure_keeps_old_html_and_does_not_open_it(self):
        run,calls,targets,project=self.run_launcher('Run-SQLite-Experiments.cmd',existing=True,fail_scenario='sqlite')
        self.assertEqual(run.returncode,1,run.stdout+run.stderr);self.assertEqual(len(calls),1);self.assertEqual(targets,[])
        self.assertEqual((project/'artifacts/sqlite-latest.html').read_text(),'old report')

    def test_mechanism_rerun_runs_both_scenarios(self):
        run,calls,targets,project=self.run_launcher('Rerun-Experiments.cmd')
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual([c['args'][2] for c in calls],['parallel','pool'])
        self.assertEqual(targets,[str(project/'artifacts/parallel-latest.html')])

    def test_second_mechanism_failure_does_not_open_partial_result(self):
        run,calls,targets,project=self.run_launcher('Rerun-Experiments.cmd',fail_scenario='pool')
        self.assertEqual(run.returncode,1,run.stdout+run.stderr)
        self.assertEqual([c['args'][2] for c in calls],['parallel','pool']);self.assertEqual(targets,[])
        self.assertEqual((project/'artifacts/parallel-latest.html').read_text(),'new parallel')


if __name__=='__main__':unittest.main()
