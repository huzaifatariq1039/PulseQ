import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';

import { TableModule } from 'primeng/table';
import { CardModule } from 'primeng/card';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DropdownModule } from 'primeng/dropdown';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService, ConfirmationService } from 'primeng/api';

import * as XLSX from 'xlsx';

import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { DistributorService, PharmacyDistributor, DistributorPayload } from '../../../core/services/distributor.service';

interface DistributorForm {
    id?: string;
    name: string;
    company: string;
    phone: string;
    email: string;
    address: string;
    city: string;
    status: string;
    notes: string;
}

@Component({
    selector: 'app-pharmacy-distributors',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule, InputTextModule,
        DropdownModule, DialogModule, ToastModule, ConfirmDialogModule, TooltipModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './distributors.component.html',
    styleUrls: ['./distributors.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class DistributorsComponent implements OnInit, OnDestroy {
    distributors: PharmacyDistributor[] = [];
    isLoading = false;
    isExporting = false;
    activeCount = 0;

    searchText = '';
    statusFilter = 'all';

    statusOptions = [
        { label: 'All Status', value: 'all' },
        { label: 'Active', value: 'active' },
        { label: 'Inactive', value: 'inactive' }
    ];

    formStatusOptions = [
        { label: 'Active', value: 'active' },
        { label: 'Inactive', value: 'inactive' }
    ];

    dialogVisible = false;
    isSaving = false;
    editingId: string | null = null;
    form: DistributorForm = this.blankForm();

    private destroy$ = new Subject<void>();
    private searchSubject$ = new Subject<void>();

    constructor(
        private distributorService: DistributorService,
        public messageService: MessageService,
        public confirmationService: ConfirmationService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.searchSubject$.pipe(
            debounceTime(350),
            distinctUntilChanged(),
            takeUntil(this.destroy$)
        ).subscribe(() => this.fetchDistributors());

        this.fetchDistributors();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── Data ──────────────────────────────────────────────────────────────
    fetchDistributors(): void {
        this.isLoading = true;
        this.cdr.markForCheck();

        this.distributorService.list({
            status: this.statusFilter !== 'all' ? this.statusFilter : undefined,
            search: this.searchText || undefined
        }).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.distributors = Array.isArray(res?.data) ? res.data : [];
                this.activeCount = res?.meta?.active ?? this.distributors.filter(d => d.status === 'active').length;
                this.isLoading = false;
                this.cdr.markForCheck();
            },
            error: () => {
                this.distributors = [];
                this.activeCount = 0;
                this.isLoading = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Load failed',
                    detail: 'Could not fetch distributors. Please try again.', life: 4000
                });
            }
        });
    }

    onSearchChange(): void { this.searchSubject$.next(); }
    onFilterChange(): void { this.fetchDistributors(); }

    clearFilters(): void {
        this.searchText = '';
        this.statusFilter = 'all';
        this.fetchDistributors();
    }

    // ── Dialog ────────────────────────────────────────────────────────────
    private blankForm(): DistributorForm {
        return {
            name: '', company: '', phone: '', email: '',
            address: '', city: '', status: 'active', notes: ''
        };
    }

    openAdd(): void {
        this.editingId = null;
        this.form = this.blankForm();
        this.dialogVisible = true;
    }

    openEdit(row: PharmacyDistributor): void {
        this.editingId = row.id;
        this.form = {
            id: row.id,
            name: row.name || '',
            company: row.company || '',
            phone: row.phone || '',
            email: row.email || '',
            address: row.address || '',
            city: row.city || '',
            status: row.status || 'active',
            notes: row.notes || ''
        };
        this.dialogVisible = true;
    }

    save(): void {
        if (!this.form.name?.trim()) {
            this.messageService.add({
                severity: 'warn', summary: 'Missing name',
                detail: 'Distributor Name is required.', life: 3000
            });
            return;
        }

        const payload: DistributorPayload = {
            name: this.form.name.trim(),
            company: this.form.company || undefined,
            phone: this.form.phone || undefined,
            email: this.form.email || undefined,
            address: this.form.address || undefined,
            city: this.form.city || undefined,
            status: this.form.status || 'active',
            notes: this.form.notes || undefined
        };

        this.isSaving = true;
        this.cdr.markForCheck();

        const req$ = this.editingId
            ? this.distributorService.update(this.editingId, payload)
            : this.distributorService.create(payload);

        req$.pipe(takeUntil(this.destroy$)).subscribe({
            next: () => {
                this.isSaving = false;
                this.dialogVisible = false;
                this.messageService.add({
                    severity: 'success', summary: this.editingId ? 'Updated' : 'Added',
                    detail: `Distributor ${this.editingId ? 'updated' : 'added'} successfully`, life: 3000
                });
                this.fetchDistributors();
            },
            error: () => {
                this.isSaving = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Save failed',
                    detail: 'Could not save the distributor. Please try again.', life: 4000
                });
            }
        });
    }

    delete(row: PharmacyDistributor): void {
        this.confirmationService.confirm({
            message: `Delete distributor <strong>${row.name}</strong>?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.distributorService.remove(row.id).subscribe({
                    next: () => {
                        this.distributors = this.distributors.filter(d => d.id !== row.id);
                        this.cdr.markForCheck();
                        this.messageService.add({
                            severity: 'success', summary: 'Deleted',
                            detail: 'Distributor removed', life: 3000
                        });
                    },
                    error: () => this.messageService.add({
                        severity: 'error', summary: 'Delete failed',
                        detail: 'Could not delete. Please try again.', life: 4000
                    })
                });
            }
        });
    }

    // ── Export ────────────────────────────────────────────────────────────
    exportToExcel(): void {
        if (!this.distributors.length) {
            this.messageService.add({
                severity: 'warn', summary: 'Nothing to export',
                detail: 'No distributors match the current filter', life: 3000
            });
            return;
        }
        this.isExporting = true;
        this.cdr.markForCheck();

        const rows = this.distributors.map(d => ({
            'Serial No': d.serial_no,
            'Distributor Name': d.name,
            'Company': d.company || '-',
            'Phone': d.phone || '-',
            'Email': d.email || '-',
            'City': d.city || '-',
            'Address': d.address || '-',
            'Status': d.status,
            'Notes': d.notes || ''
        }));

        const ws = XLSX.utils.json_to_sheet(rows);
        ws['!cols'] = Object.keys(rows[0]).map(k => ({
            wch: Math.max(k.length, ...rows.map((r: any) => String(r[k] ?? '').length)) + 2
        }));
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Distributors');
        XLSX.writeFile(wb, `pharmacy_distributors_${new Date().toISOString().split('T')[0]}.xlsx`);

        this.isExporting = false;
        this.cdr.markForCheck();
    }

    statusBadgeClass(status: string): string {
        return (status || '').toLowerCase() === 'active' ? 'badge-active' : 'badge-inactive';
    }
}
