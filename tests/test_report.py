import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from awaitlab.report import write_report


class ReportTests(unittest.TestCase):
    def test_report_data_cannot_close_script_element(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            payload={'title':'</script><script>alert(1)</script>','comparisons':[]}
            path=write_report(payload,Path(temp)/'report.html')
            text=path.read_text(encoding='utf-8')
            data=text.split('id="data">',1)[1].split('</script>',1)[0]
            self.assertNotIn('</script>',data)
            self.assertEqual(json.loads(data),payload)
            self.assertNotIn('src="http',text)

    def test_failed_replace_preserves_previous_complete_html(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            path=Path(temp)/'report.html';path.write_text('previous complete report',encoding='utf-8')
            with patch.object(Path,'replace',side_effect=PermissionError('locked by reader')):
                with self.assertRaises(PermissionError):write_report({'title':'new'},path)
            self.assertEqual(path.read_text(encoding='utf-8'),'previous complete report')


if __name__=='__main__':unittest.main()
