import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { Subscription } from 'rxjs';
import { filter, takeUntil } from 'rxjs/operators';
import { Subject } from 'rxjs';

import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { ToastModule } from 'primeng/toast';
import { PharmacyService, PharmacyPrescription } from '../../../core/services/pharmacy.service';
import { Medicine } from '../../../shared/models/medicine.model';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { AuthService } from '../../../core/services/auth.service';
import { pharmacyPath } from '../../../core/utils/portal-path.util';
import { RealtimeService } from '../../../core/services/realtime.service';

@Component({
    selector: 'app-pharmacy-dashboard',
    standalone: true,
    imports: [
        CommonModule,
        RouterModule,
        CardModule,
        ButtonModule,
        MessageModule,
        ToastModule,
        PharmacySidebarComponent
    ],
    templateUrl: './pharmacy-dashboard.component.html',
    styleUrls: ['./pharmacy-dashboard.component.css']
})
export class PharmacyDashboardComponent implements OnInit, OnDestroy {

    totalMedicines = 0;
    lowStockCount = 0;
    expiredCount = 0;
    activeCount = 0;
    inventoryValue = 0;

    medicines: Medicine[] = [];
    pendingPrescriptions: PharmacyPrescription[] = [];
    completedPrescriptions: PharmacyPrescription[] = [];
    selectedPrescriptionTab: 'pending' | 'completed' = 'pending';
    prescriptionsLoading = false;
    private sub: Subscription | null = null;

    constructor(
        private pharmacyService: PharmacyService,
        private authService: AuthService,
        private route: ActivatedRoute,
        private router: Router,
        private realtimeService: RealtimeService
    ) { }

    private destroy$ = new Subject<void>();

    ngOnInit(): void {

        const hid =
            (this.authService.getCurrentUser() as any)?.hospitalId || '';

        // Real-time updates for pharmacy queue (new prescriptions, etc.)
        if (hid) {
            this.realtimeService.connect(`hospital_${hid}`)
                .pipe(takeUntil(this.destroy$))
                .subscribe(() => {
                    this.loadPrescriptionQueue();
                    this.pharmacyService.loadMedicinesFromApi(hid);
                });
        }

        // FIX: Call load FIRST so loading() becomes true immediately.
        // The guard in PharmacyService prevents duplicate concurrent calls
        // if other components also call this before the response arrives.
        this.pharmacyService.loadMedicinesFromApi(hid);

        // FIX: filter() skips the initial empty-array emission that fires
        // synchronously when the signal is first observed (before the API
        // responds). Without this, stats briefly show 0 then re-render.
        //
        // We wait until loading is false AND we have data, OR loading is
        // false with an empty array (genuinely no medicines in the system).
        this.sub = this.pharmacyService.medicines$
            .pipe(
                filter(() => !this.pharmacyService.loading())
            )
            .subscribe(meds => {
                this.medicines = meds;
                this.updateStats();
            });

        this.loadPrescriptionQueue();
    }

    ngOnDestroy(): void {
        this.sub?.unsubscribe();
        this.destroy$.next();
        this.destroy$.complete();
    }

    updateStats(): void {

        this.totalMedicines = this.medicines.length;

        const today = new Date();

        this.lowStockCount =
            this.medicines.filter(m => m.quantity < 10).length;

        this.expiredCount =
            this.medicines.filter(
                m => m.expiryDate && new Date(m.expiryDate) < today
            ).length;

        this.activeCount =
            this.medicines.filter(
                m => this.getMedicineStatus(m) === 'Active'
            ).length;

        this.inventoryValue =
            this.medicines.reduce(
                (sum, m) => sum + (m.quantity * m.sellingPrice),
                0
            );
    }

    getMedicineStatus(medicine: Medicine): 'Active' | 'Low Stock' | 'Expired' {

        const today = new Date();
        const expiry = new Date(medicine.expiryDate);

        if (expiry < today) return 'Expired';
        if (medicine.quantity < 10) return 'Low Stock';

        return 'Active';
    }

    formatRs(amount: number): string {
        return `Rs ${amount.toFixed(2)}`;
    }

    goToInventory(): void {
        this.router.navigate([pharmacyPath('inventory')]);
    }

    goToSales(): void {
        this.router.navigate([pharmacyPath('sales')]);
    }

    get visiblePrescriptions(): PharmacyPrescription[] {
        return this.selectedPrescriptionTab === 'pending'
            ? this.pendingPrescriptions
            : this.completedPrescriptions;
    }

    loadPrescriptionQueue(): void {
        this.prescriptionsLoading = true;
        this.pharmacyService.getPrescriptionQueue('all', 200).subscribe({
            next: (res: any) => {
                const rows = Array.isArray(res?.data) ? res.data : [];
                const all: PharmacyPrescription[] = rows.map((r: any) => ({
                    id: r.id,
                    token_id: r.token_id,
                    doctor_id: r.doctor_id,
                    doctor_name: r.doctor_name,
                    patient_id: r.patient_id,
                    patient_name: r.patient_name,
                    hospital_id: r.hospital_id,
                    medicines: Array.isArray(r.medicines) ? r.medicines : [],
                    notes: r.notes,
                    dispense_status: (String(r.dispense_status || 'pending').toLowerCase() === 'completed' ? 'completed' : 'pending'),
                    dispensed_at: r.dispensed_at,
                    dispensed_by: r.dispensed_by,
                    created_at: r.created_at,
                }));

                this.pendingPrescriptions = all.filter(p => p.dispense_status === 'pending');
                this.completedPrescriptions = all.filter(p => p.dispense_status === 'completed');
                this.prescriptionsLoading = false;
            },
            error: () => {
                this.pendingPrescriptions = [];
                this.completedPrescriptions = [];
                this.prescriptionsLoading = false;
            }
        });
    }

    setPrescriptionTab(tab: 'pending' | 'completed'): void {
        this.selectedPrescriptionTab = tab;
    }

    markPrescriptionStatus(p: PharmacyPrescription, nextStatus: 'pending' | 'completed'): void {
        this.pharmacyService.updatePrescriptionStatus(p.id, nextStatus).subscribe({
            next: () => this.loadPrescriptionQueue(),
            error: () => { }
        });
    }

    getMedicineNames(p: PharmacyPrescription): string {
        if (!Array.isArray(p.medicines) || p.medicines.length === 0) return '—';
        return p.medicines.map(m => m?.name).filter(Boolean).join(', ');
    }
}