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
import { ExpenseService, PharmacyExpense, ExpensePayload } from '../../../core/services/expense.service';

interface ExpenseForm {
    id?: string;
    expense_date: string;
    demanded_by: string;
    department: string;
    item_name: string;
    quantity: number;
    unit_price: number;
    issued_by: string;
    status: string;
    notes: string;
}

@Component({
    selector: 'app-pharmacy-expense',
    standalone: true,
    imports: [
        CommonModule, RouterModule, FormsModule,
        TableModule, CardModule, ButtonModule, InputTextModule,
        DropdownModule, DialogModule, ToastModule, ConfirmDialogModule, TooltipModule,
        PharmacySidebarComponent
    ],
    providers: [MessageService, ConfirmationService],
    templateUrl: './expense.component.html',
    styleUrls: ['./expense.component.css'],
    changeDetection: ChangeDetectionStrategy.OnPush
})
export class ExpenseComponent implements OnInit, OnDestroy {
    expenses: PharmacyExpense[] = [];
    isLoading = false;
    isExporting = false;
    totalExpense = 0;

    // Filters
    searchText = '';
    dateFrom = '';
    dateTo = '';
    departmentFilter = '';
    staffFilter = '';
    statusFilter = 'all';

    statusOptions = [
        { label: 'All Status', value: 'all' },
        { label: 'Pending', value: 'pending' },
        { label: 'Issued', value: 'issued' },
        { label: 'Rejected', value: 'rejected' }
    ];

    formStatusOptions = [
        { label: 'Pending', value: 'pending' },
        { label: 'Issued', value: 'issued' },
        { label: 'Rejected', value: 'rejected' }
    ];

    // Dialog form
    dialogVisible = false;
    isSaving = false;
    editingId: string | null = null;
    form: ExpenseForm = this.blankForm();

    private destroy$ = new Subject<void>();
    private searchSubject$ = new Subject<void>();

    constructor(
        private expenseService: ExpenseService,
        public messageService: MessageService,
        public confirmationService: ConfirmationService,
        private cdr: ChangeDetectorRef
    ) { }

    ngOnInit(): void {
        this.searchSubject$.pipe(
            debounceTime(350),
            distinctUntilChanged(),
            takeUntil(this.destroy$)
        ).subscribe(() => this.fetchExpenses());

        this.fetchExpenses();
    }

    ngOnDestroy(): void {
        this.destroy$.next();
        this.destroy$.complete();
    }

