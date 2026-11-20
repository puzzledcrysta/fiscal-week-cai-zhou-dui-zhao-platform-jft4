import json
from app.modules.runs.service import get
from .decisions import timeline


def bundle(run_id):
    history = timeline(run_id)
    run = get(run_id)
    # 导出带来源行证据、促销配对与落单原因，以及适用的复核版本。
    return json.dumps({'manifest':run['manifest'],'counts':run['counts'],'results':run['accepted'],
                       'quarantine':run['quarantine'],'suppressed':run['suppressed'],
                       'promotion':run.get('promotion'),
                       'promotion_unpaired':run.get('promotion_unpaired',[]),
                       'reconciliation':run['book'],'review':history},ensure_ascii=False,indent=2)
