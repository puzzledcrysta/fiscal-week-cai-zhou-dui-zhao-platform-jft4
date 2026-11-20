from collections import Counter
from app.evidence import distribution
from app.modules.intake.service import intake
from app.modules.contract.service import normalize
from app.modules.quality.service import inspect
from app.modules.domain.service import calculate
from app.modules.domain.promotion import attach, fingerprint, unpaired
from app.modules.reconcile.service import compare


def stages(source, promotions=None):
    raw = intake(source)
    contract, rejected = normalize(raw)
    quality = inspect(contract,rejected)
    ready = attach(quality['ready'],promotions or {})
    accepted, domain_bad = calculate(ready)
    bad = sorted([*quality['rejected'],*domain_bad],key=lambda row:row['line'])
    return {'intake':raw,'contract':contract,'quality':quality,'accepted':accepted,
            'domain_bad':domain_bad,'rejected':bad,
            'promotion_input':promotions or {},
            'promotion_unpaired':unpaired(accepted,promotions or {},[*bad,*quality['suppressed']])}


def promotion_summary(accepted, promotions):
    aligned = [row for row in accepted if row['alignment'] == 'promotion']
    orphans = [item for row in aligned for item in row['promotion']['orphans']]
    return {'supplied': len(promotions), 'aligned': len(aligned),
            'keys': [row['key'] for row in aligned],
            'paired': sum(row['promotion']['paired'] for row in aligned),
            'orphaned': sum(row['promotion']['orphaned'] for row in aligned),
            'orphan_entries': len(orphans),
            'moved': sum(row['promotion']['moved'] for row in aligned),
            'weekday_changed': sum(row['promotion']['weekday_changed'] for row in aligned),
            'reasons': dict(sorted(Counter(item['code'] for item in orphans).items()))}


def execute(source,book,promotions=None):
    result = stages(source,promotions)
    raw, accepted, bad = (result[key] for key in ('intake','accepted','rejected'))
    suppressed = result['quality']['suppressed']
    counts = {'input':raw['input_count'],'accepted':len(accepted),'rejected':len(bad),
              'suppressed':len(suppressed),'blank':len(raw['blank_lines']),'repeated_header':len(raw['header_lines'])}
    balanced = counts['input'] == sum(value for key,value in counts.items() if key!='input')
    if not balanced:
        raise RuntimeError('来源记录数量无法闭合')
    return {'counts':counts,'balanced':balanced,'accepted':accepted,'quarantine':bad,'suppressed':suppressed,
            'reasons':distribution(bad),'book':compare(accepted,book),'encoding':raw['encoding'],
            'promotion':promotion_summary(accepted,result['promotion_input']),
            'promotion_unpaired':result['promotion_unpaired'],
            'promotion_fingerprint':fingerprint(result['promotion_input'])}
