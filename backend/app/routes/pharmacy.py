from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
import logging
import io
import uuid
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case, literal_column, String as SQLString
from app.db_models import PharmacyMedicine, PharmacySale, Prescription, Token, User, Doctor
from db_automation.services import PharmacyInvoiceService

from app.security import get_current_active_user
from app.database import get_db
from app.models import TokenData
from app.security import require_roles
from app.utils.responses import ok
from app.services.go_pos_service import go_pos_service
from app.services.cache_service import CacheService, cached
from app.routes.realtime import manager as RealTimeConnectionManager

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from app.db_models import Prescription

router = APIRouter()
public_router = APIRouter()

logger = logging.getLogger(__name__)


async def _broadcast_inventory_update(hospital_id: Optional[str]) -> None:
    if not hospital_id:
        return

    try:
        await RealTimeConnectionManager.broadcast_via_redis(
            f"hospital_{hospital_id}",
            {"type": "INVENTORY_UPDATE"}
        )
    except Exception:
        pass

class AddMedicineRequest(BaseModel):
    product_id: int = Field(..., ge=0)
    batch_no: str
    name: str
    generic_name: Optional[str] = None
    type: Optional[str] = None
    distributor: Optional[str] = None
    supplier_name: Optional[str] = None
    distributor_company: Optional[str] = None
    distributor_mobile: Optional[str] = None
    purchase_price: float = Field(..., gt=0)
    selling_price: float = Field(..., gt=0)
    stock_unit: Optional[str] = None
    quantity: int = Field(..., ge=0)
    expiration_date: Optional[str] = None
    manufacture_date: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    hospital_id: Optional[str] = None

class DispenseMedicineItem(BaseModel):
    product_id: int = Field(..., ge=0)
    quantity: int = Field(..., ge=1)

class DispenseMedicineRequest(BaseModel):
    patient_id: str
    doctor_id: str
    medicines: List[DispenseMedicineItem]


class PrescriptionStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="pending | completed")

def _normalize_date_str(v: Optional[str]) -> Optional[str]:
    if not v: return None
    s = v.strip()
    try:
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                dd, mm, yyyy = parts
                return datetime(int(yyyy), int(mm), int(dd)).date().isoformat()
    except Exception: pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception: pass
    return s

@router.get("/dashboard/stats", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_pharmacy_dashboard_stats(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
):
    hospital_id = current.hospital_id
    now = datetime.utcnow()

    query = db.query(
        func.count(PharmacyMedicine.id).label('total'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity > 0, 1), else_=0
        )), 0).label('in_stock'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity < 10, 1), else_=0
        )), 0).label('low_stock'),
        func.coalesce(func.sum(
            PharmacyMedicine.quantity * PharmacyMedicine.selling_price
        ), 0).label('inventory_value'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.expiration_date <= now, 1), else_=0
        )), 0).label('expired'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity > 0, case(
                (or_(PharmacyMedicine.expiration_date.is_(None),
                     PharmacyMedicine.expiration_date > now), 1),
                else_=0
            )), else_=0
        )), 0).label('active'),
    ).filter(PharmacyMedicine.is_deleted.isnot(True))

    if hospital_id:
        query = query.filter(PharmacyMedicine.hospital_id == hospital_id)

    stats = query.first()

    return ok(data={
        "total_medicines": int(stats.total or 0),
        "active_medicines": int(stats.active or 0),
        "low_stock_items": int(stats.low_stock or 0),
        "expired_items": int(stats.expired or 0),
        "inventory_value": round(float(stats.inventory_value or 0), 2)
    })

