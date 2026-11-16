import asyncio
import itertools
import unittest

from awaitlab.code_audit import audit_source


class LoopExitTests(unittest.TestCase):
    def test_continue_and_break_prove_following_guard_is_redundant(self):
        for exit_ in ('continue','break'):
            with self.subTest(exit_=exit_):
                source=f'''def read(values):
    result=[]
    for value in values:
        if value is None:
            {exit_}
        if value is None:
            result.append('dead')
        result.append(value)
    return result
'''
                findings,patched=audit_source(source)
                self.assertEqual(len(findings),1)
                self.assertTrue(findings[0]['patch_available'])
                self.assertNotIn("'dead'",patched)

    def test_while_continue_proof_and_runtime_results(self):
        source='''def read(values):
    result=[]
    while values:
        value=values.pop(0)
        if value is None:
            continue
        if value is not None:
            result.append(value)
    return result
'''
        findings,patched=audit_source(source)
        self.assertEqual(len(findings),1);self.assertTrue(findings[0]['patch_available'])
        before={};after={};exec(source,before);exec(patched,after)
        for row in itertools.product((None,True,False,0,''),repeat=3):
            self.assertEqual(before['read'](list(row)),after['read'](list(row)))

    def test_unknown_condition_with_two_exits_stops_unreachable_analysis(self):
        for body in ('return 1\n    else:\n        return 2',
                "raise ValueError('stop')\n    else:\n        return 2"):
            source=f'''def read(value,ready):
    if ready:
        {body}
    if value is None:
        if value is None:
            return 3
    return value
'''
            findings,patched=audit_source(source)
            self.assertEqual(findings,[]);self.assertEqual(patched,source)

    def test_loop_exits_do_not_terminate_outer_function_analysis(self):
        for exit_ in ('continue','break'):
            source=f'''def read(values,value):
    for item in values:
        {exit_}
    if value is None:
        return None
    if value is None:
        return 'dead'
    return value
'''
            findings,patched=audit_source(source)
            self.assertEqual(len(findings),1);self.assertNotIn("'dead'",patched)

    def test_inner_break_does_not_end_outer_iteration(self):
        source='''def read(rows):
    result=[]
    for row in rows:
        for value in row:
            if value is None:
                break
        if row is None:
            return 'invalid'
        result.append(row)
    return result
'''
        findings,patched=audit_source(source)
        self.assertEqual(findings,[]);self.assertEqual(patched,source)

    def test_mixed_loop_exits_make_following_code_unreachable(self):
        source='''def read(values,ready):
    for value in values:
        if ready:
            break
        else:
            continue
        if value is None:
            if value is None:
                return 'unreachable'
    return 1
'''
        findings,patched=audit_source(source)
        self.assertEqual(findings,[]);self.assertEqual(patched,source)

    def test_loop_else_and_live_iteration_outputs_are_preserved(self):
        values=(None,True,False,0,'',[],{'id':1})
        changes=0
        for exit_,condition in itertools.product(('continue','break'),('value is None','value is not None')):
            source=f'''def read(values):
    result=[]
    for value in values:
        if value is None:
            {exit_}
        if {condition}:
            result.append(value)
    else:
        result.append('exhausted')
    return result
'''
            findings,patched=audit_source(source)
            self.assertEqual(len(findings),1);self.assertTrue(findings[0]['patch_available'])
            changes+=source!=patched
            before={};after={};exec(source,before);exec(patched,after)
            for row in itertools.product(values,repeat=3):
                self.assertEqual(before['read'](row),after['read'](row),(exit_,condition,row))
        self.assertEqual(changes,4)

    def test_async_for_exits_preserve_results(self):
        async def values(row):
            for value in row:yield value
        async def check():
            for exit_ in ('continue','break'):
                source=f'''async def read(values):
    result=[]
    async for value in values:
        if value is None:
            {exit_}
        if value is not None:
            result.append(value)
    return result
'''
                findings,patched=audit_source(source)
                self.assertEqual(len(findings),1);self.assertTrue(findings[0]['patch_available'])
                before={};after={};exec(source,before);exec(patched,after)
                for row in itertools.product((None,True,False,0,'',[],{'id':1}),repeat=2):
                    self.assertEqual(await before['read'](values(row)),await after['read'](values(row)))
        asyncio.run(check())

    def test_finally_reassignment_drops_loop_guard_facts(self):
        source='''def read(values):
    for value in values:
        try:
            if value is None:
                continue
        finally:
            value=None
        if value is None:
            return 'reassigned'
    return 'finished'
'''
        findings,patched=audit_source(source)
        self.assertEqual(findings,[]);self.assertEqual(patched,source)
        scope={};exec(patched,scope)
        self.assertEqual(scope['read']([1]),'reassigned')
        self.assertEqual(scope['read']([None]),'finished')


if __name__=='__main__':unittest.main()
