import csv
import io
from decimal import Decimal

import pytest

from app.errors import DataError
from app.manifest import manifest
from app.modules.domain.promotion import table
from app.modules.domain.rule import evaluate_detail
from app.modules.runs.service import run
from app.pipeline import execute

HEADER = ['门店财周单', '修订号', '提交时间', '上年期首', '上年周数', '本年期首',
          '本年周数', '上年日销售', '本年日销售', '原始备注']
PROMO_HEADER = ['门店财周单', '上年促销日', '本年促销日']


def csv_bytes(header, rows):
    out = io.StringIO(newline='')
    csv.writer(out).writerows([header, *rows])
    return out.getvalue().encode()


def source(*rows):
    return csv_bytes(HEADER, rows)


def promo(*rows):
    return csv_bytes(PROMO_HEADER, rows)


def record(key, previous_sales, current_sales, previous_start='2024-01-01',
           current_start='2024-12-30', weeks='52'):
    return [key, '1', '2026-11-18T09:30:00+08:00', previous_start, weeks, current_start,
            weeks, previous_sales, current_sales, '']


def evaluate(row):
    return evaluate_detail(row)


def fields(previous_sales, current_sales, previous_promo, current_promo,
           previous_start='2024-01-01', current_start='2024-12-30',
           weeks='52', previous_weeks=None):
    return {'上年期首': previous_start, '上年周数': previous_weeks or weeks,
            '本年期首': current_start, '本年周数': weeks,
            '上年日销售': previous_sales, '本年日销售': current_sales,
            '上年促销日': previous_promo, '本年促销日': current_promo}


def test_promotion_progress_beats_fiscal_week():
    # 上年促销在第1周周一，本年促销挪到第2周周二：财周同星期配不上，促销第1天仍可配。
    delta, proof, detail = evaluate(fields(
        '2024-01-01:100;2024-01-08:999', '2025-01-07:130;2025-01-14:999',
        '2024-01-01', '2025-01-07'))
    assert detail['mode'] == 'promotion'
    assert delta == Decimal('30')
    pair, = detail['promotion']['pairs']
    assert (pair['week_shift'], pair['same_weekday']) == (1, False)
    assert detail['promotion']['moved'] == 1
    assert dict((label, value) for label, value, _ in proof)['促销挪周'] == 1


def test_fiscal_week_would_pair_a_different_day():
    # 财周规则会把 2024-01-01 与 2024-12-30 的普通营业日配成 100→500；
    # 促销进度指出真正的同场日期是 2025-01-07，差额应是 100→130。
    fiscal_delta, _, fiscal = evaluate(fields('2024-01-01:100', '2024-12-30:500;2025-01-07:130',
                                              None, None))
    assert fiscal['mode'] == 'fiscal' and fiscal_delta == Decimal('400')
    promo_delta, _, detail = evaluate(fields('2024-01-01:100', '2024-12-30:500;2025-01-07:130',
                                             '2024-01-01', '2025-01-07'))
    assert promo_delta == Decimal('30')
    assert detail['fiscal'] == Decimal('400')


def test_short_promotion_does_not_borrow_ordinary_day():
    delta, _, detail = evaluate(fields(
        '2024-01-01:100;2024-01-02:110;2024-01-03:120', '2024-12-30:130;2024-12-31:120',
        '2024-01-01;2024-01-02;2024-01-03', '2024-12-30;2024-12-31'))
    assert delta == Decimal('40')
    assert detail['promotion']['paired'] == 2
    orphan, = detail['promotion']['orphans']
    assert (orphan['order'], orphan['side'], orphan['date'], orphan['code']) == (
        3, '上年', '2024-01-03', 'PROMO_SHORT')


def test_same_date_twice_is_counted_once():
    delta, _, detail = evaluate(fields(
        '2024-01-01:100', '2024-12-30:130', '2024-01-01;2024-01-01', '2024-12-30;2024-12-30'))
    assert delta == Decimal('30')
    assert detail['promotion']['paired'] == 1 and detail['promotion']['orphaned'] == 0
    assert len(detail['promotion']['pairs']) == 1


