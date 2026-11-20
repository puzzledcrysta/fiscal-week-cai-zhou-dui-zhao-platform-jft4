import json
from app.errors import DataError
from app.settings import KEY
from app.modules.intake.reader import decode, records
from .rule import ABSENT, promo_dates

PREVIOUS, CURRENT = '上年促销日', '本年促销日'
SIDES = (PREVIOUS, CURRENT)
ALIASES = {'上年促销日期': PREVIOUS, '上年同场促销日': PREVIOUS, '上年活动日': PREVIOUS,
           '本年促销日期': CURRENT, '本年同场促销日': CURRENT, '本年活动日': CURRENT}


def table(payload):
    """解析促销日期表：门店财周单 + 两年同场促销日，日期用半角分号分隔。

    同一年重复写同一天只保留一次，不会被重复计入；整年留空表示该年没有同场促销。
    """
    if payload is None:
        return {}
    text, _ = decode(payload)
    rows = iter(records(text))
    _, header = next(rows, (0, []))
    names = [ALIASES.get(name.strip().removeprefix('﻿'), name.strip()) for name in header]
    if len(names) != 3 or set(names) != {KEY, *SIDES}:
        raise DataError('PROMO_HEADER', '促销日期表须为门店财周单、上年促销日、本年促销日三列')
    by_key = {}
    for line, row in rows:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != 3 or not row[0].strip():
            raise DataError('PROMO_WIDTH', f'促销日期表第 {line} 行缺少业务键或日期')
        key = row[0].strip()
        if key in by_key:
            raise DataError('PROMO_BOOK_CONFLICT', f'促销日期表第 {line} 行重复业务键 {key}')
        try:
            previous, current = promo_dates(row[1]), promo_dates(row[2])
        except DataError as error:
            raise DataError(error.code, f'促销日期表第 {line} 行：{error}') from error
        if previous is None and current is None:
            continue
        # 单边留空按「该年没有同场促销」处理，由复算逐条隔离，不带整表失败。
        by_key[key] = {PREVIOUS: previous or [], CURRENT: current or []}
    return by_key


def fingerprint(by_key):
    """规范化表示：键排序、日期按活动进度，重复日期不重复计入；用于批次身份与证据。"""
    return {key: {'previous': [day.isoformat() for day in value[PREVIOUS]],
                  'current': [day.isoformat() for day in value[CURRENT]]}
            for key, value in sorted(by_key.items())}


def identity(by_key):
    """批次指纹只认促销内容本身：拆分写法、日期重复或行序不同都不另生成批次。"""
    return json.dumps(fingerprint(by_key), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def attach(records, by_key):
    """把促销日期挂到待复算记录上：来源已填写的优先，留空或占位符由促销表补缺。

    原始行不改动；「无」是来源的明确表态（该年没有同场促销），不被促销表覆盖。
    """
    if not by_key:
        return records
    attached = []
    for record in records:
        supplied = by_key.get(record['key'])
        if supplied is None:
            attached.append(record)
            continue
        fields = dict(record['fields'])
        for name in SIDES:
            value = fields.get(name)
            if value is not None and value.strip().casefold() not in ABSENT:
                continue
            days = supplied[name]
            fields[name] = ';'.join(day.isoformat() for day in days) if days else '无'
        attached.append({**record, 'fields': fields})
    return attached


def unpaired(records, by_key, findings):
    """促销表里没有进入复算的业务键：给出被隔离、被替代或来源缺失的原因。"""
    present = {record['key'] for record in records}
    reasons = {}
    for finding in findings:
        reasons.setdefault(finding['key'], {'code': finding['code'], 'detail': finding['detail'],
                                            'line': finding['line']})
    return [{'key': key, **reasons.get(key, {'code': 'NO_RECORD', 'detail': '来源没有此业务键',
                                             'line': None})}
            for key in sorted(by_key) if key not in present]
