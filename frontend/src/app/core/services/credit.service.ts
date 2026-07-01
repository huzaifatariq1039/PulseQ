import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface CreditPayment {
    id: string;
    credit_id: string;
    amount: number;
    payment_date?: string;
    payment_method?: string;
    notes?: string;
    created_at?: string;
}

export interface PharmacyCredit {
    id: string;
    serial_no: number;
    hospital_id?: string;
    purchase_date?: string;
    customer_name: string;
    contact_number?: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    total_amount: number;
    amount_paid: number;
    balance: number;
    due_date?: string;
    status: 'pending' | 'partially_paid' | 'cleared';
    notes?: string;
    created_at?: string;
    updated_at?: string;
    payments?: CreditPayment[];
}

export interface CreditPayload {
    purchase_date?: string;
    customer_name: string;
    contact_number?: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    amount_paid?: number;
    due_date?: string;
    notes?: string;
}

export interface CreditPaymentPayload {
    amount: number;
    payment_date?: string;
    payment_method?: string;
    notes?: string;
}

export interface CustomerSummary {
    customer_name: string;
    contact_number?: string;
    entries: number;
    total_credit: number;
    total_paid: number;
    total_balance: number;
}

export interface CreditFilters {
    customer?: string;
    status?: string;
    search?: string;
}

@Injectable({ providedIn: 'root' })
export class CreditService {
    private readonly API = `${environment.apiBaseUrl}/staff/pharmacy/credits`;

    constructor(private http: HttpClient) { }

    list(filters?: CreditFilters): Observable<any> {
        let params = new HttpParams();
        if (filters) {
            Object.entries(filters).forEach(([key, value]) => {
                if (value !== undefined && value !== null && value !== '') {
                    params = params.set(key, String(value));
                }
            });
        }
        return this.http.get(this.API, { params });
    }

    get(id: string): Observable<any> {
        return this.http.get(`${this.API}/${id}`);
    }

    customerSummary(): Observable<any> {
        return this.http.get(`${this.API}/summary`);
    }

    create(payload: CreditPayload): Observable<any> {
        return this.http.post(this.API, payload);
    }

    update(id: string, payload: Partial<CreditPayload>): Observable<any> {
        return this.http.put(`${this.API}/${id}`, payload);
    }

    addPayment(id: string, payload: CreditPaymentPayload): Observable<any> {
        return this.http.post(`${this.API}/${id}/payments`, payload);
    }

    remove(id: string): Observable<any> {
        return this.http.delete(`${this.API}/${id}`);
    }
}
