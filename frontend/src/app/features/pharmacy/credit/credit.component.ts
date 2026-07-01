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
import {
    CreditService, PharmacyCredit, CreditPayload, CustomerSummary
} from '../../../core/services/credit.service';

interface CreditForm {
    id?: string;
    purchase_date: string;
    customer_name: string;
    contact_number: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    amount_paid: number;
    due_date: string;
    notes: string;
}

@Component({
    selector: 'app-pharmacy-credit',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule, InputTextModule,
        DropdownModule, DialogModule, ToastModule, ConfirmDialogModule, TooltipModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './credit.component.html',
    styleUrls: ['./credit.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class CreditComponent implements OnInit, OnDestroy {
    view: 'records' | 'customers' = 'records';

    credits: PharmacyCredit[] = [];
    customers: CustomerSummary[] = [];
    isLoading = false;
    isExporting = false;

    totalCredit = 0;
    totalPaid = 0;
    totalBalance = 0;

    // Filters
    searchText = '';
    customerFilter = '';
    statusFilter = 'all';

    statusOptions = [
        { label: 'All Status', value: 'all' },
        { label: 'Pending', value: 'pending' },
        { label: 'Partially Paid', value: 'partially_paid' },
        { label: 'Cleared', value: 'cleared' }
    ];

    // Entry dialog
    dialogVisible = false;
    isSaving = false;
    editingId: string | null = null;
    form: CreditForm = this.blankForm();

    // Payment dialog
    payDialogVisible = false;
    isPaying = false;
    activeCredit: PharmacyCredit | null = null;
    payAmount = 0;
    payDate = new Date().toISOString().split('T')[0];
    payMethod = 'cash';
    payNotes = '';

    payMethodOptions = [
        { label: 'Cash', value: 'cash' },
        { label: 'Card', value: 'card' },
        { label: 'Bank Transfer', value: 'bank' },
        { label: 'Other', value: 'other' }
    ];

    // Bill print
    printingCredit: PharmacyCredit | null = null;

    private destroy$ = new Subject<void>();
    private searchSubject$ = new Subject<void>();

    constructor(
        private creditService: CreditService,
        public messageService: MessageService,
        public confirmationService: ConfirmationService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.searchSubject$.pipe(
            debounceTime(350),
            distinctUntilChanged(),
            takeUntil(this.destroy$)
        ).subscribe(() => this.fetchCredits());

        this.fetchCredits();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── View switch ───────────────────────────────────────────────────────
    switchView(v: 'records' | 'customers'): void {
        this.view = v;
        if (v === 'customers' && !this.customers.length) {
            this.fetchCustomers();
        }
    }

    // ── Data ──────────────────────────────────────────────────────────────
    fetchCredits(): void {
        this.isLoading = true;
        this.cdr.markForCheck();

        this.creditService.list({
            customer: this.customerFilter || undefined,
            status: this.statusFilter !== 'all' ? this.statusFilter : undefined,
            search: this.searchText || undefined
        }).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.credits = Array.isArray(res?.data) ? res.data : [];
                this.totalCredit = res?.meta?.total_credit ?? 0;
                this.totalPaid = res?.meta?.total_paid ?? 0;
                this.totalBalance = res?.meta?.total_balance ?? 0;
                this.isLoading = false;
                this.cdr.markForCheck();
            },
            error: () => {
                this.credits = [];
                this.isLoading = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Load failed',
                    detail: 'Could not fetch credit records. Please try again.', life: 4000
                });
            }
        });
    }

    fetchCustomers(): void {
        this.creditService.customerSummary().pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.customers = Array.isArray(res?.data) ? res.data : [];
                this.cdr.markForCheck();
            },
            error: () => {
                this.customers = [];
                this.cdr.markForCheck();
            }
        });
    }

    // ── Filters ───────────────────────────────────────────────────────────
    onSearchChange(): void { this.searchSubject$.next(); }
    onFilterChange(): void { this.fetchCredits(); }

    clearFilters(): void {
        this.searchText = '';
        this.customerFilter = '';
        this.statusFilter = 'all';
        this.fetchCredits();
    }

    // ── Add / edit ────────────────────────────────────────────────────────
    private blankForm(): CreditForm {
        return {
            purchase_date: new Date().toISOString().split('T')[0],
            customer_name: '', contact_number: '', item_name: '',
            quantity: 1, unit_price: 0, amount_paid: 0, due_date: '', notes: ''
        };
    }

    openAdd(): void {
        this.editingId = null;
        this.form = this.blankForm();
        this.dialogVisible = true;
    }

    openEdit(row: PharmacyCredit): void {
        this.editingId = row.id;
        this.form = {
            id: row.id,
            purchase_date: (row.purchase_date || '').split('T')[0],
            customer_name: row.customer_name || '',
            contact_number: row.contact_number || '',
            item_name: row.item_name || '',
            quantity: row.quantity ?? 0,
            unit_price: row.unit_price ?? 0,
            amount_paid: row.amount_paid ?? 0,
            due_date: (row.due_date || '').split('T')[0],
            notes: row.notes || ''
        };
        this.dialogVisible = true;
    }

    get formTotal(): number {
        return (this.form.quantity || 0) * (this.form.unit_price || 0);
    }

    get formBalance(): number {
        return this.formTotal - (this.form.amount_paid || 0);
    }

    save(): void {
        if (!this.form.customer_name?.trim() || !this.form.item_name?.trim()) {
            this.messageService.add({
                severity: 'warn', summary: 'Missing fields',
                detail: 'Customer Name and Item Name are required.', life: 3000
            });
            return;
        }
        if ((this.form.amount_paid || 0) > this.formTotal) {
            this.messageService.add({
                severity: 'warn', summary: 'Invalid amount',
                detail: 'Amount paid cannot exceed the total amount.', life: 3000
            });
            return;
        }

        const payload: CreditPayload = {
            purchase_date: this.form.purchase_date || undefined,
            customer_name: this.form.customer_name.trim(),
            contact_number: this.form.contact_number || undefined,
            item_name: this.form.item_name.trim(),
            quantity: Number(this.form.quantity) || 0,
            unit_price: Number(this.form.unit_price) || 0,
            amount_paid: Number(this.form.amount_paid) || 0,
            due_date: this.form.due_date || undefined,
            notes: this.form.notes || undefined
        };

        this.isSaving = true;
        this.cdr.markForCheck();

        // amount_paid is only used as the opening balance on create.
        const cleanPayload = this.editingId ? { ...payload, amount_paid: undefined } : payload;

        const req$ = this.editingId
            ? this.creditService.update(this.editingId, cleanPayload)
            : this.creditService.create(payload);

        req$.pipe(takeUntil(this.destroy$)).subscribe({
            next: () => {
                this.isSaving = false;
                this.dialogVisible = false;
                this.messageService.add({
                    severity: 'success', summary: this.editingId ? 'Updated' : 'Added',
                    detail: `Credit entry ${this.editingId ? 'updated' : 'created'} successfully`, life: 3000
                });
                this.refreshAll();
            },
            error: () => {
                this.isSaving = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Save failed',
                    detail: 'Could not save the credit entry. Please try again.', life: 4000
                });
            }
        });
    }

    delete(row: PharmacyCredit): void {
        this.confirmationService.confirm({
            message: `Delete credit entry for <strong>${row.customer_name}</strong>?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.creditService.remove(row.id).subscribe({
                    next: () => {
                        this.credits = this.credits.filter(c => c.id !== row.id);
                        this.cdr.markForCheck();
                        this.messageService.add({
                            severity: 'success', summary: 'Deleted',
                            detail: 'Credit entry removed', life: 3000
                        });
                        this.refreshAll();
                    },
                    error: () => this.messageService.add({
                        severity: 'error', summary: 'Delete failed',
                        detail: 'Could not delete. Please try again.', life: 4000
                    })
                });
            }
        });
    }

    // ── Payments ──────────────────────────────────────────────────────────
    openPay(row: PharmacyCredit): void {
        // Load full record (with payment history) for the dialog.
        this.activeCredit = row;
        this.payAmount = row.balance || 0;
        this.payDate = new Date().toISOString().split('T')[0];
        this.payMethod = 'cash';
        this.payNotes = '';
        this.payDialogVisible = true;

        this.creditService.get(row.id).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                if (res?.data) {
                    this.activeCredit = res.data;
                    this.cdr.markForCheck();
                }
            },
            error: () => { /* keep the row data we already have */ }
        });
    }

    recordPayment(): void {
        if (!this.activeCredit) return;
        const amount = Number(this.payAmount) || 0;
        if (amount <= 0) {
            this.messageService.add({
                severity: 'warn', summary: 'Invalid amount',
                detail: 'Enter a payment amount greater than zero.', life: 3000
            });
            return;
        }
        if (amount > (this.activeCredit.balance || 0) + 0.01) {
            this.messageService.add({
                severity: 'warn', summary: 'Too much',
                detail: 'Payment exceeds the remaining balance.', life: 3000
            });
            return;
        }

        this.isPaying = true;
        this.cdr.markForCheck();

        this.creditService.addPayment(this.activeCredit.id, {
            amount,
            payment_date: this.payDate || undefined,
            payment_method: this.payMethod || undefined,
            notes: this.payNotes || undefined
        }).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.isPaying = false;
                if (res?.data) this.activeCredit = res.data;
                this.payAmount = this.activeCredit?.balance || 0;
                this.payNotes = '';
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'success', summary: 'Payment recorded',
                    detail: 'The payment was added successfully', life: 3000
                });
                this.refreshAll();
            },
            error: () => {
                this.isPaying = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Payment failed',
                    detail: 'Could not record the payment. Please try again.', life: 4000
                });
            }
        });
    }

    private refreshAll(): void {
        this.fetchCredits();
        if (this.customers.length || this.view === 'customers') this.fetchCustomers();
    }

    // ── Bill print ────────────────────────────────────────────────────────
    printBill(row: PharmacyCredit): void {
        // Fetch the full record (with payment history) so the bill is complete.
        this.creditService.get(row.id).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.printingCredit = res?.data || row;
                this.cdr.markForCheck();
                setTimeout(() => window.print(), 300);
            },
            error: () => {
                // Fall back to the row we already have.
                this.printingCredit = row;
                this.cdr.markForCheck();
                setTimeout(() => window.print(), 300);
            }
        });
    }

    todayString(): string {
        return new Date().toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: '2-digit'
        });
    }

    // ── Export ────────────────────────────────────────────────────────────
    exportToExcel(): void {
        const isCustomers = this.view === 'customers';
        const source: any[] = isCustomers ? this.customers : this.credits;
        if (!source.length) {
            this.messageService.add({
                severity: 'warn', summary: 'Nothing to export',
                detail: 'No records match the current filter', life: 3000
            });
            return;
        }
        this.isExporting = true;
        this.cdr.markForCheck();

        const rows = isCustomers
            ? this.customers.map(c => ({
                'Customer Name': c.customer_name,
                'Contact': c.contact_number || '-',
                'Entries': c.entries,
                'Total Credit': c.total_credit,
                'Total Paid': c.total_paid,
                'Total Balance': c.total_balance
            }))
            : this.credits.map(c => ({
                'Serial No': c.serial_no,
                'Date of Purchase': this.formatDate(c.purchase_date),
                'Customer Name': c.customer_name,
                'Contact': c.contact_number || '-',
                'Item Name': c.item_name,
                'Quantity': c.quantity,
                'Unit Price': c.unit_price,
                'Total Amount': c.total_amount,
                'Amount Paid': c.amount_paid,
                'Balance': c.balance,
                'Due Date': this.formatDate(c.due_date),
                'Status': c.status,
                'Notes': c.notes || ''
            }));

        const ws = XLSX.utils.json_to_sheet(rows);
        ws['!cols'] = Object.keys(rows[0]).map(k => ({
            wch: Math.max(k.length, ...rows.map((r: any) => String(r[k] ?? '').length)) + 2
        }));
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, isCustomers ? 'Customers' : 'Credits');
        XLSX.writeFile(wb, `pharmacy_credits_${isCustomers ? 'customers' : 'records'}_${new Date().toISOString().split('T')[0]}.xlsx`);

        this.isExporting = false;
        this.cdr.markForCheck();
    }

    // ── Helpers ───────────────────────────────────────────────────────────
    formatDate(dateStr?: string): string {
        if (!dateStr) return '-';
        try {
            return new Date(dateStr).toLocaleDateString('en-US', {
                year: 'numeric', month: 'short', day: '2-digit'
            });
        } catch { return dateStr; }
    }

    statusLabel(status: string): string {
        switch ((status || '').toLowerCase()) {
            case 'cleared': return 'Cleared';
            case 'partially_paid': return 'Partially Paid';
            default: return 'Pending';
        }
    }

    statusBadgeClass(status: string): string {
        switch ((status || '').toLowerCase()) {
            case 'cleared': return 'badge-active';
            case 'partially_paid': return 'badge-partial';
            default: return 'badge-low-stock';
        }
    }

    isOverdue(row: PharmacyCredit): boolean {
        if (!row.due_date || (row.status || '').toLowerCase() === 'cleared') return false;
        const due = new Date(row.due_date);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return due < today;
    }
}