@router.get("/reports/sales-summary", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_pharmacy_sales_summary(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
):
    hospital_id = current.hospital_id
    def _sum_sales(start: datetime, end: datetime) -> float:
        q = db.query(
            func.coalesce(func.sum(
                case(
                    (PharmacySale.total_amount.isnot(None), PharmacySale.total_amount),
                    else_=PharmacySale.total_price
                )
            ), 0)
        ).filter(PharmacySale.sold_at >= start, PharmacySale.sold_at < end)
        if hospital_id:
            q = q.filter(PharmacySale.hospital_id == hospital_id)
        return float(q.scalar() or 0)

    def _count_sales(start: datetime, end: datetime) -> int:
        q = db.query(func.count(PharmacySale.id)).filter(
            PharmacySale.sold_at >= start, PharmacySale.sold_at < end
        )
        if hospital_id:
            q = q.filter(PharmacySale.hospital_id == hospital_id)
        return int(q.scalar() or 0)

    def _pct_change(current: float, previous: float) -> float:
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    total_query = db.query(
        func.coalesce(func.sum(
            case(
                (PharmacySale.total_amount.isnot(None), PharmacySale.total_amount),
                else_=PharmacySale.total_price
            )
        ), 0).label('total_revenue'),
        func.count(PharmacySale.id).label('total_count')
    )
    if hospital_id:
        total_query = total_query.filter(PharmacySale.hospital_id == hospital_id)
    totals = total_query.first()

    now = datetime.utcnow()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    daily_revenue = _sum_sales(today_start, today_end)
    daily_count = _count_sales(today_start, today_end)

    days_since_monday = now.weekday()
    this_week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = this_week_start - timedelta(days=7)

    this_week_revenue = _sum_sales(this_week_start, now)
    last_week_revenue = _sum_sales(last_week_start, this_week_start)
    weekly_pct_change = _pct_change(this_week_revenue, last_week_revenue)

    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if this_month_start.month == 1:
        last_month_start = this_month_start.replace(year=this_month_start.year - 1, month=12)
    else:
        last_month_start = this_month_start.replace(month=this_month_start.month - 1)

    this_month_revenue = _sum_sales(this_month_start, now)
    last_month_revenue = _sum_sales(last_month_start, this_month_start)
    monthly_pct_change = _pct_change(this_month_revenue, last_month_revenue)

    return ok(data={
        "total_revenue": round(float(totals.total_revenue or 0), 2),
        "total_sales_count": totals.total_count or 0,
        "daily_revenue": round(daily_revenue, 2),
        "daily_sales_count": daily_count,
        "weekly_revenue": round(this_week_revenue, 2),
        "weekly_pct_change": weekly_pct_change,
        "weekly_trend": "up" if weekly_pct_change > 0 else ("down" if weekly_pct_change < 0 else "neutral"),
        "monthly_revenue": round(this_month_revenue, 2),
        "monthly_pct_change": monthly_pct_change,
        "monthly_trend": "up" if monthly_pct_change > 0 else ("down" if monthly_pct_change < 0 else "neutral"),
    })

@router.get("/reports/revenue-chart", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_revenue_chart_data(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    days: int = Query(7, ge=1, le=30)
):
    hospital_id = current.hospital_id

    now = datetime.utcnow()
    start_date = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    query = db.query(
        func.date(PharmacySale.sold_at).label('sale_date'),
        func.coalesce(func.sum(PharmacySale.total_price), 0).label('day_revenue'),
        func.count(PharmacySale.id).label('sales_count')
    ).filter(PharmacySale.sold_at >= start_date)
    
    if hospital_id:
        query = query.filter(PharmacySale.hospital_id == hospital_id)
    
    query = query.group_by(func.date(PharmacySale.sold_at))
    aggregated_sales = query.all()
    
    sales_map = {row.sale_date: {'revenue': float(row.day_revenue), 'count': row.sales_count} for row in aggregated_sales}
    
    chart_data = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        day_date = day.date()
        day_stats = sales_map.get(day_date, {'revenue': 0.0, 'count': 0})
        
        chart_data.append({
            "date": day.strftime("%Y-%m-%d"),
            "revenue": round(day_stats['revenue'], 2),
            "sales_count": day_stats['count']
        })
    
    return ok(data=chart_data)

@router.get("/sales/history", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_sales_history(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    hospital_id = current.hospital_id
    query = db.query(PharmacySale)
    if hospital_id:
        query = query.filter(PharmacySale.hospital_id == hospital_id)
    
    total = query.count()
    sales = query.order_by(PharmacySale.sold_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    
    results = []
    for s in sales:
        results.append({
            "id": s.id,
            "medicine_name": s.medicine_name,
            "quantity": s.quantity,
            "unit_price": s.unit_price,
            "total_price": s.total_price,
            "sold_at": s.sold_at.isoformat(),
            "payment_status": s.payment_status,
            "patient_id": s.patient_id,
            "doctor_id": s.doctor_id,
            "performed_by": s.performed_by
        })
        
    return ok(data=results, meta={"total": total, "page": page, "page_size": page_size})

@router.get("/external/pos/sales/history", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_pos_sales_history_alias(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return await get_sales_history(db, current, page, page_size)

@public_router.get("/search-medicine")
async def search_medicine(
    q: str = Query(..., description="Search by medicine name or generic name"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    terms = [t for t in q.strip().split() if t]
    
    query = db.query(PharmacyMedicine).filter(PharmacyMedicine.is_deleted.isnot(True))
    
    for term in terms:
        like_term = f"%{term}%"
        # [FIX] Numeric UUID resolution
        conditions = [
            PharmacyMedicine.name.ilike(like_term),
            PharmacyMedicine.generic_name.ilike(like_term)
        ]
        if term.isdigit():
            conditions.append(PharmacyMedicine.product_id == int(term))
            
        query = query.filter(or_(*conditions))
        
    medicines = query.all()

    results = []
    for m in medicines:
        data = {k: v for k, v in m.__dict__.items() if not k.startswith('_')}
        results.append({
            "product_id": data.get("product_id"),
            "name": data.get("name"),
            "generic_name": data.get("generic_name"),
            "selling_price": float(data.get("selling_price") or 0),
            "quantity": int(data.get("quantity") or 0),
            "expiration_date": data.get("expiration_date").isoformat() if data.get("expiration_date") else None,
            "low_stock": bool((data.get("quantity") or 0) < 5),
        })

    return {"results": results}

@public_router.post("/add-medicine")
async def public_add_medicine(
    payload: AddMedicineRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    # Prefer hospital_id from a logged-in user's JWT over whatever the body claims,
    # so a logged-in pharmacy user can never write into another hospital's inventory.
    user_hospital = payload.hospital_id
    if authorization:
        try:
            from app.security import verify_token
            token = authorization.replace("Bearer ", "").strip()
            token_payload = verify_token(token)
            if token_payload and token_payload.get("hospital_id"):
                user_hospital = str(token_payload.get("hospital_id")).strip()
        except Exception:
            pass
    
    # [FIX] Multi-tenant scoping and Native Upsert (ignores is_deleted to find ghosts)
    existing = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.product_id == payload.product_id,
        PharmacyMedicine.hospital_id == user_hospital
    ).first()

    exp_iso = _normalize_date_str(payload.expiration_date)
    exp_dt = None
    if exp_iso:
        try:
            exp_dt = datetime.fromisoformat(exp_iso)
        except (ValueError, TypeError):
            pass

    if existing:
        existing.batch_no = payload.batch_no
        existing.name = payload.name
        existing.generic_name = payload.generic_name
        existing.type = payload.type
        existing.distributor = payload.distributor or payload.supplier_name
        existing.distributor_company = payload.distributor_company
        existing.distributor_mobile = payload.distributor_mobile
        existing.purchase_price = payload.purchase_price
        existing.selling_price = payload.selling_price
        existing.stock_unit = payload.stock_unit
        existing.quantity = payload.quantity
        existing.expiration_date = exp_dt
        existing.category = payload.category
        existing.sub_category = payload.sub_category
        existing.manufacture_date = _normalize_date_str(payload.manufacture_date)
        existing.is_deleted = False # Instantly revive it from the trash
        existing.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing)
        await _broadcast_inventory_update(user_hospital)
        return ok(message="Medicine updated successfully", data={
            "id": existing.id,
            "product_id": existing.product_id,
            "batch_no": existing.batch_no,
            "name": existing.name,
            "generic_name": existing.generic_name,
            "type": existing.type,
            "distributor": existing.distributor,
            "supplier_name": payload.supplier_name or existing.distributor,
            "distributor_company": payload.distributor_company,
            "distributor_mobile": payload.distributor_mobile,
            "purchase_price": existing.purchase_price,
            "selling_price": existing.selling_price,
            "stock_unit": existing.stock_unit,
            "quantity": existing.quantity,
            "expiration_date": existing.expiration_date.isoformat() if existing.expiration_date else None,
            "manufacture_date": existing.manufacture_date,
            "category": existing.category,
            "sub_category": existing.sub_category,
            "hospital_id": existing.hospital_id,
        })
    new_med = PharmacyMedicine(
        id=str(uuid.uuid4()),
        product_id=payload.product_id,
        batch_no=payload.batch_no,
        name=payload.name,
        generic_name=payload.generic_name,
        type=payload.type,
        distributor=payload.distributor or payload.supplier_name,
        distributor_company=payload.distributor_company,
        distributor_mobile=payload.distributor_mobile,
        purchase_price=payload.purchase_price,
        selling_price=payload.selling_price,
        stock_unit=payload.stock_unit,
        quantity=payload.quantity,
        expiration_date=exp_dt,
        manufacture_date=_normalize_date_str(payload.manufacture_date),  # ✅ fixed — was missing
        category=payload.category,
        sub_category=payload.sub_category,
        hospital_id=user_hospital,
        created_at=datetime.utcnow()
    )
    db.add(new_med)
    db.commit()
    await _broadcast_inventory_update(user_hospital)
    return ok(message="Medicine added successfully", data={
        "id": new_med.id,
        "product_id": new_med.product_id,
        "batch_no": new_med.batch_no,
        "name": new_med.name,
        "generic_name": new_med.generic_name,
        "type": new_med.type,
        "distributor": new_med.distributor,
        "supplier_name": payload.supplier_name or new_med.distributor,
        "distributor_company": payload.distributor_company,
        "distributor_mobile": payload.distributor_mobile,
        "purchase_price": new_med.purchase_price,
        "selling_price": new_med.selling_price,
        "stock_unit": new_med.stock_unit,
        "quantity": new_med.quantity,
        "expiration_date": new_med.expiration_date.isoformat() if new_med.expiration_date else None,
        "manufacture_date": _normalize_date_str(payload.manufacture_date),
        "category": new_med.category,
        "sub_category": new_med.sub_category,
        "hospital_id": new_med.hospital_id,
    })

async def _sync_medicines_internal(db: Session, hospital_id: Optional[str] = None) -> Dict[str, int]:
    from app.services.pharmacy_inventory_service import list_medicines as list_legacy
    
    legacy_items = list_legacy(limit=1000)
    if not legacy_items:
        return {"synced": 0, "skipped": 0, "total_legacy": 0}

    existing_ids = {row[0] for row in db.query(PharmacyMedicine.product_id).all()}
    
    synced_count = 0
    skipped_count = 0
    
    for item in legacy_items:
        prod_id = item.get("product_id")
        if prod_id is None:
            continue
            
        prod_id_int = int(prod_id)
        if prod_id_int in existing_ids:
            skipped_count += 1
            continue
            
        new_med = PharmacyMedicine(
            id=str(item.get("id") or uuid.uuid4()),
            product_id=prod_id_int,
            batch_no=str(item.get("batch_no") or "LEGACY"),
            name=str(item.get("name") or "Unnamed"),
            generic_name=item.get("generic_name"),
            type=item.get("type"),
            distributor=item.get("distributor"),
            purchase_price=float(item.get("purchase_price") or 0),
            selling_price=float(item.get("selling_price") or 0),
            stock_unit=item.get("stock_unit"),
            quantity=int(item.get("quantity") or 0),
            expiration_date=item.get("expiration_date"),
            category=item.get("category"),
            sub_category=item.get("sub_category"),
            hospital_id=item.get("hospital_id") or hospital_id,
            created_at=item.get("created_at") or datetime.utcnow()
        )
        db.add(new_med)
        synced_count += 1
        
    if synced_count > 0:
        db.commit()
        await _broadcast_inventory_update(hospital_id)
        
    return {
        "synced": synced_count,
        "skipped": skipped_count,
        "total_legacy": len(legacy_items)
    }

@router.post("/sync-from-legacy", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def sync_medicines_from_legacy(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user)
) -> Any:
    result = await _sync_medicines_internal(db)
    return ok(data=result, message=f"Successfully imported {result['synced']} medicines from legacy storage")


@router.get("/medicines", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_all_medicines_staff(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=5000),  
) -> Dict[str, Any]:
    """Staff endpoint to get medicines for their hospital"""
    hid = current.hospital_id or ""
    
    cols = (
        PharmacyMedicine.id, PharmacyMedicine.product_id, PharmacyMedicine.batch_no,
        PharmacyMedicine.name, PharmacyMedicine.generic_name, PharmacyMedicine.type,
        PharmacyMedicine.distributor, PharmacyMedicine.distributor_company,
        PharmacyMedicine.distributor_mobile, PharmacyMedicine.purchase_price,
        PharmacyMedicine.selling_price, PharmacyMedicine.stock_unit,
        PharmacyMedicine.quantity, PharmacyMedicine.expiration_date,
        PharmacyMedicine.manufacture_date,
        PharmacyMedicine.category, PharmacyMedicine.sub_category,
        PharmacyMedicine.hospital_id, PharmacyMedicine.created_at,
        PharmacyMedicine.updated_at,
    )
    base = db.query(*cols).filter(PharmacyMedicine.is_deleted.isnot(True))
    if hid:
        base = base.filter(PharmacyMedicine.hospital_id == hid)
    
    if product_id is not None:
        base = base.filter(PharmacyMedicine.product_id == product_id)

    total = base.count()
    rows = base.order_by(PharmacyMedicine.name).offset((page-1)*page_size).limit(page_size).all()

    results = [
        {
            "id": r.id, "product_id": r.product_id, "batch_no": r.batch_no,
            "name": r.name, "generic_name": r.generic_name, "type": r.type,
            "distributor": r.distributor,
            "distributor_company": r.distributor_company,
            "distributor_mobile": r.distributor_mobile,
            "purchase_price": float(r.purchase_price or 0),
            "selling_price": float(r.selling_price or 0),
            "stock_unit": r.stock_unit,
            "quantity": int(r.quantity or 0),
            "low_stock": (r.quantity or 0) < 5,
            "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
            "manufacture_date": str(r.manufacture_date) if r.manufacture_date else None,
            "category": r.category, "sub_category": r.sub_category,
            "hospital_id": r.hospital_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]

    return ok(
        data=results,
        meta={
            "total": total, "page": page, "page_size": page_size,
            "hospital_id": hid,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1
        }
    )


@public_router.get("/medicines")
async def get_all_medicines(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=5000),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    # Silently derive hospital_id from a logged-in user's JWT if the
    # frontend didn't pass it explicitly as a query param.
    if not hospital_id and authorization:
        try:
            from app.security import verify_token
            token = authorization.replace("Bearer ", "").strip()
            payload = verify_token(token)
            if payload:
                hospital_id = str(payload.get("hospital_id") or "").strip() or None
        except Exception:
            pass

    cols = (
        PharmacyMedicine.id, PharmacyMedicine.product_id, PharmacyMedicine.batch_no,
        PharmacyMedicine.name, PharmacyMedicine.generic_name, PharmacyMedicine.type,
        PharmacyMedicine.distributor, PharmacyMedicine.distributor_company,
        PharmacyMedicine.distributor_mobile, PharmacyMedicine.purchase_price,
        PharmacyMedicine.selling_price, PharmacyMedicine.stock_unit,
        PharmacyMedicine.quantity, PharmacyMedicine.expiration_date,
        PharmacyMedicine.manufacture_date,
        PharmacyMedicine.category, PharmacyMedicine.sub_category,
        PharmacyMedicine.hospital_id, PharmacyMedicine.created_at,
        PharmacyMedicine.updated_at,
    )
    base = db.query(*cols).filter(PharmacyMedicine.is_deleted.isnot(True))
    if hospital_id:
        base = base.filter(PharmacyMedicine.hospital_id == hospital_id)
    
    if product_id is not None:
        base = base.filter(PharmacyMedicine.product_id == product_id)

    total = base.count()
    rows = base.order_by(PharmacyMedicine.name).offset((page-1)*page_size).limit(page_size).all()

    results = [
        {
            "id": r.id, "product_id": r.product_id, "batch_no": r.batch_no,
            "name": r.name, "generic_name": r.generic_name, "type": r.type,
            "distributor": r.distributor,
            "supplier_name": r.distributor,
            "distributor_company": r.distributor_company,
            "distributor_mobile": r.distributor_mobile,
            "purchase_price": float(r.purchase_price or 0),
            "selling_price": float(r.selling_price or 0),
            "stock_unit": r.stock_unit,
            "quantity": int(r.quantity or 0),
            "low_stock": (r.quantity or 0) < 5,
            "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
            "manufacture_date": str(r.manufacture_date) if r.manufacture_date else None,
            "category": r.category, "sub_category": r.sub_category,
            "hospital_id": r.hospital_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]

    return ok(
        data=results,
        meta={
            "total": total, "page": page, "page_size": page_size,
            "hospital_id": hospital_id,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1
        }
    )

@router.post("/dispense-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def dispense_medicine(
    payload: DispenseMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        for item in payload.medicines:
            med = db.query(PharmacyMedicine).filter(
                PharmacyMedicine.product_id == item.product_id,
                PharmacyMedicine.hospital_id == current.hospital_id
            ).with_for_update().first()
            
            if not med:
                raise HTTPException(status_code=404, detail=f"Medicine {item.product_id} not found")
            
            if med.quantity < item.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {med.name}")
            
            med.quantity -= item.quantity
            
            sale = PharmacySale(
                id=str(uuid.uuid4()),
                hospital_id=current.hospital_id,
                patient_id=payload.patient_id,
                doctor_id=payload.doctor_id,
                medicine_id=med.product_id,
                medicine_name=med.name,
                quantity=item.quantity,
                unit_price=med.selling_price,
                total_price=float(item.quantity * med.selling_price),
                sold_at=datetime.utcnow(),
                performed_by=current.user_id
            )
            db.add(sale)
        
        db.commit()

        # Real-time sync: a dispense changes shared pharmacy state (prescription
        # moves pending -> completed, stock levels drop). Notify all pharmacy
        # screens in this hospital so a colleague's open board refreshes.
        try:
            from app.routes.realtime import notify_queue_update
            await notify_queue_update(current.hospital_id, None)
        except Exception:
            pass

        return ok(message="Medicines dispensed successfully")
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException): raise e
        logger.exception("Dispense failed")
        raise HTTPException(status_code=500, detail="Dispense failed")


@router.get("/prescriptions", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_prescriptions(
    status: str = Query("pending", description="pending | completed | all"),
    department: Optional[str] = Query(None, description="Doctor department/specialization"),
    doctor_id: Optional[str] = Query(None, description="Doctor ID"),
    search: Optional[str] = Query(None, description="Search by patient name or token number"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    status_val = str(status or "pending").strip().lower()
    if status_val not in {"pending", "completed", "all"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status. Use pending, completed, or all")

    query = (
        db.query(Prescription, Token, Doctor, User)
        .outerjoin(Token, Token.id == Prescription.token_id)
        .outerjoin(Doctor, Doctor.id == Prescription.doctor_id)
        .outerjoin(User, User.id == Prescription.patient_id)
    )

    if current.hospital_id:
        query = query.filter(Prescription.hospital_id == current.hospital_id)

    if status_val != "all":
        query = query.filter(func.lower(func.coalesce(Prescription.dispense_status, "pending")) == status_val)

    if doctor_id:
        query = query.filter(Prescription.doctor_id == doctor_id)

    if department:
        dep = str(department).strip().lower()
        if dep:
            query = query.filter(func.lower(func.coalesce(Doctor.specialization, "")) == dep)

    if search:
        q = str(search).strip()
        if q:
            like = f"%{q}%"
            query = query.filter(or_(
                func.coalesce(Token.patient_name, "").ilike(like),
                func.coalesce(User.name, "").ilike(like),
                func.cast(func.coalesce(Token.token_number, 0), SQLString).ilike(like),
            ))

    rows = query.order_by(Prescription.created_at.desc()).limit(limit).all()

    data: List[Dict[str, Any]] = []
    for prescription, token, doctor, patient_user in rows:
        token_patient_name = getattr(token, "patient_name", None) if token else None
        patient_name = token_patient_name or (getattr(patient_user, "name", None) if patient_user else None)
        doctor_name = getattr(doctor, "name", None) if doctor else None
        token_number = getattr(token, "token_number", None) if token else None
        department_name = (getattr(doctor, "specialization", None) if doctor else None) or (getattr(token, "department", None) if token else None)

        data.append({
            "id": prescription.id,
            "token_id": prescription.token_id,
            "token_number": token_number,
            "doctor_id": prescription.doctor_id,
            "doctor_name": doctor_name,
            "department": department_name,
            "patient_id": prescription.patient_id,
            "patient_name": patient_name,
            "hospital_id": prescription.hospital_id,
            "medicines": prescription.medicines or [],
            "notes": prescription.notes,
            "dispense_status": prescription.dispense_status or "pending",
            "dispensed_at": prescription.dispensed_at.isoformat() if prescription.dispensed_at else None,
            "dispensed_by": prescription.dispensed_by,
            "created_at": prescription.created_at.isoformat() if prescription.created_at else None,
        })

    return ok(data=data)


@router.patch("/prescriptions/{prescription_id}/status", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_prescription_status(
    prescription_id: str,
    payload: PrescriptionStatusUpdateRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

    if current.hospital_id and row.hospital_id and str(row.hospital_id) != str(current.hospital_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    status_val = str(payload.status or "").strip().lower()
    if status_val not in {"pending", "completed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status. Use pending or completed")

    row.dispense_status = status_val
    if status_val == "completed":
        row.dispensed_at = datetime.utcnow()
        row.dispensed_by = current.user_id
    else:
        row.dispensed_at = None
        row.dispensed_by = None

    db.commit()
    db.refresh(row)

    # Real-time sync: another pharmacist's open prescription screen (dashboard
    # or prescriptions list) should refresh when this one is marked pending/
    # completed — otherwise the pending queue goes stale across pharmacy staff.
    try:
        from app.routes.realtime import notify_queue_update
        await notify_queue_update(current.hospital_id, None)
    except Exception:
        pass

    return ok(data=row.to_dict(), message=f"Prescription marked as {status_val}")
    

@router.post("/add-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def add_medicine(
    payload: AddMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    
    exp_dt = None
    if payload.expiration_date:
        try:
            if isinstance(payload.expiration_date, datetime):
                exp_dt = payload.expiration_date
            else:
                exp_iso = str(payload.expiration_date).strip()
                exp_dt = datetime.fromisoformat(exp_iso)
        except Exception:
            exp_dt = None
            logger.exception("Invalid expiration date format")

    # [FIX] Applied the same Soft-Delete ghost fix here as in the public router
    existing = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.product_id == int(payload.product_id),
        PharmacyMedicine.hospital_id == current.hospital_id
    ).first()
    
    if existing:
        existing.name = payload.name
        existing.generic_name = payload.generic_name
        existing.batch_no = payload.batch_no
        existing.quantity = payload.quantity
        existing.selling_price = payload.selling_price
        existing.purchase_price = payload.purchase_price
        existing.expiration_date = exp_dt  # ✅ use normalized exp_dt
        existing.manufacture_date = _normalize_date_str(payload.manufacture_date)  # ✅ fixed
        existing.category = payload.category
        existing.sub_category = payload.sub_category
        existing.type = payload.type
        existing.distributor = payload.distributor or payload.supplier_name
        existing.distributor_company = payload.distributor_company
        existing.distributor_mobile = payload.distributor_mobile
        existing.stock_unit = payload.stock_unit
        existing.updated_at = datetime.utcnow()
        existing.is_deleted = False
        db.commit()
        db.refresh(existing)
        await _broadcast_inventory_update(current.hospital_id)
        return ok(data={"id": existing.id, "product_id": existing.product_id},
            message="Medicine updated successfully"
        )

    new_med = PharmacyMedicine(
        id=str(uuid.uuid4()),
        product_id=payload.product_id,
        batch_no=payload.batch_no,
        name=payload.name,
        generic_name=payload.generic_name,
        type=payload.type,
        distributor=payload.distributor or payload.supplier_name,
        distributor_company=payload.distributor_company,
        distributor_mobile=payload.distributor_mobile,
        purchase_price=payload.purchase_price,
        selling_price=payload.selling_price,
        stock_unit=payload.stock_unit,
        quantity=payload.quantity,
        expiration_date=exp_dt,
        manufacture_date=_normalize_date_str(payload.manufacture_date),
        category=payload.category,
        sub_category=payload.sub_category,
        hospital_id=current.hospital_id, 
        created_at=datetime.utcnow()
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)
    await _broadcast_inventory_update(current.hospital_id)
    return ok(data={"id": new_med.id, "product_id": new_med.product_id},
        message="Medicine added successfully"
    )

@router.get("/items", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_items(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    q: Optional[str] = Query(None),
    search_param: Optional[str] = Query(None, alias="search"),
    is_deleted: Optional[bool] = Query(False),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> Any:
    hospital_id = current.hospital_id

    cols = (
        PharmacyMedicine.id, PharmacyMedicine.product_id, PharmacyMedicine.batch_no,
        PharmacyMedicine.name, PharmacyMedicine.generic_name, PharmacyMedicine.type,
        PharmacyMedicine.distributor, PharmacyMedicine.purchase_price,
        PharmacyMedicine.selling_price, PharmacyMedicine.stock_unit,
        PharmacyMedicine.quantity, PharmacyMedicine.expiration_date, PharmacyMedicine.manufacture_date,
        PharmacyMedicine.category, PharmacyMedicine.sub_category,
        PharmacyMedicine.hospital_id, PharmacyMedicine.created_at,
        PharmacyMedicine.updated_at, PharmacyMedicine.is_deleted,
    )
    
    base = db.query(*cols)
    if is_deleted or status == 'deleted' or status == 'trash':
        base = base.filter(PharmacyMedicine.is_deleted == True)
    else:
        base = base.filter(PharmacyMedicine.is_deleted.isnot(True))

    if hospital_id:
        base = base.filter(PharmacyMedicine.hospital_id == hospital_id)
        
    search_term = q or search_param
    if search_term:
        terms = [t for t in search_term.strip().split() if t]
        for term in terms:
            like_term = f"%{term}%"
            conditions = [
                PharmacyMedicine.name.ilike(like_term),
                PharmacyMedicine.generic_name.ilike(like_term),
                PharmacyMedicine.batch_no.ilike(like_term)
            ]
            if term.isdigit():
                conditions.append(PharmacyMedicine.product_id == int(term))
                
            base = base.filter(or_(*conditions))

    total = base.count()
    rows = base.order_by(PharmacyMedicine.updated_at.desc()).offset((page-1)*page_size).limit(page_size).all()

    results = [
        {
            "id": r.id, "product_id": r.product_id, "batch_no": r.batch_no,
            "name": r.name, "generic_name": r.generic_name, "type": r.type,
            "distributor": r.distributor,
            "purchase_price": float(r.purchase_price or 0),
            "selling_price": float(r.selling_price or 0),
            "stock_unit": r.stock_unit,
            "quantity": int(r.quantity or 0),
            "low_stock": (r.quantity or 0) < 5,
            "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
            "manufacture_date": str(r.manufacture_date) if r.manufacture_date else None,
            "category": r.category, "sub_category": r.sub_category,
            "hospital_id": r.hospital_id,
            "is_deleted": bool(r.is_deleted),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]

    return ok(data=results, meta={
        "page": page, "page_size": page_size, "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "has_next": page * page_size < total,
        "has_prev": page > 1
    })

@router.delete("/items/{item_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Any:
    med = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.id == item_id
    ).first()

    if med and current.hospital_id and med.hospital_id and med.hospital_id != current.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not med:
        try:
            med = db.query(PharmacyMedicine).filter(
                PharmacyMedicine.product_id == int(item_id),
                or_(
                    PharmacyMedicine.hospital_id == current.hospital_id,
                    PharmacyMedicine.hospital_id.is_(None)
                )
            ).first()
        except (ValueError, TypeError):
            pass

    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")

    deleted_name = med.name
    deleted_id = med.id

    med.is_deleted = True
    med.deleted_at = datetime.utcnow()

    if not med.hospital_id and current.hospital_id:
        med.hospital_id = current.hospital_id

    db.commit()
    await _broadcast_inventory_update(current.hospital_id)

    return ok(message=f"Medicine '{deleted_name}' deleted successfully", data={"deleted_id": deleted_id})

@router.patch("/items/{item_id}/restore", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def restore_item(
    item_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Any:
    med = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.id == item_id,
        or_(
            PharmacyMedicine.hospital_id == current.hospital_id,
            PharmacyMedicine.hospital_id.is_(None)
        )
    ).first()

    if not med:
        try:
            med = db.query(PharmacyMedicine).filter(
                PharmacyMedicine.product_id == int(item_id),
                or_(
                    PharmacyMedicine.hospital_id == current.hospital_id,
                    PharmacyMedicine.hospital_id.is_(None)
                )
            ).first()
        except (ValueError, TypeError):
            pass

    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")

    if not med.is_deleted:
        raise HTTPException(status_code=400, detail="Medicine is not deleted")

    med.is_deleted = False
    med.deleted_at = None
    med.updated_at = datetime.utcnow()

    if not med.hospital_id and current.hospital_id:
        med.hospital_id = current.hospital_id

    db.commit()
    await _broadcast_inventory_update(current.hospital_id)

    return ok(
        message=f"Medicine '{med.name}' restored successfully",
        data={"restored_id": med.id}
    )

# ═══════════════════════════════════════════════════════════════════════════════
#  PHARMACY INVOICES ROUTES
#  Append this entire block to the bottom of routes/pharmacy.py
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Also add this ONE import at the top of pharmacy.py alongside existing imports:
#
#  from db_automation.services import PharmacyInvoiceService
#
# ═══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional, List as _List


# ── Request / Response models ─────────────────────────────────────────────────

class InvoiceItemPayload(_BaseModel):
    medicine_id: _Optional[str] = None
    product_id: _Optional[int] = None
    product_name: str
    product_code: _Optional[str] = None
    quantity: float = 1
    unit_price: float
    discount: float = 0.0
    total: float


class CreateInvoiceRequest(_BaseModel):
    customer_id: _Optional[str] = None
    customer_name: str = "Walk in customer"
    payment_method: str = "cash"
    status: str = "pending"
    subtotal: float = 0.0
    discount: float = 0.0
    discount_percent: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    amount_paid: float = 0.0
    balance_due: float = 0.0
    notes: _Optional[str] = None
    items: _List[InvoiceItemPayload] = []


class UpdateInvoiceRequest(_BaseModel):
    customer_id: _Optional[str] = None
    customer_name: _Optional[str] = None
    payment_method: _Optional[str] = None
    status: _Optional[str] = None
    subtotal: _Optional[float] = None
    discount: _Optional[float] = None
    discount_percent: _Optional[float] = None
    tax: _Optional[float] = None
    total: _Optional[float] = None
    amount_paid: _Optional[float] = None
    balance_due: _Optional[float] = None
    notes: _Optional[str] = None
    items: _Optional[_List[InvoiceItemPayload]] = None


# ── GET /invoices ─────────────────────────────────────────────────────────────

@router.get("/invoices", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_invoices(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    status: _Optional[str] = Query(None, description="completed | pending | partial | cancelled"),
    search: _Optional[str] = Query(None, description="Search by invoice # or customer name"),
    payment_method: _Optional[str] = Query(None, description="cash | card | insurance | online"),
    date_from: _Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: _Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    h_id = getattr(current, "hospital_id", None)
    result = PharmacyInvoiceService.get_all_invoices(
        db=db,
        hospital_id=h_id,
        status=status,
        search=search,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )
    return ok(data=result)


# ── GET /invoices/trash ───────────────────────────────────────────────────────
# Returns soft-deleted invoices (Trash button in UI)

@router.get("/invoices/trash", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_invoice_trash(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
):
    h_id = getattr(current, "hospital_id", None)
    invoices = PharmacyInvoiceService.get_trash(db=db, hospital_id=h_id)

    if isinstance(invoices, dict) and "invoices" in invoices:
        for invoice in invoices["invoices"]:
            invoice["date"] = invoice.get("created_at")         # alias for frontend
            if not invoice.get("updated_at"):
                invoice["updated_at"] = invoice.get("created_at") # fix null updated_at
    
    return ok(data=invoices)


# ── GET /invoices/{invoice_id} ────────────────────────────────────────────────
# Full invoice detail with all line items (View button in UI)

@router.get("/invoices/{invoice_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
):
    invoice = PharmacyInvoiceService.get_invoice_by_id(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    data = invoice.to_dict()
    data["items"] = PharmacyInvoiceService.get_invoice_items(db=db, invoice_id=invoice_id)
    data["item_count"] = len(data["items"])

    # Add hospital info dynamically based on the invoice's hospital_id
    from app.db_models import Hospital
    hospital_id = data.get("hospital_id") or getattr(current, "hospital_id", None)
    if hospital_id:
        hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if hospital:
            data["hospital_name"] = hospital.name
            data["hospital_address"] = getattr(hospital, "address", None)
            data["hospital_phone"] = getattr(hospital, "phone", None)
            data["hospital_email"] = getattr(hospital, "email", None)
            data["hospital_logo"] = getattr(hospital, "logo_url", None)
        else:
            data["hospital_name"] = "Hospital"
            data["hospital_address"] = None
            data["hospital_phone"] = None
            data["hospital_email"] = None
            data["hospital_logo"] = None

    return ok(data=data)


# ── POST /invoices ────────────────────────────────────────────────────────────
# Create new invoice (New Invoice button in UI)

@router.post("/invoices", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def create_invoice(
    payload: CreateInvoiceRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
):
    # ✅ Recalculate totals from items if frontend sends 0
    if payload.items:
        calculated_subtotal = sum(
            float(item.unit_price or 0) * float(item.quantity or 1)
            for item in payload.items
        )
        calculated_total = calculated_subtotal - float(payload.discount or 0) + float(payload.tax or 0)
        # Only override if frontend sent 0
        if payload.subtotal == 0:
            payload.subtotal = round(calculated_subtotal, 2)
        if payload.total == 0:
            payload.total = round(calculated_total, 2)
        if payload.balance_due == 0:
            payload.balance_due = round(payload.total - float(payload.amount_paid or 0), 2)

    hospital_id = getattr(current, "hospital_id", None)

    # ✅ Validate stock availability BEFORE creating the invoice
    stock_errors = []
    for item in payload.items:
        if not item.product_id:
            continue
        med = db.query(PharmacyMedicine).filter(
            PharmacyMedicine.product_id == item.product_id,
            PharmacyMedicine.hospital_id == hospital_id,
            PharmacyMedicine.is_deleted.isnot(True),
        ).first()
        if not med:
            stock_errors.append(f"'{item.product_name}' not found in inventory")
        elif med.quantity < int(item.quantity or 1):
            stock_errors.append(f"'{med.name}' has only {med.quantity} units available, requested {int(item.quantity or 1)}")

    if stock_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Stock unavailable", "errors": stock_errors}
        )

    invoice = PharmacyInvoiceService.create_invoice(
        db=db,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        payment_method=payload.payment_method,
        status=payload.status,
        subtotal=payload.subtotal,
        discount=payload.discount,
        discount_percent=payload.discount_percent,
        tax=payload.tax,
        total=payload.total,
        amount_paid=payload.amount_paid,
        balance_due=payload.balance_due,
        notes=payload.notes,
        hospital_id=hospital_id,
        created_by=getattr(current, "user_id", None),
        items=[item.model_dump() for item in payload.items],
    )

   # ✅ Deduct stock and record sales AFTER invoice is created successfully
    try:
        for item in payload.items:
            if not item.product_id:
                continue
            med = db.query(PharmacyMedicine).filter(
                PharmacyMedicine.product_id == item.product_id,
                PharmacyMedicine.hospital_id == hospital_id,
                PharmacyMedicine.is_deleted.isnot(True),
            ).with_for_update().first()
            if med:
                med.quantity -= int(item.quantity or 1)
                med.updated_at = datetime.utcnow()

            sale = PharmacySale(
                id=str(uuid.uuid4()),
                hospital_id=hospital_id,
                medicine_id=item.product_id,
                medicine_name=item.product_name,
                quantity=int(item.quantity or 1),
                unit_price=float(item.unit_price or 0),
                total_price=float(item.total or 0),
                total_amount=float(item.total or 0),
                payment_status=payload.status or "pending",
                sold_at=datetime.utcnow(),
                performed_by=getattr(current, "user_id", None),
            )
            db.add(sale)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to deduct stock for invoice {invoice.id}: {e}")
        db.rollback()

    await _broadcast_inventory_update(hospital_id)

    invoice_data = invoice.to_dict()
    invoice_data["items"] = PharmacyInvoiceService.get_invoice_items(db=db, invoice_id=invoice.id)
    return ok(data=invoice_data, message="Invoice created successfully")


# ── PUT /invoices/{invoice_id} ────────────────────────────────────────────────
# Edit invoice (Edit button in UI)

@router.put("/invoices/{invoice_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_invoice(
    invoice_id: str,
    payload: UpdateInvoiceRequest,
    db: Session = Depends(get_db),
):
    updated_data = payload.model_dump(exclude_unset=True, exclude={"items"})
    items = [item.model_dump() for item in payload.items] if payload.items is not None else None

    invoice = PharmacyInvoiceService.update_invoice(
        db=db,
        invoice_id=invoice_id,
        updated_data=updated_data,
        items=items,
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    data = invoice.to_dict()
    data["items"] = PharmacyInvoiceService.get_invoice_items(db=db, invoice_id=invoice.id)
    data["item_count"] = len(data["items"])
    return ok(data=data, message="Invoice updated successfully")


# ── PATCH /invoices/{invoice_id}/status ──────────────────────────────────────
# Quick status change (e.g. mark as completed/cancelled)

@router.patch("/invoices/{invoice_id}/status", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_invoice_status(
    invoice_id: str,
    new_status: str = Query(..., description="completed | pending | partial | cancelled"),
    db: Session = Depends(get_db),
):
    invoice = PharmacyInvoiceService.update_status(db=db, invoice_id=invoice_id, new_status=new_status)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return ok(data=invoice.to_dict(), message=f"Status updated to '{new_status}'")

# ── DELETE /invoices/{invoice_id}/permanent ───────────────────────────────────
# Permanently delete from Trash (hard delete)

@router.delete("/invoices/{invoice_id}/permanent", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def permanent_delete_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    success = PharmacyInvoiceService.hard_delete_invoice(db=db, invoice_id=invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found in trash")
    return ok(message="Invoice permanently deleted")

# ── DELETE /invoices/{invoice_id} ─────────────────────────────────────────────
# Soft delete → moves to Trash

@router.delete("/invoices/{invoice_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    success = PharmacyInvoiceService.soft_delete_invoice(db=db, invoice_id=invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return ok(message="Invoice moved to trash")


# ── POST /invoices/{invoice_id}/restore ──────────────────────────────────────
# Restore invoice from Trash

@router.post("/invoices/{invoice_id}/restore", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def restore_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
):
    invoice = PharmacyInvoiceService.restore_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found in trash")
    return ok(data=invoice.to_dict(), message="Invoice restored successfully")

# ═══════════════════════════════════════════════════════════════════════════════
#  SALES & REVENUE PAGE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_date_range(
    preset: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str]
) -> Tuple[datetime, datetime]:
    """Resolve date range from preset or explicit from/to dates."""
    now = datetime.utcnow()
    if preset == "last_7_days":
        return now - timedelta(days=7), now
    elif preset == "this_month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    elif preset == "last_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_prev = first_this - timedelta(seconds=1)
        first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return first_prev, last_prev
    elif from_date and to_date:
        return datetime.fromisoformat(from_date), datetime.fromisoformat(to_date)
    else:
        # Default: last 30 days
        return now - timedelta(days=30), now


# ── GET /sales/overview ───────────────────────────────────────────────────────
# Overview tab — Total Revenue, Invoices, Units Sold, Avg Order Value

@router.get("/sales/overview", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_sales_overview(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    preset: Optional[str] = Query("last_30_days", description="last_7_days | last_30_days | this_month | last_month"),
    from_date: Optional[str] = Query(None, description="ISO date e.g. 2026-04-01"),
    to_date: Optional[str] = Query(None, description="ISO date e.g. 2026-05-09"),
):
    h_id = getattr(current, "hospital_id", None)
    start, end = _resolve_date_range(preset, from_date, to_date)

    sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == h_id,
        PharmacySale.payment_status != "cancelled",
        PharmacySale.sold_at >= start,
        PharmacySale.sold_at <= end,
    ).all()

    total_revenue = sum((s.total_amount or s.total_price or 0) for s in sales)
    total_invoices = len(sales)
    units_sold = sum((s.quantity or 0) for s in sales)
    avg_order_value = round(total_revenue / total_invoices, 2) if total_invoices > 0 else 0.0

    return ok(data={
        "total_revenue": round(total_revenue, 2),
        "invoices": total_invoices,
        "units_sold": units_sold,
        "avg_order_value": avg_order_value,
        "period": {
            "from": start.isoformat(),
            "to": end.isoformat()
        }
    })


# ── GET /sales/over-time ──────────────────────────────────────────────────────
# Overview tab — "Sales over time" chart (daily breakdown)

@router.get("/sales/over-time", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_sales_over_time(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    preset: Optional[str] = Query("last_30_days"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    h_id = getattr(current, "hospital_id", None)
    start, end = _resolve_date_range(preset, from_date, to_date)

    rows = db.query(
        func.date(PharmacySale.sold_at).label("date"),
        func.coalesce(func.sum(
            case((PharmacySale.total_amount.isnot(None), PharmacySale.total_amount),
                 else_=PharmacySale.total_price)
        ), 0).label("revenue"),
        func.count(PharmacySale.id).label("invoices")
    ).filter(
        PharmacySale.hospital_id == h_id,
        PharmacySale.payment_status != "cancelled",
        PharmacySale.sold_at >= start,
        PharmacySale.sold_at <= end,
    ).group_by(
        func.date(PharmacySale.sold_at)
    ).order_by(
        func.date(PharmacySale.sold_at)
    ).all()

    return ok(data=[
        {
            "date": str(row.date),
            "revenue": round(float(row.revenue or 0), 2),
            "invoices": row.invoices
        }
        for row in rows
    ])


# ── GET /sales/payment-methods ────────────────────────────────────────────────
# Overview tab — "Payment method" breakdown (Cash, Card, Online)

@router.get("/sales/payment-methods", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_payment_method_breakdown(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    preset: Optional[str] = Query("last_30_days"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    h_id = getattr(current, "hospital_id", None)
    start, end = _resolve_date_range(preset, from_date, to_date)

    sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == h_id,
        PharmacySale.payment_status != "cancelled",
        PharmacySale.sold_at >= start,
        PharmacySale.sold_at <= end,
    ).all()

    breakdown: Dict[str, float] = {"cash": 0.0, "card": 0.0, "online": 0.0}

    for s in sales:
        method = "cash"  # default
        if isinstance(s.items, dict):
            method = str(s.items.get("payment_method", "cash")).lower()
        elif isinstance(s.items, list) and s.items:
            method = str(s.items[0].get("payment_method", "cash")).lower()
        if method not in breakdown:
            method = "cash"
        breakdown[method] += (s.total_amount or s.total_price or 0)

    total = sum(breakdown.values())
    return ok(data={
        "breakdown": [
            {
                "method": k,
                "amount": round(v, 2),
                "percentage": round((v / total * 100), 1) if total > 0 else 0
            }
            for k, v in breakdown.items()
        ],
        "total": round(total, 2)
    })


# ── GET /sales/top-medicines ──────────────────────────────────────────────────
# Products tab — Top selling medicines

@router.get("/sales/top-medicines", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_top_selling_medicines(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    preset: Optional[str] = Query("last_30_days"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    h_id = getattr(current, "hospital_id", None)
    start, end = _resolve_date_range(preset, from_date, to_date)

    rows = db.query(
        PharmacySale.medicine_name,
        func.coalesce(func.sum(PharmacySale.quantity), 0).label("units_sold"),
        func.coalesce(func.sum(
            case((PharmacySale.total_amount.isnot(None), PharmacySale.total_amount),
                 else_=PharmacySale.total_price)
        ), 0).label("revenue"),
        func.coalesce(func.sum(
            PharmacySale.unit_price * PharmacySale.quantity
        ), 0).label("total_selling"),
        func.count(PharmacySale.id).label("transactions")
    ).filter(
        PharmacySale.hospital_id == h_id,
        PharmacySale.payment_status != "cancelled",
        PharmacySale.medicine_name.isnot(None),
        PharmacySale.sold_at >= start,
        PharmacySale.sold_at <= end,
    ).group_by(
        PharmacySale.medicine_name
    ).order_by(
        func.sum(PharmacySale.quantity).desc()
    ).limit(limit).all()

    # Join with PharmacyMedicine to get purchase_price for profit calculation
    result = []
    for row in rows:
        medicine = db.query(PharmacyMedicine).filter(
            PharmacyMedicine.name == row.medicine_name,
            PharmacyMedicine.hospital_id == h_id,
            PharmacyMedicine.is_deleted.isnot(True)
        ).first()

        purchase_price = float(medicine.purchase_price or 0) if medicine else 0.0
        units_sold = int(row.units_sold or 0)
        revenue = round(float(row.revenue or 0), 2)
        cost = round(purchase_price * units_sold, 2)
        profit = round(revenue - cost, 2)

        result.append({
            "medicine_name": row.medicine_name,
            "units_sold": units_sold,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "transactions": row.transactions
        })

    return ok(data=result)


# ── GET /sales/export ─────────────────────────────────────────────────────────
# Export Excel button

@router.get("/sales/export", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def export_sales_excel(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    preset: Optional[str] = Query("last_30_days"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    import openpyxl
    from io import BytesIO

    h_id = getattr(current, "hospital_id", None)
    start, end = _resolve_date_range(preset, from_date, to_date)

    sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == h_id,
        PharmacySale.payment_status != "cancelled",
        PharmacySale.sold_at >= start,
        PharmacySale.sold_at <= end,
    ).order_by(PharmacySale.sold_at.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales & Revenue"
    ws.append(["ID", "Medicine", "Quantity", "Unit Price", "Total Amount", "Payment Status", "Sold At"])

    for s in sales:
        ws.append([
            s.id,
            s.medicine_name or "N/A",
            s.quantity or 0,
            s.unit_price or 0,
            s.total_amount or s.total_price or 0,
            s.payment_status,
            s.sold_at.isoformat() if s.sold_at else ""
        ])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"sales_{start.date()}_to_{end.date()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

class UpdateMedicineRequest(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    batch_no: Optional[str] = None
    quantity: Optional[int] = None
    selling_price: Optional[float] = None
    purchase_price: Optional[float] = None
    expiration_date: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    type: Optional[str] = None
    distributor: Optional[str] = None
    stock_unit: Optional[str] = None

@public_router.delete("/medicines/{medicine_id}")
async def delete_medicine_public(
    medicine_id: str,
    hospital_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    # Silently derive hospital_id from JWT if not explicitly passed, so a
    # logged-in pharmacy user can't accidentally/intentionally delete another hospital's medicine.
    if not hospital_id and authorization:
        try:
            from app.security import verify_token
            token = authorization.replace("Bearer ", "").strip()
            payload = verify_token(token)
            if payload:
                hospital_id = str(payload.get("hospital_id") or "").strip() or None
        except Exception:
            pass

    # Try by UUID first
    med = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.id == medicine_id,
        PharmacyMedicine.is_deleted.isnot(True)
    ).first()

    # Try by product_id if UUID not found
    if not med:
        try:
            med = db.query(PharmacyMedicine).filter(
                PharmacyMedicine.product_id == int(medicine_id),
                PharmacyMedicine.is_deleted.isnot(True)
            ).first()
        except (ValueError, TypeError):
            pass

    # Try with hospital_id filter
    if not med and hospital_id:
        med = db.query(PharmacyMedicine).filter(
            PharmacyMedicine.hospital_id == hospital_id,
            PharmacyMedicine.is_deleted.isnot(True)
        ).filter(
            (PharmacyMedicine.id == medicine_id) |
            (PharmacyMedicine.product_id == int(medicine_id) if medicine_id.isdigit() else False)
        ).first()

    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")

    if hospital_id and med.hospital_id and med.hospital_id != hospital_id:
        raise HTTPException(status_code=403, detail="Access denied: medicine belongs to a different hospital")

    med.is_deleted = True
    med.deleted_at = datetime.utcnow()
    db.commit()
    await _broadcast_inventory_update(med.hospital_id)

    return ok(
        message=f"Medicine '{med.name}' deleted successfully",
        data={"deleted_id": med.id, "product_id": med.product_id}
    )

@public_router.put("/medicines/{medicine_id}")
async def update_medicine_public(
    medicine_id: str,
    payload: UpdateMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    med = db.query(PharmacyMedicine).filter(
        PharmacyMedicine.id == medicine_id,
        PharmacyMedicine.hospital_id == getattr(current, "hospital_id", None)
    ).first()

    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(med, field, value)

    med.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(med)
    await _broadcast_inventory_update(getattr(current, "hospital_id", None))
    return ok(message="Medicine updated successfully", data={"id": med.id})

# ═══════════════════════════════════════════════════════════════════════════════
#  PHARMACY PRESCRIPTION REPORT - PDF DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/reports/prescriptions/pdf", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def download_prescription_report_pdf(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    preset: Optional[str] = Query(None, description="today | this_week | this_month"),
):
    h_id = getattr(current, "hospital_id", None)

    # Resolve date range
    now = datetime.utcnow()
    if preset == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        period_label = f"Daily Report — {now.strftime('%d %b %Y')}"
    elif preset == "this_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        period_label = f"Weekly Report — {start.strftime('%d %b')} to {now.strftime('%d %b %Y')}"
    elif preset == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        period_label = f"Monthly Report — {now.strftime('%B %Y')}"
    elif from_date and to_date:
        start = datetime.fromisoformat(from_date)
        end = datetime.fromisoformat(to_date).replace(hour=23, minute=59, second=59)
        period_label = f"Report — {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        period_label = f"Monthly Report — {now.strftime('%B %Y')}"

    # Fetch prescriptions with patient and doctor info
    from sqlalchemy import and_
    prescriptions = db.query(Prescription).filter(
        Prescription.hospital_id == h_id,
        Prescription.created_at >= start,
        Prescription.created_at <= end,
    ).order_by(Prescription.created_at.desc()).all()

    # Fetch hospital name
    from app.db_models import Hospital
    hospital = db.query(Hospital).filter(Hospital.id == h_id).first()
    hospital_name = hospital.name if hospital else "Hospital"

    # Build PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, spaceAfter=4, alignment=TA_CENTER, textColor=colors.grey)
    heading_style = ParagraphStyle('Heading', parent=styles['Normal'], fontSize=11, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor('#1a1a2e'), fontName='Helvetica-Bold')
    normal_style = ParagraphStyle('Normal2', parent=styles['Normal'], fontSize=9)

    elements = []

    # Header
    elements.append(Paragraph(hospital_name, title_style))
    elements.append(Paragraph("Prescription Report", subtitle_style))
    elements.append(Paragraph(period_label, subtitle_style))
    elements.append(Paragraph(f"Generated: {now.strftime('%d %b %Y, %I:%M %p')}", subtitle_style))
    elements.append(Spacer(1, 0.5*cm))

    # Summary
    elements.append(Paragraph(f"Total Prescriptions: {len(prescriptions)}", heading_style))
    elements.append(Spacer(1, 0.3*cm))

    if not prescriptions:
        elements.append(Paragraph("No prescriptions found for the selected period.", normal_style))
    else:
        for i, presc in enumerate(prescriptions, 1):
            # Fetch patient and doctor names
            from app.db_models import User, Doctor, Token
            patient = db.query(User).filter(User.id == presc.patient_id).first()
            doctor = db.query(Doctor).filter(Doctor.id == presc.doctor_id).first()
            token = db.query(Token).filter(Token.id == presc.token_id).first()

            patient_name = patient.name if patient else "Unknown"
            doctor_name = doctor.name if doctor else "Unknown"
            mrn = token.mrn if token else "N/A"
            date_str = presc.created_at.strftime('%d %b %Y, %I:%M %p') if presc.created_at else "N/A"

            # Patient info block
            elements.append(Paragraph(
                f"#{i} — {patient_name} &nbsp;&nbsp; MRN: {mrn} &nbsp;&nbsp; Doctor: {doctor_name} &nbsp;&nbsp; Date: {date_str}",
                heading_style
            ))

            # Medicines table
            medicines = presc.medicines or []
            if medicines:
                table_data = [["#", "Medicine", "Generic Name", "Dosage", "Instructions"]]
                for j, med in enumerate(medicines, 1):
                    table_data.append([
                        str(j),
                        str(med.get("name") or ""),
                        str(med.get("generic_name") or ""),
                        str(med.get("dosage") or ""),
                        str(med.get("instructions") or ""),
                    ])

                col_widths = [1*cm, 4*cm, 4*cm, 3*cm, 5.5*cm]
                table = Table(table_data, colWidths=col_widths, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('PADDING', (0, 0), (-1, -1), 6),
                ]))
                elements.append(table)
            else:
                elements.append(Paragraph("No medicines prescribed.", normal_style))

            # Notes
            if presc.notes:
                elements.append(Paragraph(f"Notes: {presc.notes}", normal_style))

            elements.append(Spacer(1, 0.4*cm))

    doc.build(elements)
    buffer.seek(0)

    filename = f"prescription_report_{now.strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