def test_closed_or_missing_day_stays_orphaned():
    delta, _, detail = evaluate(fields(
        '2024-01-01:100;2024-01-02:停业', '2024-12-30:150;2024-12-31:160',
        '2024-01-01;2024-01-02', '2024-12-30;2024-12-31'))
    assert delta == Decimal('50')
    codes = {(item['side'], item['code']) for item in detail['promotion']['orphans']}
    assert codes == {('上年', 'PROMO_CLOSED'), ('本年', 'PROMO_PAIR')}


def test_promotion_day_without_sales_reported():
    delta, _, detail = evaluate(fields(
        '2024-01-01:100', '2024-12-30:150;2024-12-31:160',
        '2024-01-01;2024-01-02', '2024-12-30;2024-12-31'))
    assert delta == Decimal('50')
    codes = {(item['side'], item['code']) for item in detail['promotion']['orphans']}
    assert codes == {('上年', 'PROMO_NO_DATA'), ('本年', 'PROMO_PAIR')}


def test_leap_week_promotion_is_listed_not_paired():
    sixty_three = fields('2024-01-01:100;2024-12-30:1100', '2025-01-06:120',
                         '2024-01-01;2024-12-30', '2025-01-06;2025-01-07',
                         previous_start='2024-01-01', current_start='2025-01-06',
                         previous_weeks='53')
    delta, _, detail = evaluate(sixty_three)
    assert delta == Decimal('20')
    leap = [item for item in detail['promotion']['orphans'] if item['code'] == 'PROMO_LEAP']
    assert [item['side'] for item in leap] == ['上年']


def test_single_sided_promotion_refused():
    with pytest.raises(DataError) as error:
        evaluate(fields('2024-01-01:100', '2024-12-30:130', '2024-01-01', None))
    assert error.value.code == 'PROMO_FORMAT'


def test_promotion_outside_year_rejected():
    with pytest.raises(DataError) as error:
        evaluate(fields('2024-01-01:100', '2024-12-30:130', '2023-12-31', '2024-12-30'))
    assert error.value.code == 'PROMO_SPAN'


def test_no_promotion_falls_back_to_fiscal_rule():
    for previous, current in [(None, None), ('', ''), ('无', '无'), ('-', '-')]:
        delta, proof, detail = evaluate(fields('2024-01-01:100', '2024-12-30:130', previous, current))
        assert detail['mode'] == 'fiscal' and delta == Decimal('30')


def test_table_deduplicates_and_sorts_dates():
    parsed = table(promo(['A', '2024-01-02;2024-01-01;2024-01-02', '2024-12-30']))
    assert [day.isoformat() for day in parsed['A']['上年促销日']] == ['2024-01-01', '2024-01-02']


def test_table_rejects_duplicate_key_and_bad_header():
    with pytest.raises(DataError) as error:
        table(promo(['A', '2024-01-01', '2024-12-30'], ['A', '2024-01-02', '2024-12-31']))
    assert error.value.code == 'PROMO_BOOK_CONFLICT'
    with pytest.raises(DataError) as error:
        table(csv_bytes(['门店财周单', '促销日'], [['A', '2024-01-01']]))
    assert error.value.code == 'PROMO_HEADER'


def test_batch_identity_uses_canonical_promotion_content():
    first = manifest(b'a', b'b', table(promo(['A', '2024-01-02;2024-01-01', '2024-12-30'])))
    same = manifest(b'a', b'b', table(promo(['A', '2024-01-01;2024-01-02', '2024-12-30'])))
    other = manifest(b'a', b'b', table(promo(['A', '2024-01-01', '2024-12-31'])))
    plain = manifest(b'a', b'b')
    assert first['run_id'] == same['run_id']
    assert first['run_id'] != other['run_id'] != plain['run_id']
    assert plain['parameters']['promotion'] is False


