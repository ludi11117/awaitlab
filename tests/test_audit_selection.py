import unittest
from awaitlab.code_audit import audit_source


SOURCE='''def first(value):
    if value is None:
        return None
    if value is None:
        return 1
    return value

def second(value):
    if value is None:
        return None
    if value is not None:
        return value
'''


class SelectionTests(unittest.TestCase):
    def test_only_selected_guard_changes_and_other_function_stays_identical(self):
        findings,patched=audit_source(SOURCE,fix_lines={4})
        self.assertEqual(len(findings),2)
        self.assertEqual([item['line'] for item in findings if item['patch_available']],[4])
        self.assertEqual(patched.split('def second')[1],SOURCE.split('def second')[1])
        self.assertNotIn('return 1',patched)

    def test_empty_or_missing_selection_does_not_apply_other_edits(self):
        for lines in (set(),{999},{2}):
            findings,patched=audit_source(SOURCE,fix_lines=lines)
            self.assertEqual(patched,SOURCE);self.assertFalse(any(item['patch_available'] for item in findings))

    def test_selection_still_runs_syntax_and_docstring_validation(self):
        for source,line in (
                ('def read(value):\n    if value is not None:\n        if value is None:\n            return 1\n    return value\n',3),
                ('def read(value):\n    if value is None or value is not None:\n        "not a docstring"\n    return 1\n',2)):
            findings,patched=audit_source(source,fix_lines={line})
            self.assertEqual(patched,source);self.assertFalse(findings[0]['patch_available'])

    def test_nested_selection_does_not_remove_outer_guard(self):
        source='def read(value):\n    if value is None:\n        if value is None:\n            return None\n    return value\n'
        findings,patched=audit_source(source,fix_lines={3})
        self.assertIn('    if value is None:',patched);self.assertNotIn('        if value is None:',patched)
        before={};after={};exec(source,before);exec(patched,after)
        for value in (None,True,False,0,'',[],{'id':1}):self.assertEqual(before['read'](value),after['read'](value))


if __name__=='__main__':unittest.main()
