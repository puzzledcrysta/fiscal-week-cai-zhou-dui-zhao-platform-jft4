from datetime import timedelta
from decimal import Decimal as D
from app.errors import DataError
from .values import calendar, number, whole, parts

# 促销日期留空或旧表占位符视为「未提供」，回落到财周对齐；「无」表示明确没有促销。
ABSENT = {'', '-', 'n/a', 'null', '未知'}
NO_PROMOTION = '无'


def index(text, start, weeks):
    result = {}
    for item in parts(text):
        raw_day, sep, raw_amount = item.partition(':')
        if not sep:
            raise DataError('FISCAL_FORMAT', '日销售须包含日期和销售额')
        day = calendar(raw_day)
        offset = (day-start).days
        if not 0 <= offset < weeks*7:
            raise DataError('FISCAL_SPAN', f'{day} 超出本财年')
        amount = None if raw_amount == '停业' else number(raw_amount, -10**8, 10**8)
        if offset in result and result[offset] != amount:
            raise DataError('FISCAL_CONFLICT', f'{day} 有互相矛盾的营业记录')
        result[offset] = amount
    return result


def promo_dates(text):
    """解析一年的促销日期，按活动进度（日历先后）排出第 1、2… 天；同一天只记一次。"""
    if text is None:
        return None
    value = text.strip()
    if value.casefold() in ABSENT:
        return None
    if value == NO_PROMOTION:
        return []
    return sorted({calendar(raw_day) for raw_day in parts(value)})


def placed(days, start, weeks, label):
    """按日历先后排定促销日；重复日期只保留一次，不按天重复计入。"""
    located, seen = [], set()
    for day in days:
        offset = (day-start).days
        if not 0 <= offset < weeks*7:
            raise DataError('PROMO_SPAN', f'{label}促销日 {day} 超出本财年')
        if offset not in seen:
            seen.add(offset)
            located.append((day, offset))
    return sorted(located, key=lambda item: item[1])


def fiscal_pair(before, after):
    delta, used, skipped, weeks = D(0), 0, 0, {}
    for offset in sorted(before.keys() | after.keys()):
        a, b = before.get(offset), after.get(offset)
        if offset >= 364 or a is None or b is None:
            skipped += 1
            continue
        value = b-a
        week = offset//7+1
        weeks[week] = weeks.get(week, D(0))+value
        delta += value
        used += 1
    return delta, used, skipped, weeks


def day_amount(indexed, offset):
    if offset not in indexed:
        return None, 'PROMO_NO_DATA'
    if indexed[offset] is None:
        return None, 'PROMO_CLOSED'
    return indexed[offset], None


def orphan(order, side, day, code, detail):
    return {'order': order, 'side': side, 'date': day.isoformat(), 'code': code, 'detail': detail}


def promotion_pair(before, after, previous, previous_weeks, current, current_weeks,
                   previous_days, current_days):
    """按促销进度（活动第几天）对齐：序号相同才配对，不让普通营业日补缺，日期只计一次。"""
    previous_sequence = placed(previous_days, previous, previous_weeks, '上年')
    current_sequence = placed(current_days, current, current_weeks, '本年')
    delta, pairs, orphans = D(0), [], []
    moved = weekday_changed = 0
    for position in range(max(len(previous_sequence), len(current_sequence))):
        order = position+1
        old = previous_sequence[position] if position < len(previous_sequence) else None
        new = current_sequence[position] if position < len(current_sequence) else None
        old_leap = old is not None and old[1] >= 364
        new_leap = new is not None and new[1] >= 364
        if old_leap:
            orphans.append(orphan(order, '上年', old[0], 'PROMO_LEAP', '第53周单列，不做可比配对'))
        if new_leap:
            orphans.append(orphan(order, '本年', new[0], 'PROMO_LEAP', '第53周单列，不做可比配对'))
        if old is None or new is None or old_leap or new_leap:
            orphans.extend(uncoupled(order, old, old_leap, new, new_leap))
            continue
        old_amount, old_code = day_amount(before, old[1])
        new_amount, new_code = day_amount(after, new[1])
        if old_code or new_code:
            if old_code:
                orphans.append(orphan(order, '上年', old[0], old_code, '该促销日没有可用日销'))
            if new_code:
                orphans.append(orphan(order, '本年', new[0], new_code, '该促销日没有可用日销'))
            if not old_code:
                orphans.append(orphan(order, '上年', old[0], 'PROMO_PAIR', '对应促销日不可比，本期不计数'))
            if not new_code:
                orphans.append(orphan(order, '本年', new[0], 'PROMO_PAIR', '对应促销日不可比，本期不计数'))
            continue
        value = new_amount-old_amount
        shift = new[1]//7-old[1]//7
        same_weekday = new[0].weekday() == old[0].weekday()
        moved += shift != 0
        weekday_changed += (shift == 0 and not same_weekday)
        delta += value
        pairs.append({'order': order,
                      'previous_date': old[0].isoformat(), 'current_date': new[0].isoformat(),
                      'previous_week': old[1]//7+1, 'current_week': new[1]//7+1,
                      'week_shift': shift, 'same_weekday': same_weekday,
                      'previous_amount': format(old_amount, 'f'),
                      'current_amount': format(new_amount, 'f'),
                      'delta': format(value, 'f')})
    if not pairs:
        raise DataError('PROMO_NO_PAIR', '同一场促销没有可比营业日')
    orphans.sort(key=lambda item: (item['order'], item['side'] != '上年'))
    return delta, pairs, orphans, moved, weekday_changed


