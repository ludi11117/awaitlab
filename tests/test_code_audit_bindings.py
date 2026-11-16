import unittest

from awaitlab.code_audit import audit_source


class BindingTests(unittest.TestCase):
    def assert_unbound_preserved(self,source):
        findings,patched=audit_source(source)
        self.assertEqual(findings,[]);self.assertEqual(patched,source)
        for candidate in (source,patched):
            scope={};exec(candidate,scope)
            with self.assertRaises(UnboundLocalError):scope['read'](None)

    def test_deleted_parameter_read_is_not_removed(self):
        self.assert_unbound_preserved('''def read(value):
    del value
    if value is None and value is not None:
        return 1
    return 2
''')

    def test_exception_cleanup_can_unbind_a_parameter(self):
        self.assert_unbound_preserved('''def read(value):
    try:
        raise ValueError()
    except ValueError as value:
        pass
    if value is None and value is not None:
        return 1
    return 2
''')

    def test_nested_nonlocal_delete_can_unbind_a_parameter(self):
        self.assert_unbound_preserved('''def read(value):
    def clear():
        nonlocal value
        del value
    clear()
    if value is None and value is not None:
        return 1
    return 2
''')

    def test_all_parameter_kinds_respect_explicit_deletion(self):
        for signature,args,kwargs in (('value, /',(None,),{}),('*args',(),{}),('**kwargs',(),{}),
                ('*, value',(),{'value':None})):
            name='args' if signature=='*args' else 'kwargs' if signature=='**kwargs' else 'value'
            source=f'def read({signature}):\n    del {name}\n    if {name} is None or {name} is not None:\n        return 1\n    return 2\n'
            findings,patched=audit_source(source)
            self.assertEqual(findings,[]);self.assertEqual(patched,source)
            scope={};exec(patched,scope)
            with self.assertRaises(UnboundLocalError):scope['read'](*args,**kwargs)

    def test_unrelated_inner_local_deletion_does_not_taint_outer_parameter(self):
        source='''def read(value):
    def inner(value):
        del value
    if value is None or value is not None:
        return 1
    return 2
'''
        findings,patched=audit_source(source)
        self.assertEqual(len(findings),1);self.assertTrue(findings[0]['patch_available'])
        scope={};exec(patched,scope)
        self.assertEqual(scope['read'](None),1)

    def test_new_guards_can_prove_facts_after_a_rebind(self):
        source='''def read(value,replacement):
    del value
    value=replacement
    if value is None:
        return 0
    if value is None:
        return 1
    return value
'''
        findings,patched=audit_source(source)
        self.assertEqual(len(findings),1);self.assertTrue(findings[0]['patch_available'])
        before={};after={};exec(source,before);exec(patched,after)
        for value in (None,True,False,0,'',[],{'id':1}):
            self.assertEqual(before['read']('ignored',value),after['read']('ignored',value))


if __name__=='__main__':unittest.main()
