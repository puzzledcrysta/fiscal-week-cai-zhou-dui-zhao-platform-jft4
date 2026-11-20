from base64 import b64decode
from binascii import Error as Base64Error
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from app.settings import SAMPLE_ROOT
from app.errors import DataError

MAX_BYTES = 128 * 1024
CsvText = Annotated[str, Field(max_length=MAX_BYTES)]
EncodedCsv = Annotated[str, Field(max_length=(MAX_BYTES + 2) // 3 * 4)]


def input_bytes(text, encoded, path):
    if text is not None and encoded is not None:
        raise DataError('CONTRACT', '同一输入只能提交文本或原始文件')
    if encoded is not None:
        try:
            raw = b64decode(encoded, validate=True)
        except (ValueError, Base64Error) as error:
            raise DataError('ENCODING', '原始文件编码无效') from error
    elif text is not None:
        raw = text.encode()
    else:
        return path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise DataError('LIMIT', '单个文件不能超过 128 KiB', 413)
    return raw


class Source(BaseModel):
    data: CsvText | None = None
    data_base64: EncodedCsv | None = None
    demo: Literal['shift'] = 'shift'
    promotion: CsvText | None = None
    promotion_base64: EncodedCsv | None = None

    def raw(self):
        return input_bytes(self.data, self.data_base64, SAMPLE_ROOT/'shift.csv')

    def promotions(self):
        """两年同场促销日期表；未提交时返回 None，本次按原财周规则对齐。"""
        if self.promotion is not None and self.promotion_base64 is not None:
            raise DataError('CONTRACT', '促销日期只能提交文本或原始文件其中之一')
        if self.promotion is not None:
            raw = self.promotion.encode()
        elif self.promotion_base64 is not None:
            try:
                raw = b64decode(self.promotion_base64, validate=True)
            except (ValueError, Base64Error) as error:
                raise DataError('ENCODING', '促销日期文件编码无效') from error
        else:
            return None
        if not raw.strip():
            return None
        if len(raw) > MAX_BYTES:
            raise DataError('LIMIT', '单个文件不能超过 128 KiB', 413)
        return raw


class Paired(Source):
    book: CsvText | None = None
    book_base64: EncodedCsv | None = None

    def ledger(self):
        return input_bytes(self.book, self.book_base64, SAMPLE_ROOT/'external.csv')


class Review(BaseModel):
    version: int = Field(ge=0)
    decision: Literal['确认','退回']
    note: str = Field(default='',max_length=500)


def read_sample(name):
    choices = {'shift':'shift.csv','external':'external.csv','promotion':'promotion.csv'}
    if name not in choices:
        raise DataError('DEMO_UNKNOWN','没有此样例',404)
    return SAMPLE_ROOT.joinpath(choices[name]).read_bytes()
