import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from awaitlab.code_audit import AuditRun,audit_path
from awaitlab.code_audit_report import render_audit_report
from awaitlab.git_index import audit_index
from awaitlab.index_apply import apply_index


GOOD='def read(value):\n    return value\n'
BAD='def read(value):\n    if value is None:\n        return None\n    if value is None:\n        return 1\n    return value\n'


class GitAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.hooks=self.root/'empty-hooks';self.hooks.mkdir()
        self.env={**os.environ,'GIT_DIR':str(self.root/'.git'),'GIT_WORK_TREE':str(self.root),
            'GIT_INDEX_FILE':str(self.root/'.git/index'),'GIT_TERMINAL_PROMPT':'0'}
        self.git('init','-q')
        self.git('config','core.autocrlf','false');self.git('config','commit.gpgsign','false')
        self.git('config','core.hooksPath',str(self.hooks))

    def git(self,*args,input=None):
        result=subprocess.run(['git','-C',str(self.root),*args],env=self.env,input=input,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        return result.stdout

    def write(self,name,source):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.encode('utf-8'));return path

    def commit(self):
        self.git('-c','user.name=AwaitLabTest','-c','user.email=test@example.invalid','commit','-qm','fixture')

    def scan(self,target=None,**options):
        with patch.dict(os.environ,self.env):return audit_index(target or self.root,**options)

    def save_report(self,report=None):
        path=self.root/'review.json';path.write_text(json.dumps(report or self.scan()),encoding='utf-8');return path

    def apply(self,path,**options):
        with patch.dict(os.environ,self.env):return apply_index(path,**options)

    def test_new_repository_reads_staged_blob_without_mutating_index(self):
        path=self.write('case.py',BAD);self.git('add','case.py')
        before=(self.root/'.git/index').read_bytes()
        report=self.scan()
        self.assertIsNone(report['index_snapshot']['base_head'])
        self.assertEqual(report['files_scanned'],1);self.assertEqual(len(report['findings']),1)
        self.assertEqual(report['sources']['case.py']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual((self.root/'.git/index').read_bytes(),before)

    def test_unstaged_fix_does_not_hide_staged_problem_and_cached_patch_leaves_worktree(self):
        path=self.write('case.py',GOOD);self.git('add','case.py');self.commit()
        self.write('case.py',BAD);self.git('add','case.py')
        unstaged='# unstaged sentinel\n'+GOOD;self.write('case.py',unstaged)
        report=self.scan()
        self.assertEqual(len(report['findings']),1);self.assertEqual(audit_path(path)['findings'],[])
        self.assertEqual(report['source_scope'],'git_index')
        self.assertEqual(report['sources']['case.py']['git_blob'],self.git('rev-parse',':case.py').decode().strip())
        patch_path=self.root/'review.patch';patch_path.write_bytes(report['patch'].encode('utf-8'))
        self.git('apply','--cached','--check',str(patch_path));self.git('apply','--cached',str(patch_path))
        self.assertEqual(path.read_text(encoding='utf-8'),unstaged)
        self.assertNotIn(b'return 1',self.git('show',':case.py'))
        self.assertEqual(self.scan()['findings'],[])

    def test_untracked_and_only_unstaged_files_are_not_scanned(self):
        self.write('case.py',GOOD);self.git('add','case.py');self.commit()
        self.write('case.py',BAD);self.write('untracked.py',BAD)
        report=self.scan()
        self.assertEqual(report['files_scanned'],0);self.assertEqual(report['findings'],[])

    def test_literal_subdirectory_unicode_filename_and_excludes(self):
        self.write('module[one]/中文 文件.py',BAD);self.write('other.py',BAD);self.git('add','.')
        report=self.scan(self.root/'module[one]')
        self.assertEqual(report['files_scanned'],1)
        self.assertIn('module[one]/中文 文件.py',report['sources'])
        patch_path=self.root/'review.patch';patch_path.write_bytes(report['patch'].encode('utf-8'))
        self.git('apply','--cached','--check',str(patch_path))
        excluded=self.scan(self.root/'module[one]',exclude=['*.py'])
        self.assertEqual(excluded['files_scanned'],0);self.assertEqual(excluded['excluded_paths'],['中文 文件.py'])

    def test_rename_is_scanned_at_new_name_and_delete_is_not_parsed(self):
        self.write('old.py',BAD);self.git('add','old.py');self.commit()
        self.git('mv','old.py','new.py');report=self.scan()
        self.assertEqual(report['files_scanned'],1);self.assertIn('new.py',report['sources'])
        self.assertEqual(report['index_snapshot']['deleted_python_paths'],['old.py'])
        deleted=self.scan(self.root/'old.py')
        self.assertEqual(deleted['files_scanned'],0)
        self.assertEqual(deleted['index_snapshot']['deleted_python_paths'],['old.py'])

    def test_intent_to_add_is_not_a_staged_source(self):
        self.write('case.py',BAD);self.git('add','-N','case.py')
        report=self.scan()
        self.assertEqual(report['files_scanned'],0)
        self.assertEqual(report['findings'],[])

    def test_merge_conflict_reports_one_error_without_selecting_a_side(self):
        self.write('case.py',GOOD);self.git('add','case.py');self.commit()
        base=self.git('rev-parse',':case.py').strip()
        ours=self.git('hash-object','-w','--stdin',input=BAD.encode()).strip()
        theirs=self.git('hash-object','-w','--stdin',input=(BAD+'# theirs\n').encode()).strip()
        rows=b'0 '+b'0'*len(base)+b'\tcase.py\n'+b''.join(b'100644 '+oid+b' '+str(stage).encode()+b'\tcase.py\n'
            for stage,oid in ((1,base),(2,ours),(3,theirs)))
        self.git('update-index','--index-info',input=rows)
        report=self.scan()
        self.assertEqual(report['files_scanned'],0);self.assertEqual(len(report['errors']),1)
        self.assertIn('合并冲突',report['errors'][0]['error'])

    def test_external_diff_and_clean_filter_are_not_executed(self):
        self.write('case.py',BAD);self.git('add','case.py')
        marker=self.root/'helper-executed';helper=self.root/'helper.py'
        helper.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("called")\n',encoding='utf-8')
        command=f'"{Path(sys.executable).as_posix()}" "{helper.as_posix()}"'
        self.git('config','diff.external',command);self.git('config','filter.trap.clean',command)
        self.write('.gitattributes','*.py filter=trap\n')
        report=self.scan()
        self.assertEqual(len(report['findings']),1);self.assertFalse(marker.exists())

    def test_index_change_during_scan_marks_result_incomplete(self):
        self.write('case.py',BAD);self.git('add','case.py');original=AuditRun.add_source
        def mutate(run,*args,**kwargs):
            original(run,*args,**kwargs)
            self.write('case.py',GOOD);self.git('add','case.py')
        with patch.object(AuditRun,'add_source',mutate):report=self.scan()
        self.assertTrue(any('发生变化' in error['error'] for error in report['errors']))

    def test_cli_default_path_exports_snapshot_html(self):
        self.write('case.py',BAD);self.git('add','case.py')
        sdk=Path(__file__).resolve().parents[1]
        env={**self.env,'PYTHONPATH':str(sdk),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        report=self.root/'audit.json';html=self.root/'audit.html'
        result=subprocess.run([sys.executable,'-m','awaitlab','audit','--staged','--check','--output',str(report),'--html',str(html)],
            cwd=self.root,env=env,capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['source_scope'],'git_index')
        text=html.read_text(encoding='utf-8')
        self.assertIn('Git 暂存区快照',text);self.assertIn('python -m awaitlab apply-index',text)
        self.assertIn(self.git('rev-parse',':case.py').decode().strip(),text)

    def test_nonrepo_cli_fails_without_replacing_previous_report(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as directory:
            root=Path(directory);target=root/'audit.json';target.write_text('previous report',encoding='utf-8')
            env={key:value for key,value in os.environ.items() if key not in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE')}
            env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,'-m','awaitlab','audit',str(root),'--staged','--output',str(target)],
                cwd=root,env=env,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertNotIn('Traceback',result.stdout+result.stderr)
            self.assertEqual(target.read_text(encoding='utf-8'),'previous report')

    def test_staged_crlf_source_patch_preserves_index_line_endings(self):
        source=BAD.replace('\n','\r\n');self.write('case.py',source);self.git('add','case.py')
        report=self.scan();path=self.root/'review.patch';path.write_bytes(report['patch'].encode('utf-8'))
        self.git('apply','--cached','--check',str(path));self.git('apply','--cached',str(path))
        patched=self.git('show',':case.py')
        self.assertIn(b'\r\n',patched);self.assertNotIn(b'        return 1',patched)

    def test_staged_cr_only_patch_is_applied_and_verified(self):
        source=BAD.replace('\n','\r');path=self.write('case.py',source);self.git('add','case.py')
        report=self.save_report()
        self.assertEqual(self.apply(report,check=True),1)
        self.assertEqual(self.apply(report),1)
        fixed=self.git('show',':case.py')
        self.assertNotIn(b'\n',fixed);self.assertNotIn(b'return 1',fixed)
        self.assertEqual(path.read_bytes(),source.encode())

    def test_nonregular_index_entry_is_recorded_without_parsing(self):
        oid=self.git('hash-object','-w','--stdin',input=b'other.py').decode().strip()
        self.git('update-index','--add','--cacheinfo',f'120000,{oid},link.py')
        report=self.scan()
        self.assertEqual(report['files_scanned'],0)
        self.assertEqual(report['index_snapshot']['skipped_nonregular_paths'],['link.py'])
        self.assertIn('非普通文件：link.py',render_audit_report(report))

    def test_missing_staged_blob_is_not_reported_as_clean(self):
        oid=self.git('hash-object','--stdin',input=b'x').decode().strip()
        self.git('update-index','--add','--info-only','--cacheinfo',f'100644,{oid},missing.py')
        with self.assertRaisesRegex(ValueError,'暂存对象不可读'):
            self.scan()

    def test_multiple_files_share_one_git_blob_reader_process(self):
        for i in range(4):self.write(f'case{i}.py',BAD)
        self.git('add','.')
        with patch('subprocess.Popen',wraps=subprocess.Popen) as calls:report=self.scan()
        batch_calls=[call for call in calls.call_args_list if 'cat-file' in call.args[0]]
        self.assertEqual(len(batch_calls),1)
        self.assertIn('--batch',batch_calls[0].args[0])
        self.assertEqual(report['files_scanned'],4)

    def test_full_snapshot_verification_rejects_stale_patch_accepted_by_git_context_check(self):
        source='def read(value):\n    if value is None:\n        return None\n'+'    pass\n'*20+\
            '    if value is None:\n        return 1\n    return value\n'
        self.write('case.py',source);self.git('add','case.py');report=self.scan()
        patch_path=self.root/'review.patch';patch_path.write_bytes(report['patch'].encode('utf-8'))
        report_path=self.save_report(report)
        changed=source.replace('if value is None:', 'if value is not None:',1)
        self.write('case.py',changed);self.git('add','case.py')
        result=subprocess.run(['git','-C',str(self.root),'apply','--cached','--check',str(patch_path)],
            env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('index ',report['patch'])
        before=(self.root/'.git/index').read_bytes()
        for check in (True,False):
            with self.assertRaisesRegex(ValueError,'版本或补丁'):
                self.apply(report_path,check=check)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertFalse((self.root/'.git/index.lock').exists())

    def test_sha256_repository_patch_matches_git_object_format(self):
        with tempfile.TemporaryDirectory(dir='D:/CodexWork/temp/awaitlab') as directory:
            root=Path(directory);env={**self.env,'GIT_DIR':str(root/'.git'),
                'GIT_WORK_TREE':str(root),'GIT_INDEX_FILE':str(root/'.git/index')}
            def git(*args):
                result=subprocess.run(['git','-C',str(root),*args],env=env,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
                return result.stdout
            git('init','--object-format=sha256','-q');git('config','core.autocrlf','false')
            git('config','core.hooksPath',str(self.hooks))
            (root/'case.py').write_bytes(BAD.encode());git('add','case.py')
            with patch.dict(os.environ,env):report=audit_index(root)
            self.assertEqual(report['index_snapshot']['object_format'],'sha256')
            self.assertEqual(len(report['sources']['case.py']['git_blob']),64)
            target=root/'review.patch';target.write_bytes(report['patch'].encode('utf-8'))
            git('apply','--cached','--check',str(target))
            report_path=root/'review.json';report_path.write_text(json.dumps(report),encoding='utf-8')
            with patch.dict(os.environ,env):self.assertEqual(apply_index(report_path),1)
            self.assertNotIn(b'return 1',git('show',':case.py'))

    def test_apply_index_check_is_read_only_and_apply_preserves_unstaged_source(self):
        path=self.write('case.py',BAD);self.git('add','case.py');report=self.save_report()
        self.write('case.py','# unstaged sentinel\n'+GOOD)
        source=path.read_bytes();before=(self.root/'.git/index').read_bytes()
        self.assertEqual(self.apply(report,check=True),1)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertFalse((self.root/'.git/index.lock').exists())
        self.assertEqual(self.apply(report),1)
        self.assertEqual(path.read_bytes(),source)
        self.assertNotIn(b'return 1',self.git('show',':case.py'))
        self.assertFalse((self.root/'.git/index.lock').exists())
        with self.assertRaisesRegex(ValueError,'版本或补丁'):self.apply(report)

    def test_tampered_report_patch_hash_version_or_scope_is_rejected(self):
        self.write('case.py',BAD);self.git('add','case.py');report=self.scan()
        before=(self.root/'.git/index').read_bytes()
        for field,value in (('patch',''),('library_version','0.0.0'),('source_scope','worktree'),
                ('errors',[{'path':'case.py','error':'incomplete'}]),('sources',{}),('exclude_patterns',[1])):
            with self.subTest(field=field):
                path=self.save_report({**report,field:value})
                with self.assertRaises(ValueError):self.apply(path)
                self.assertEqual((self.root/'.git/index').read_bytes(),before)

    def test_preexisting_git_lock_is_preserved(self):
        self.write('case.py',BAD);self.git('add','case.py');report=self.save_report()
        lock=self.root/'.git/index.lock';lock.write_bytes(b'other Git operation')
        with self.assertRaisesRegex(ValueError,'被占用'):self.apply(report)
        self.assertEqual(lock.read_bytes(),b'other Git operation')

    def test_result_validation_failure_rolls_back_real_index(self):
        path=self.write('case.py',BAD);self.git('add','case.py');report=self.save_report()
        before=(self.root/'.git/index').read_bytes();source=path.read_bytes()
        with patch('awaitlab.index_apply.verify_result',side_effect=ValueError('result rejected')):
            with self.assertRaisesRegex(ValueError,'result rejected'):self.apply(report)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertEqual(path.read_bytes(),source)
        self.assertFalse((self.root/'.git/index.lock').exists())

    def test_single_file_scope_does_not_expand_to_sibling_files(self):
        self.write('case.py',BAD);self.write('sibling.py',BAD);self.git('add','.')
        sibling=self.git('rev-parse',':sibling.py')
        report=self.save_report(self.scan(self.root/'case.py'))
        self.assertEqual(self.apply(report),1)
        self.assertEqual(self.git('rev-parse',':sibling.py'),sibling)
        self.assertNotIn(b'return 1',self.git('show',':case.py'))

    def test_split_index_and_intent_to_add_survive_application(self):
        self.write('case.py',BAD);self.git('add','case.py')
        self.write('pending.py',GOOD);self.git('add','-N','pending.py')
        self.git('update-index','--split-index')
        report=self.save_report();pending=self.git('ls-files','--debug','pending.py')
        self.assertEqual(self.apply(report),1)
        self.assertEqual(self.git('ls-files','--debug','pending.py'),pending)
        self.assertNotIn(b'return 1',self.git('show',':case.py'))

    def test_active_alternate_index_only_is_updated(self):
        self.write('case.py',GOOD);self.git('add','case.py');before=(self.root/'.git/index').read_bytes()
        alternate=self.root/'alternate-index';alternate.write_bytes(before)
        self.env['GIT_INDEX_FILE']=str(alternate)
        self.write('case.py',BAD);self.git('add','case.py');report=self.save_report()
        self.assertEqual(self.apply(report),1)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertNotIn(b'return 1',self.git('show',':case.py'))

    def test_apply_cli_rejects_invalid_json_without_traceback(self):
        path=self.root/'invalid.json';path.write_text('{broken',encoding='utf-8')
        env={**self.env,'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-m','awaitlab','apply-index',str(path),'--check'],
            cwd=self.root,env=env,capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,2)
        self.assertNotIn('Traceback',result.stdout+result.stderr)

    def test_wrong_temporary_result_hash_cannot_replace_real_index(self):
        from awaitlab.git_index import GitReader
        self.write('case.py',BAD);self.git('add','case.py');report=self.save_report()
        before=(self.root/'.git/index').read_bytes()
        wrong=self.git('hash-object','-w','--stdin',input=GOOD.encode()).decode().strip()
        original=GitReader.read
        def corrupt_result(reader,*args,**options):
            result=original(reader,*args,**options)
            if 'apply' in args and '--check' not in args:
                original(reader,'update-index','--cacheinfo',f'100644,{wrong},case.py')
            return result
        with patch.object(GitReader,'read',corrupt_result):
            with self.assertRaisesRegex(ValueError,'结果与已复核源码不一致'):self.apply(report)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)

    def test_linked_worktree_uses_its_own_index(self):
        self.write('case.py',GOOD);self.git('add','case.py');self.commit()
        linked=self.root/'linked';self.git('worktree','add','-qb','review-case',str(linked))
        before=(self.root/'.git/index').read_bytes()
        env={key:value for key,value in self.env.items() if key not in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE')}
        (linked/'case.py').write_bytes(BAD.encode())
        subprocess.run(['git','-C',str(linked),'add','case.py'],env=env,capture_output=True,check=True)
        with patch.dict(os.environ,env,clear=True):
            report=audit_index(linked);path=self.save_report(report)
            self.assertEqual(apply_index(path),1)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertEqual((linked/'case.py').read_bytes(),BAD.encode())

    def test_empty_patch_does_not_rewrite_index(self):
        self.write('case.py',GOOD);self.git('add','case.py');report=self.save_report()
        before=(self.root/'.git/index').read_bytes()
        self.assertEqual(self.apply(report),0)
        self.assertEqual((self.root/'.git/index').read_bytes(),before)
        self.assertFalse((self.root/'.git/index.lock').exists())


if __name__=='__main__':unittest.main()