def test_promotion_book_is_used_for_external_reconciliation():
    data = source(record('001', '2024-01-01:100', '2025-01-06:120;2025-01-07:130'))
    promotions = table(promo(['001', '2024-01-01', '2025-01-07']))
    book = csv_bytes(['门店财周单', '外部记录值(元)'], [['001', '30']])
    report = execute(data, book, promotions)
    assert report['accepted'][0]['amount'] == '30'
    assert report['book']['rows'][0]['code'] == 'MATCH'
    assert report['book']['delta'] == '0'
    assert report['promotion']['aligned'] == 1 and report['promotion']['paired'] == 1


def test_rerun_same_batch_adds_no_record(client):
    payload = {'promotion': promo(['00101', '2024-01-01', '2025-01-06']).decode()}
    first = client.post('/api/runs', json=payload).json()
    second = client.post('/api/runs', json=payload).json()
    assert first == second
    assert len(client.get('/api/runs').json()) == 1
    assert first['manifest']['parameters']['promotion'] is True


def test_export_carries_pairs_and_orphan_reasons(client):
    data = source(record('001', '2024-01-01:100;2024-01-02:110;2024-01-03:120',
                         '2024-12-30:130;2024-12-31:120'))
    promotions = promo(['001', '2024-01-01;2024-01-02;2024-01-03', '2024-12-30;2024-12-31'])
    run_id = client.post('/api/runs', json={'data': data.decode(),
                                            'promotion': promotions.decode()}).json()['manifest']['run_id']
    bundle = client.get(f'/api/export/{run_id}').json()
    row = bundle['results'][0]
    assert [pair['order'] for pair in row['promotion']['pairs']] == [1, 2]
    assert row['promotion']['orphans'][0]['code'] == 'PROMO_SHORT'
    assert bundle['promotion']['orphaned'] == 1


def test_review_needs_note_when_promotion_days_are_orphaned(client):
    data = source(record('001', '2024-01-01:100;2024-01-02:110',
                         '2024-12-30:130'))
    promotions = promo(['001', '2024-01-01;2024-01-02', '2024-12-30'])
    run_id = client.post('/api/runs', json={'data': data.decode(),
                                            'promotion': promotions.decode()}).json()['manifest']['run_id']
    refused = client.post(f'/api/review/{run_id}', json={'version': 0, 'decision': '确认', 'note': ' '})
    assert (refused.status_code, refused.json()['code']) == (422, 'REVIEW_NOTE')
    accepted = client.post(f'/api/review/{run_id}', json={'version': 0, 'decision': '确认',
                                                          'note': '少办一天已核'})
    assert accepted.status_code == 200


def test_replay_keeps_promotion_inputs(client):
    data = source(record('001', '2024-01-01:100', '2025-01-07:130'))
    promotions = promo(['001', '2024-01-01', '2025-01-07'])
    first = client.post('/api/runs', json={'data': data.decode(),
                                           'promotion': promotions.decode()}).json()
    run_id = first['manifest']['run_id']
    assert client.post(f'/api/runs/{run_id}/replay').json() == first
    restored = client.get(f'/api/runs/{run_id}/source').json()
    assert restored['promotion_base64'] and restored['data_base64']


def test_unmatched_promotion_key_is_reported(client):
    data = source(record('001', '2024-01-01:100', '2024-12-30:130'))
    promotions = promo(['001', '2024-01-01', '2024-12-30'],
                       ['404', '2024-01-01', '2024-12-30'])
    result = client.post('/api/reconcile', json={'data': data.decode(),
                                                 'promotion': promotions.decode()}).json()
    assert result['promotion_unpaired'] == [
        {'key': '404', 'code': 'NO_RECORD', 'detail': '来源没有此业务键', 'line': None}]


def test_promotion_table_optional_column_in_source():
    # 来源表直接带两年促销日时，不需要另交促销表。
    header = HEADER[:9] + ['上年促销日', '本年促销日']
    rows = [record('001', '2024-01-01:100', '2025-01-07:130')[:9] + ['2024-01-01', '2025-01-07']]
    report = execute(csv_bytes(header, rows), csv_bytes(['门店财周单', '外部记录值(元)'], []))
    assert report['accepted'][0]['alignment'] == 'promotion'
    assert report['accepted'][0]['amount'] == '30'
