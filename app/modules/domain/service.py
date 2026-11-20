from app.errors import DataError
from app.evidence import finding
from app.settings import UNIT
from .rule import evaluate_detail


def calculate(records):
    accepted, rejected = [], []
    for record in records:
        try:
            amount, proof, detail = evaluate_detail(record['fields'])
        except DataError as error:
            rejected.append(finding(record, error.code, str(error)))
            continue
        accepted.append({'key': record['key'], 'line': record['line'], 'revision': record['revision'],
                         'amount': format(amount, 'f'), 'unit': UNIT, 'raw': record['raw'],
                         'alignment': detail['mode'],
                         'fiscal_amount': (None if detail['fiscal'] is None
                                           else format(detail['fiscal'], 'f')),
                         'promotion': detail['promotion'],
                         'proof': [{'metric': label, 'value': str(value), 'unit': unit}
                                   for label, value, unit in proof]})
    return accepted, rejected
