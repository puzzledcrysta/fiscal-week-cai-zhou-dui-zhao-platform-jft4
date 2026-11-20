from hashlib import sha256
from app.settings import RULE_VERSION
from app.modules.domain.promotion import identity


def digest(payload):
    return None if payload is None else sha256(payload).hexdigest()


def manifest(raw,book,promotions=None):
    source_hash,book_hash = digest(raw),digest(book)
    promotion_identity = identity(promotions) if promotions else None
    promotion_hash = None if not promotion_identity else sha256(promotion_identity.encode()).hexdigest()
    # 同一份来源、外部账与同一套促销日期才复用一个批次；重跑不新增记录。
    # 没有促销日期时沿用旧指纹写法，升级前存下的批次重跑仍是同一批。
    parts = [RULE_VERSION, source_hash, book_hash]
    if promotion_hash is not None:
        parts.append(promotion_hash)
    run_id = sha256(':'.join(parts).encode()).hexdigest()
    return {'run_id':run_id,'source_sha256':source_hash,'book_sha256':book_hash,
            'promotion_sha256':promotion_hash,'version':RULE_VERSION,
            'parameters':{'mode':'独立复算','promotion':promotion_hash is not None}}
