"""Pharmacy Expense & Credit ledger endpoints.

Mounted under the same prefix as the pharmacy portal (/api/v1/staff/pharmacy),
so the frontend reaches these at e.g. /api/v1/staff/pharmacy/expenses.

- Expense  : internal medicine/drip requests demanded by hospital staff.
- Credit   : credit sales to known customers, with partial payment history.

All endpoints are scoped to the caller's hospital_id (multi-tenant) and require
the `pharmacy` or `admin` role, matching the rest of the pharmacy portal.
"""
from typing import Any, Dict, Optional, List
from datetime import datetime
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TokenData
from app.security import get_current_active_user, require_roles
from app.db_models import PharmacyExpense, PharmacyCredit, PharmacyCreditPayment, PharmacyDistributor
from app.utils.responses import ok

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse a date / datetime string from the frontend. Returns None if blank/invalid."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try common formats: ISO, date-only, dd-MM-yyyy
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:len(fmt) + 4] if "T" in fmt else s[:10], fmt)
        except (ValueError, TypeError):
            continue
    try:
        # Last resort: fromisoformat (handles offsets)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _next_serial(db: Session, model, hospital_id: Optional[str]) -> int:
    """Per-hospital running serial number for the given model."""
    q = db.query(func.max(model.serial_no))
    if hospital_id:
        q = q.filter(model.hospital_id == hospital_id)
    current = q.scalar() or 0
    return int(current) + 1


def _credit_status(total: float, paid: float) -> str:
    if paid <= 0:
        return "pending"
    if paid >= total:
        return "cleared"
    return "partially_paid"


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class ExpenseCreate(BaseModel):
    expense_date: Optional[str] = None
    demanded_by: Optional[str] = None
    department: Optional[str] = None
    item_name: str = Field(..., min_length=1)
    quantity: float = Field(1, ge=0)
    unit_price: float = Field(0, ge=0)
    issued_by: Optional[str] = None
    status: str = "pending"
    notes: Optional[str] = None


class ExpenseUpdate(BaseModel):
    expense_date: Optional[str] = None
    demanded_by: Optional[str] = None
    department: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    issued_by: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class CreditCreate(BaseModel):
    purchase_date: Optional[str] = None
    customer_name: str = Field(..., min_length=1)
    contact_number: Optional[str] = None
    item_name: str = Field(..., min_length=1)
    quantity: float = Field(1, ge=0)
    unit_price: float = Field(0, ge=0)
    amount_paid: float = Field(0, ge=0)
    due_date: Optional[str] = None
    notes: Optional[str] = None


class CreditUpdate(BaseModel):
    purchase_date: Optional[str] = None
    customer_name: Optional[str] = None
    contact_number: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount_paid: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class CreditPaymentCreate(BaseModel):
    amount: float = Field(..., gt=0)
    payment_date: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class DistributorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None


class DistributorUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════════════
# EXPENSE MODULE
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/expenses", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_expenses(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    demanded_by: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    hid = current.hospital_id
    q = db.query(PharmacyExpense).filter(PharmacyExpense.is_deleted.isnot(True))
    if hid:
        q = q.filter(PharmacyExpense.hospital_id == hid)

    df = _parse_dt(date_from)
    dt = _parse_dt(date_to)
    if df:
        q = q.filter(PharmacyExpense.expense_date >= df)
    if dt:
        # inclusive end-of-day
        q = q.filter(PharmacyExpense.expense_date <= dt.replace(hour=23, minute=59, second=59))
    if department:
        q = q.filter(PharmacyExpense.department.ilike(f"%{department}%"))
    if demanded_by:
        q = q.filter(PharmacyExpense.demanded_by.ilike(f"%{demanded_by}%"))
    if status_filter and status_filter.lower() != "all":
        q = q.filter(PharmacyExpense.status == status_filter.lower())
    if search:
        like = f"%{search}%"
        q = q.filter(
            PharmacyExpense.item_name.ilike(like)
            | PharmacyExpense.demanded_by.ilike(like)
            | PharmacyExpense.department.ilike(like)
        )

    rows = q.order_by(PharmacyExpense.serial_no.desc()).all()
    data = [r.to_dict() for r in rows]
    total_expense = sum((r.total_price or 0) for r in rows)
    return ok(
        data=data,
        meta={
            "count": len(data),
            "total_expense": round(total_expense, 2),
            "hospital_id": hid,
        },
    )


