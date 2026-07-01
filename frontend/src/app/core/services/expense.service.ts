import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface PharmacyExpense {
    id: string;
    serial_no: number;
    hospital_id?: string;
    expense_date?: string;
    demanded_by?: string;
    department?: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    total_price: number;
    issued_by?: string;
    status: 'pending' | 'issued' | 'rejected';
    notes?: string;
    created_at?: string;
    updated_at?: string;
}

export interface ExpensePayload {
    expense_date?: string;
    demanded_by?: string;
    department?: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    issued_by?: string;
    status?: string;
    notes?: string;
}

export interface ExpenseFilters {
    date_from?: string;
    date_to?: string;
    department?: string;
    demanded_by?: string;
    status?: string;
    search?: string;
}

@Injectable({ providedIn: 'root' })
export class ExpenseService {
    private readonly API = `${environment.apiBaseUrl}/staff/pharmacy/expenses`;

    constructor(private http: HttpClient) { }

    list(filters?: ExpenseFilters): Observable<any> {
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

    create(payload: ExpensePayload): Observable<any> {
        return this.http.post(this.API, payload);
    }

    update(id: string, payload: Partial<ExpensePayload>): Observable<any> {
        return this.http.put(`${this.API}/${id}`, payload);
    }

    remove(id: string): Observable<any> {
        return this.http.delete(`${this.API}/${id}`);
    }
}