def uncoupled(order, old, old_leap, new, new_leap):
    """一侧缺失或落在第53周时，为仍在场的一侧写明落单原因。"""
    found = []
    if old is not None and not old_leap:
        code = 'PROMO_PAIR' if new is not None else 'PROMO_SHORT'
        detail = ('对面的同序促销日落在第53周，不可比' if new is not None
                  else '本年没有同序促销日，普通营业日不替代')
        found.append(orphan(order, '上年', old[0], code, detail))
    if new is not None and not new_leap:
        code = 'PROMO_PAIR' if old is not None else 'PROMO_SHORT'
        detail = ('对面的同序促销日落在第53周，不可比' if old is not None
                  else '上年没有同序促销日，普通营业日不替代')
        found.append(orphan(order, '本年', new[0], code, detail))
    return found


def week_proof(weeks):
    proof = []
    for week, value in weeks.items():
        period = ((week-1)//13)*3 + (1 if (week-1)%13 < 4 else 2 if (week-1)%13 < 8 else 3)
        proof.append((f'第{period:02}期 W{week:02}', value, '元'))
    return proof


def leap_amounts(before, after):
    extra = sum((amount for offset, amount in after.items() if offset >= 364 and amount is not None), D(0))
    previous_extra = sum((amount for offset, amount in before.items() if offset >= 364 and amount is not None), D(0))
    return extra, previous_extra


def promotion_inputs(row):
    """两年促销日的解析结果：None=本次按财周对齐，否则是两年的促销日序列。"""
    previous_promo = promo_dates(row.get('上年促销日'))
    current_promo = promo_dates(row.get('本年促销日'))
    if previous_promo is None and current_promo is None:
        return None
    if (previous_promo is None) != (current_promo is None):
        raise DataError('PROMO_FORMAT', '两年促销日须同时填写或同时留空')
    if not previous_promo and not current_promo:
        return None
    if not previous_promo or not current_promo:
        raise DataError('PROMO_NO_PAIR', '同一场促销有一年没有任何日期')
    return previous_promo, current_promo


def evaluate_detail(row):
    previous, current = calendar(row['上年期首']), calendar(row['本年期首'])
    prev_count, cur_count = whole(row['上年周数'], 52, 53), whole(row['本年周数'], 52, 53)
    if previous.weekday() or current-previous != timedelta(weeks=prev_count):
        raise DataError('FISCAL_BOUNDARY', '期首须为周一，且两期连续')
    before = index(row['上年日销售'], previous, prev_count)
    after = index(row['本年日销售'], current, cur_count)
    fiscal_delta, used, skipped, weeks = fiscal_pair(before, after)
    extra, previous_extra = leap_amounts(before, after)
    promo = promotion_inputs(row)
    if promo is None:
        if not used:
            raise DataError('FISCAL_NO_PAIR', '共有财周内没有双方营业日')
        proof = week_proof(weeks)
        proof += [('双方营业', used, '日'), ('未配对', skipped, '日'),
                  ('本年闰周', extra, '元'), ('上年闰周', previous_extra, '元')]
        return fiscal_delta, proof, {'mode': 'fiscal', 'fiscal': fiscal_delta, 'promotion': None}
    previous_promo, current_promo = promo
    delta, pairs, orphans, moved, weekday_changed = promotion_pair(
        before, after, previous, prev_count, current, cur_count, previous_promo, current_promo)
    # 落单按促销第几天计数：同一天两侧都落单也只算一天。
    orphaned = len({item['order'] for item in orphans})
    promotion = {'previous_days': len(previous_promo), 'current_days': len(current_promo),
                 'paired': len(pairs), 'orphaned': orphaned, 'orphan_entries': len(orphans),
                 'moved': moved, 'weekday_changed': weekday_changed,
                 'pairs': pairs, 'orphans': orphans}
    proof = [('对齐方式', '促销进度', ''), ('促销可比', len(pairs), '日'),
             ('促销落单', orphaned, '日'), ('促销挪周', moved, '日'),
             ('财周参照', format(fiscal_delta, 'f') if used else '无可比日', '元' if used else ''),
             ('本年闰周', extra, '元'), ('上年闰周', previous_extra, '元')]
    return delta, proof, {'mode': 'promotion', 'fiscal': fiscal_delta if used else None,
                          'promotion': promotion}


def evaluate(row):
    delta, proof, _ = evaluate_detail(row)
    return delta, proof
