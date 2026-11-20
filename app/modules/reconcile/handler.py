from fastapi import APIRouter
from app.inputs import Paired
from app.modules.domain.promotion import table
from app.pipeline import execute

router = APIRouter()

@router.post('/api/reconcile')
def reconcile(source: Paired):
    report = execute(source.raw(),source.ledger(),table(source.promotions()))
    return {key:report[key] for key in ('book','counts','balanced','promotion','promotion_unpaired')}
