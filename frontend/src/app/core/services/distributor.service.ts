import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface PharmacyDistributor {
    id: string;
    serial_no: number;
    hospital_id?: string;
    name: string;
    company?: string;
    phone?: string;
    email?: string;
    address?: string;
    city?: string;
    status: 'active' | 'inactive';
    notes?: string;
    created_at?: string;
    updated_at?: string;
}

export interface DistributorPayload {
    name: string;
    company?: string;
    phone?: string;
    email?: string;
    address?: string;
    city?: string;
    status?: string;
    notes?: string;
}

export interface DistributorFilters {
    status?: string;
    search?: string;
}

@Injectable({ providedIn: 'root' })
export class DistributorService {
    private readonly API = `${environment.apiBaseUrl}/staff/pharmacy/distributors`;

    constructor(private http: HttpClient) { }

    list(filters?: DistributorFilters): Observable<any> {
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

    create(payload: DistributorPayload): Observable<any> {
        return this.http.post(this.API, payload);
    }

    update(id: string, payload: Partial<DistributorPayload>): Observable<any> {
        return this.http.put(`${this.API}/${id}`, payload);
    }

    remove(id: string): Observable<any> {
        return this.http.delete(`${this.API}/${id}`);
    }
}
