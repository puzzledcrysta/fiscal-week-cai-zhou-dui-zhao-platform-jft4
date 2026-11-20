from fastapi import APIRouter
from app.inputs import Source
from app.modules.domain.promotion import table
from app.pipeline import stages

router = APIRouter()

@router.post('/api/domain')
def recalculate(source: Source):
    result = stages(source.raw(),table(source.promotions()))
    return {key:result[key] for key in ('accepted','rejected','domain_bad','promotion_unpaired')}