@router.post("/expenses", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        hid = current.hospital_id
        total = round((payload.quantity or 0) * (payload.unit_price or 0), 2)
        row = PharmacyExpense(
            id=str(uuid.uuid4()),
            serial_no=_next_serial(db, PharmacyExpense, hid),
            hospital_id=hid,
            expense_date=_parse_dt(payload.expense_date) or datetime.utcnow(),
            demanded_by=payload.demanded_by,
            department=payload.department,
            item_name=payload.item_name,
            quantity=payload.quantity or 0,
            unit_price=payload.unit_price or 0,
            total_price=total,
            issued_by=payload.issued_by,
            status=(payload.status or "pending").lower(),
            notes=payload.notes,
            created_by=current.user_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(), message="Expense recorded successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to create expense")
        raise HTTPException(status_code=500, detail="Failed to record expense")


@router.put("/expenses/{expense_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyExpense).filter(PharmacyExpense.id == expense_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    try:
        data = payload.model_dump(exclude_unset=True)
        if "expense_date" in data:
            row.expense_date = _parse_dt(data.pop("expense_date")) or row.expense_date
        if "status" in data and data["status"]:
            data["status"] = str(data["status"]).lower()
        for key, value in data.items():
            setattr(row, key, value)
        # Recompute total
        row.total_price = round((row.quantity or 0) * (row.unit_price or 0), 2)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(), message="Expense updated successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to update expense")
        raise HTTPException(status_code=500, detail="Failed to update expense")


@router.delete("/expenses/{expense_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyExpense).filter(PharmacyExpense.id == expense_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    try:
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.commit()
        return ok(message="Expense deleted successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to delete expense")
        raise HTTPException(status_code=500, detail="Failed to delete expense")


# ═════════════════════════════════════════════════════════════════════════════
# CREDIT MODULE
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/credits", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_credits(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    customer: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    hid = current.hospital_id
    q = db.query(PharmacyCredit).filter(PharmacyCredit.is_deleted.isnot(True))
    if hid:
        q = q.filter(PharmacyCredit.hospital_id == hid)
    if customer:
        q = q.filter(PharmacyCredit.customer_name.ilike(f"%{customer}%"))
    if status_filter and status_filter.lower() != "all":
        q = q.filter(PharmacyCredit.status == status_filter.lower())
    if search:
        like = f"%{search}%"
        q = q.filter(
            PharmacyCredit.customer_name.ilike(like)
            | PharmacyCredit.item_name.ilike(like)
            | PharmacyCredit.contact_number.ilike(like)
        )

    rows = q.order_by(PharmacyCredit.serial_no.desc()).all()
    data = [r.to_dict() for r in rows]
    return ok(
        data=data,
        meta={
            "count": len(data),
            "total_credit": round(sum((r.total_amount or 0) for r in rows), 2),
            "total_paid": round(sum((r.amount_paid or 0) for r in rows), 2),
            "total_balance": round(sum((r.balance or 0) for r in rows), 2),
            "hospital_id": hid,
        },
    )


@router.get("/credits/summary", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def credit_customer_summary(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Per-customer credit summary: total credit, total paid, total balance."""
    hid = current.hospital_id
    q = db.query(
        PharmacyCredit.customer_name.label("customer_name"),
        func.max(PharmacyCredit.contact_number).label("contact_number"),
        func.count(PharmacyCredit.id).label("entries"),
        func.coalesce(func.sum(PharmacyCredit.total_amount), 0).label("total_credit"),
        func.coalesce(func.sum(PharmacyCredit.amount_paid), 0).label("total_paid"),
        func.coalesce(func.sum(PharmacyCredit.balance), 0).label("total_balance"),
    ).filter(PharmacyCredit.is_deleted.isnot(True))
    if hid:
        q = q.filter(PharmacyCredit.hospital_id == hid)
    q = q.group_by(PharmacyCredit.customer_name).order_by(func.sum(PharmacyCredit.balance).desc())

    data = [
        {
            "customer_name": r.customer_name,
            "contact_number": r.contact_number,
            "entries": int(r.entries or 0),
            "total_credit": round(float(r.total_credit or 0), 2),
            "total_paid": round(float(r.total_paid or 0), 2),
            "total_balance": round(float(r.total_balance or 0), 2),
        }
        for r in q.all()
    ]
    return ok(data=data, meta={"count": len(data), "hospital_id": hid})


@router.get("/credits/{credit_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_credit(
    credit_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyCredit).filter(PharmacyCredit.id == credit_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Credit entry not found")
    return ok(data=row.to_dict(include_payments=True))


@router.post("/credits", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def create_credit(
    payload: CreditCreate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        hid = current.hospital_id
        total = round((payload.quantity or 0) * (payload.unit_price or 0), 2)
        paid = round(payload.amount_paid or 0, 2)
        balance = round(total - paid, 2)
        credit = PharmacyCredit(
            id=str(uuid.uuid4()),
            serial_no=_next_serial(db, PharmacyCredit, hid),
            hospital_id=hid,
            purchase_date=_parse_dt(payload.purchase_date) or datetime.utcnow(),
            customer_name=payload.customer_name,
            contact_number=payload.contact_number,
            item_name=payload.item_name,
            quantity=payload.quantity or 0,
            unit_price=payload.unit_price or 0,
            total_amount=total,
            amount_paid=paid,
            balance=balance,
            due_date=_parse_dt(payload.due_date),
            status=_credit_status(total, paid),
            notes=payload.notes,
            created_by=current.user_id,
            created_at=datetime.utcnow(),
        )
        db.add(credit)
        db.flush()
        # If an initial payment was provided, record it in the history too.
        if paid > 0:
            db.add(PharmacyCreditPayment(
                id=str(uuid.uuid4()),
                credit_id=credit.id,
                amount=paid,
                payment_date=credit.purchase_date,
                payment_method="initial",
                notes="Initial payment at credit creation",
                created_by=current.user_id,
                created_at=datetime.utcnow(),
            ))
        db.commit()
        db.refresh(credit)
        return ok(data=credit.to_dict(include_payments=True), message="Credit entry created successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to create credit entry")
        raise HTTPException(status_code=500, detail="Failed to create credit entry")


@router.put("/credits/{credit_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_credit(
    credit_id: str,
    payload: CreditUpdate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyCredit).filter(PharmacyCredit.id == credit_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Credit entry not found")
    try:
        data = payload.model_dump(exclude_unset=True)
        if "purchase_date" in data:
            row.purchase_date = _parse_dt(data.pop("purchase_date")) or row.purchase_date
        if "due_date" in data:
            row.due_date = _parse_dt(data.pop("due_date"))
        for key, value in data.items():
            setattr(row, key, value)
        # Recompute totals & status
        row.total_amount = round((row.quantity or 0) * (row.unit_price or 0), 2)
        row.balance = round(row.total_amount - (row.amount_paid or 0), 2)
        row.status = _credit_status(row.total_amount, row.amount_paid or 0)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(include_payments=True), message="Credit entry updated successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to update credit entry")
        raise HTTPException(status_code=500, detail="Failed to update credit entry")


@router.post("/credits/{credit_id}/payments", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def add_credit_payment(
    credit_id: str,
    payload: CreditPaymentCreate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyCredit).filter(PharmacyCredit.id == credit_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Credit entry not found")

    amount = round(payload.amount or 0, 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if amount > (row.balance or 0) + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Payment ({amount}) exceeds remaining balance ({row.balance})",
        )
    try:
        db.add(PharmacyCreditPayment(
            id=str(uuid.uuid4()),
            credit_id=row.id,
            amount=amount,
            payment_date=_parse_dt(payload.payment_date) or datetime.utcnow(),
            payment_method=payload.payment_method,
            notes=payload.notes,
            created_by=current.user_id,
            created_at=datetime.utcnow(),
        ))
        row.amount_paid = round((row.amount_paid or 0) + amount, 2)
        row.balance = round((row.total_amount or 0) - row.amount_paid, 2)
        row.status = _credit_status(row.total_amount or 0, row.amount_paid)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(include_payments=True), message="Payment recorded successfully")
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Failed to record payment")
        raise HTTPException(status_code=500, detail="Failed to record payment")


@router.delete("/credits/{credit_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_credit(
    credit_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyCredit).filter(PharmacyCredit.id == credit_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Credit entry not found")
    try:
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.commit()
        return ok(message="Credit entry deleted successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to delete credit entry")
        raise HTTPException(status_code=500, detail="Failed to delete credit entry")


# ═════════════════════════════════════════════════════════════════════════════
# DISTRIBUTOR MODULE  (medicine distributors / suppliers registry)
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/distributors", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_distributors(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
) -> Dict[str, Any]:
    hid = current.hospital_id
    q = db.query(PharmacyDistributor).filter(PharmacyDistributor.is_deleted.isnot(True))
    if hid:
        q = q.filter(PharmacyDistributor.hospital_id == hid)
    if status_filter and status_filter.lower() != "all":
        q = q.filter(PharmacyDistributor.status == status_filter.lower())
    if search:
        like = f"%{search}%"
        q = q.filter(
            PharmacyDistributor.name.ilike(like)
            | PharmacyDistributor.company.ilike(like)
            | PharmacyDistributor.phone.ilike(like)
            | PharmacyDistributor.city.ilike(like)
        )

    rows = q.order_by(PharmacyDistributor.serial_no.desc()).all()
    data = [r.to_dict() for r in rows]
    return ok(
        data=data,
        meta={
            "count": len(data),
            "active": sum(1 for r in rows if (r.status or "").lower() == "active"),
            "hospital_id": hid,
        },
    )


@router.post("/distributors", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def create_distributor(
    payload: DistributorCreate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        hid = current.hospital_id
        row = PharmacyDistributor(
            id=str(uuid.uuid4()),
            serial_no=_next_serial(db, PharmacyDistributor, hid),
            hospital_id=hid,
            name=payload.name,
            company=payload.company,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            city=payload.city,
            status=(payload.status or "active").lower(),
            notes=payload.notes,
            created_by=current.user_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(), message="Distributor added successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to create distributor")
        raise HTTPException(status_code=500, detail="Failed to add distributor")


@router.put("/distributors/{distributor_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def update_distributor(
    distributor_id: str,
    payload: DistributorUpdate,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyDistributor).filter(PharmacyDistributor.id == distributor_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Distributor not found")
    try:
        data = payload.model_dump(exclude_unset=True)
        if "status" in data and data["status"]:
            data["status"] = str(data["status"]).lower()
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return ok(data=row.to_dict(), message="Distributor updated successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to update distributor")
        raise HTTPException(status_code=500, detail="Failed to update distributor")


@router.delete("/distributors/{distributor_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_distributor(
    distributor_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    row = db.query(PharmacyDistributor).filter(PharmacyDistributor.id == distributor_id).first()
    if not row or (current.hospital_id and row.hospital_id != current.hospital_id):
        raise HTTPException(status_code=404, detail="Distributor not found")
    try:
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.commit()
        return ok(message="Distributor deleted successfully")
    except Exception:
        db.rollback()
        logger.exception("Failed to delete distributor")
        raise HTTPException(status_code=500, detail="Failed to delete distributor")
