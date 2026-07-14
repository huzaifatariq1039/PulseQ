import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PharmacySidebarComponent } from '../shared/components/pharmacy-sidebar/pharmacy-sidebar.component';
import { PharmacyService, PharmacyPrescription } from '../../../core/services/pharmacy.service';
import { AuthService } from '../../../core/services/auth.service';
import { RealtimeService } from '../../../core/services/realtime.service';
import { ButtonModule } from 'primeng/button';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

interface DoctorFilter {
  id: string;
  name: string;
  department: string;
}

@Component({
  selector: 'app-pharmacy-prescriptions',
  standalone: true,
  imports: [CommonModule, FormsModule, PharmacySidebarComponent, ButtonModule],
  templateUrl: './prescriptions.component.html',
  styleUrls: ['./prescriptions.component.css']
})
export class PrescriptionsComponent implements OnInit, OnDestroy {
  loading = false;

  prescriptions: PharmacyPrescription[] = [];
  departments: string[] = [];
  doctors: DoctorFilter[] = [];

  selectedDepartment = '';
  selectedDoctorId = '';
  search = '';

  private destroy$ = new Subject<void>();

  constructor(
    private pharmacyService: PharmacyService,
    private authService: AuthService,
    private realtimeService: RealtimeService
  ) {}

  ngOnInit(): void {
    // Real-time sync: refresh the prescription queue whenever any pharmacy
    // action changes shared state (a colleague dispenses or marks a script
    // pending/completed) so this board never goes stale.
    const hospitalId = this.getHospitalId();
    if (hospitalId) {
      this.realtimeService.connect(`hospital_${hospitalId}`)
        .pipe(takeUntil(this.destroy$))
        .subscribe((message: any) => {
          if (message?.type && message.type !== 'ack') {
            this.loadPrescriptions();
          }
        });
    }

    this.loadPrescriptions();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private getHospitalId(): string {
    const user: any = this.authService.getCurrentUser();
    return user?.hospitalId || user?.hospital_id || '';
  }

  get filteredDoctors(): DoctorFilter[] {
    if (!this.selectedDepartment) return this.doctors;
    return this.doctors.filter(d => d.department === this.selectedDepartment);
  }

  get filteredPrescriptions(): PharmacyPrescription[] {
    const term = this.search.trim().toLowerCase();
    return this.prescriptions.filter(p => {
      if (this.selectedDepartment && (p.department || '') !== this.selectedDepartment) return false;
      if (this.selectedDoctorId && (p.doctor_id || '') !== this.selectedDoctorId) return false;

      if (!term) return true;
      const patient = (p.patient_name || '').toLowerCase();
      const token = String(p.token_number ?? '').toLowerCase();
      return patient.includes(term) || token.includes(term);
    });
  }

  onDepartmentChange(): void {
    if (this.selectedDoctorId) {
      const valid = this.filteredDoctors.some(d => d.id === this.selectedDoctorId);
      if (!valid) this.selectedDoctorId = '';
    }
  }

  loadPrescriptions(): void {
    this.loading = true;
    this.pharmacyService.getPrescriptionQueue('all', 500).subscribe({
      next: (res: any) => {
        const rows = Array.isArray(res?.data) ? res.data : [];
        this.prescriptions = rows.map((r: any) => ({
          id: r.id,
          token_id: r.token_id,
          token_number: r.token_number,
          doctor_id: r.doctor_id,
          doctor_name: r.doctor_name,
          department: r.department,
          patient_id: r.patient_id,
          patient_name: r.patient_name,
          hospital_id: r.hospital_id,
          medicines: Array.isArray(r.medicines) ? r.medicines : [],
          notes: r.notes,
          dispense_status: (String(r.dispense_status || 'pending').toLowerCase() === 'completed' ? 'completed' : 'pending'),
          dispensed_at: r.dispensed_at,
          dispensed_by: r.dispensed_by,
          created_at: r.created_at,
        } as PharmacyPrescription));

        const depSet = new Set<string>();
        const doctorMap = new Map<string, DoctorFilter>();

        for (const p of this.prescriptions) {
          const dep = String(p.department || '').trim();
          if (dep) depSet.add(dep);

          const did = String(p.doctor_id || '').trim();
          const dname = String(p.doctor_name || '').trim();
          if (did && !doctorMap.has(did)) {
            doctorMap.set(did, { id: did, name: dname || 'Doctor', department: dep || 'General' });
          }
        }

        this.departments = Array.from(depSet).sort((a, b) => a.localeCompare(b));
        this.doctors = Array.from(doctorMap.values()).sort((a, b) => a.name.localeCompare(b.name));
        this.loading = false;
      },
      error: () => {
        this.prescriptions = [];
        this.departments = [];
        this.doctors = [];
        this.loading = false;
      }
    });
  }

  markStatus(p: PharmacyPrescription, status: 'pending' | 'completed'): void {
    this.pharmacyService.updatePrescriptionStatus(p.id, status).subscribe({
      next: () => this.loadPrescriptions(),
      error: () => {}
    });
  }

  medicineCount(p: PharmacyPrescription): number {
    return Array.isArray(p.medicines) ? p.medicines.length : 0;
  }
}