    // ── Data ──────────────────────────────────────────────────────────────
    fetchExpenses(): void {
        this.isLoading = true;
        this.cdr.markForCheck();

        this.expenseService.list({
            date_from: this.dateFrom || undefined,
            date_to: this.dateTo || undefined,
            department: this.departmentFilter || undefined,
            demanded_by: this.staffFilter || undefined,
            status: this.statusFilter !== 'all' ? this.statusFilter : undefined,
            search: this.searchText || undefined
        }).pipe(takeUntil(this.destroy$)).subscribe({
            next: (res: any) => {
                this.expenses = Array.isArray(res?.data) ? res.data : [];
                this.totalExpense = res?.meta?.total_expense ?? this.computeTotal();
                this.isLoading = false;
                this.cdr.markForCheck();
            },
            error: () => {
                this.expenses = [];
                this.totalExpense = 0;
                this.isLoading = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Load failed',
                    detail: 'Could not fetch expenses. Please try again.', life: 4000
                });
            }
        });
    }

    private computeTotal(): number {
        return this.expenses.reduce((sum, e) => sum + (e.total_price || 0), 0);
    }

    // ── Filters ───────────────────────────────────────────────────────────
    onSearchChange(): void { this.searchSubject$.next(); }
    onFilterChange(): void { this.fetchExpenses(); }

    clearFilters(): void {
        this.searchText = '';
        this.dateFrom = '';
        this.dateTo = '';
        this.departmentFilter = '';
        this.staffFilter = '';
        this.statusFilter = 'all';
        this.fetchExpenses();
    }

    // ── Dialog: add / edit ────────────────────────────────────────────────
    private blankForm(): ExpenseForm {
        return {
            expense_date: new Date().toISOString().split('T')[0],
            demanded_by: '', department: '', item_name: '',
            quantity: 1, unit_price: 0, issued_by: '', status: 'pending', notes: ''
        };
    }

    openAdd(): void {
        this.editingId = null;
        this.form = this.blankForm();
        this.dialogVisible = true;
    }

    openEdit(row: PharmacyExpense): void {
        this.editingId = row.id;
        this.form = {
            id: row.id,
            expense_date: (row.expense_date || '').split('T')[0],
            demanded_by: row.demanded_by || '',
            department: row.department || '',
            item_name: row.item_name || '',
            quantity: row.quantity ?? 0,
            unit_price: row.unit_price ?? 0,
            issued_by: row.issued_by || '',
            status: row.status || 'pending',
            notes: row.notes || ''
        };
        this.dialogVisible = true;
    }

    get formTotal(): number {
        return (this.form.quantity || 0) * (this.form.unit_price || 0);
    }

    save(): void {
        if (!this.form.item_name?.trim()) {
            this.messageService.add({
                severity: 'warn', summary: 'Missing item',
                detail: 'Medicine / Item Name is required.', life: 3000
            });
            return;
        }

        const payload: ExpensePayload = {
            expense_date: this.form.expense_date || undefined,
            demanded_by: this.form.demanded_by || undefined,
            department: this.form.department || undefined,
            item_name: this.form.item_name.trim(),
            quantity: Number(this.form.quantity) || 0,
            unit_price: Number(this.form.unit_price) || 0,
            issued_by: this.form.issued_by || undefined,
            status: this.form.status || 'pending',
            notes: this.form.notes || undefined
        };

        this.isSaving = true;
        this.cdr.markForCheck();

        const req$ = this.editingId
            ? this.expenseService.update(this.editingId, payload)
            : this.expenseService.create(payload);

        req$.pipe(takeUntil(this.destroy$)).subscribe({
            next: () => {
                this.isSaving = false;
                this.dialogVisible = false;
                this.messageService.add({
                    severity: 'success', summary: this.editingId ? 'Updated' : 'Added',
                    detail: `Expense ${this.editingId ? 'updated' : 'recorded'} successfully`, life: 3000
                });
                this.fetchExpenses();
            },
            error: () => {
                this.isSaving = false;
                this.cdr.markForCheck();
                this.messageService.add({
                    severity: 'error', summary: 'Save failed',
                    detail: 'Could not save the expense. Please try again.', life: 4000
                });
            }
        });
    }

    delete(row: PharmacyExpense): void {
        this.confirmationService.confirm({
            message: `Delete expense for <strong>${row.item_name}</strong>?`,
            header: 'Confirm Delete',
            icon: 'pi pi-exclamation-triangle',
            accept: () => {
                this.expenseService.remove(row.id).subscribe({
                    next: () => {
                        this.expenses = this.expenses.filter(e => e.id !== row.id);
                        this.totalExpense = this.computeTotal();
                        this.cdr.markForCheck();
                        this.messageService.add({
                            severity: 'success', summary: 'Deleted',
                            detail: 'Expense removed', life: 3000
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
        if (!this.expenses.length) {
            this.messageService.add({
                severity: 'warn', summary: 'Nothing to export',
                detail: 'No expenses match the current filter', life: 3000
            });
            return;
        }
        this.isExporting = true;
        this.cdr.markForCheck();

        const rows = this.expenses.map(e => ({
            'Serial No': e.serial_no,
            'Date': this.formatDate(e.expense_date),
            'Demanded By': e.demanded_by || '-',
            'Department / Ward': e.department || '-',
            'Item Name': e.item_name,
            'Quantity': e.quantity,
            'Unit Price': e.unit_price,
            'Total Price': e.total_price,
            'Issued By': e.issued_by || '-',
            'Status': e.status,
            'Notes': e.notes || ''
        }));

        const ws = XLSX.utils.json_to_sheet(rows);
        ws['!cols'] = Object.keys(rows[0]).map(k => ({
            wch: Math.max(k.length, ...rows.map((r: any) => String(r[k] ?? '').length)) + 2
        }));
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Expenses');
        XLSX.writeFile(wb, `pharmacy_expenses_${new Date().toISOString().split('T')[0]}.xlsx`);

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

    statusBadgeClass(status: string): string {
        switch ((status || '').toLowerCase()) {
            case 'issued': return 'badge-active';
            case 'rejected': return 'badge-expired';
            default: return 'badge-low-stock';
        }
    }
}
