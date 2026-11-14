"""Self-contained interactive report; no server, CDN, or resident background process."""
import json
from pathlib import Path


def write_report(report, target):
    assets=Path(__file__).resolve().parent/'assets'
    data=json.dumps(report,ensure_ascii=False,separators=(',',':')).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwaitLab · 异步优化实验报告</title><style>'''
    html+=(assets/'report.css').read_text(encoding='utf-8')+'</style></head><body><div id="app"></div><script type="application/json" id="data">'+data+'</script><script>'
    html+=(assets/'report.js').read_text(encoding='utf-8')+'</script></body></html>'
    target=Path(target);target.write_text(html,encoding='utf-8')
    return target
