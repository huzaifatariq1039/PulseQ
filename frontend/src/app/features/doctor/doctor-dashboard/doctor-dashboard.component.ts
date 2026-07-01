import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextareaModule } from 'primeng/inputtextarea';
import { BadgeModule } from 'primeng/badge';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ConsultationService } from '../../../core/services/consultation.service';
import { QueueService } from '../../../core/services/queue.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap } from 'rxjs/operators';
import { DoctorSidebarComponent } from '../shared/components/doctor-sidebar/doctor-sidebar.component';

interface PrescribedMedicine {
  name: string;
  generic_name?: string;
  dosage?: string;
  instructions?: string;
  in_stock: boolean;
  quantity_available?: number;
}
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AuthService } from '../../../core/services/auth.service';
import { NotificationService } from '../../../core/services/notification.service';
import { DoctorService } from '../../../core/services';
import { RealtimeService } from '../../../core/services/realtime.service';

interface Patient {
  name: string;
  age: number;
  gender: string;
  reason: string;
  phone: string;
  token: string;
  patientId?: string;
  tokenId?: string;
  mrn?: string;
}

interface UpcomingPatient {
  token: string;
  name: string;
  age: number;
  reason: string;
  waitTime: string;
  patientId?: string;
  tokenId?: string;
  mrn?: string;
  gender?: string;
  phone?: string;
}

@Component({
  selector: 'app-doctor-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterModule,
    FormsModule,
    ButtonModule,
    CardModule,
    InputTextareaModule,
    BadgeModule,
    ToastModule,
    DoctorSidebarComponent
  ],
  providers: [MessageService],
  templateUrl: './doctor-dashboard.component.html',
  styleUrl: './doctor-dashboard.component.css'
})
export class DoctorDashboardComponent implements OnInit {

  doctorName = '';
  doctorId = '';
  specialty = '';
  qualifications = '';
  waitingPatients = 0;
  patientsServed = 0;
  rating = 0;
  reviewCount = 0;
  sidebarOpen = false;

  currentPatient: Patient | null = null;

  consultationNotes = '';
  consultationStartTime: Date | null = null;
  isConsultationActive = false;

  // Prescription / medicine entry
  medicineQuery = '';
  medicineSuggestions: any[] = [];
  showSuggestions = false;
  searchingMeds = false;
  prescribedMedicines: PrescribedMedicine[] = [];
  private medSearch$ = new Subject<string>();

  upcomingPatients: UpcomingPatient[] = [];
  skippedPatients: UpcomingPatient[] = [];
  private realtimeRoom: string | null = null;

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private messageService = inject(MessageService);
  private consultationService = inject(ConsultationService);
  private queueService = inject(QueueService);
  private staffService = inject(StaffPortalService);
  private authService = inject(AuthService);
  private doctorService = inject(DoctorService);
  private notificationService = inject(NotificationService);
  private realtimeService = inject(RealtimeService);
  private destroyRef = inject(DestroyRef);

  constructor(private cdr: ChangeDetectorRef) { }

  // =========================
  // START CONSULTATION
  // =========================
  trackStar(index: number): number {
    return index;
  }

  trackUpcomingPatient(index: number, patient: UpcomingPatient): string | number {
    return patient.tokenId || patient.token || index;
  }

  trackSkippedPatient(patient: UpcomingPatient): string | number {
    return patient.tokenId || patient.token || patient.name;
  }

  startConsultation(): void {
    if (!this.currentPatient) return;

    const tokenId = this.currentPatient.tokenId;

    if (!tokenId) {
      console.error('Missing tokenId', this.currentPatient);
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Token ID is missing for this patient'
      });
      return;
    }

    if (!this.doctorId) {
      console.error('Missing doctorId');
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Doctor ID is missing. Please refresh the page.'
      });
      return;
    }

    const payload = { token_id: tokenId, doctor_id: this.doctorId };
    console.log('START consultation payload:', payload);

    this.consultationService.startConsultationApi(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: any) => {
          console.log('Start consultation response:', res);
          this.consultationStartTime = new Date();
          this.isConsultationActive = true;

          // ✅ Remove current patient from upcoming queue immediately on start
          if (this.currentPatient?.tokenId) {
            this.upcomingPatients = this.upcomingPatients.filter(
              p => p.tokenId !== this.currentPatient!.tokenId &&
                p.token !== this.currentPatient!.token
            );
            console.log('[START] Removed serving patient from upcoming queue:', this.currentPatient.tokenId);
          }

          this.messageService.add({
            severity: 'info',
            summary: 'Consultation Started',
            detail: `With ${this.currentPatient?.name}`
          });
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error('Start consultation error', err);
          this.messageService.add({
            severity: 'error',
            summary: 'Failed to Start',
            detail: err?.error?.message || 'Could not start consultation. Please try again.'
          });
        }
      });
  }

  // =========================
  // FINISH CONSULTATION
  // =========================
  finishConsultation(): void {
    if (!this.currentPatient || !this.consultationStartTime) return;

    const tokenId = this.currentPatient.tokenId;

    if (!tokenId) {
      console.error('Missing tokenId', this.currentPatient);
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Token ID is missing for this patient'
      });
      return;
    }

    if (!this.doctorId) {
      console.error('Missing doctorId');
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Doctor ID is missing. Please refresh the page.'
      });
      return;
    }

    const payload = {
      token_id: tokenId,
      doctor_id: this.doctorId,
      consultation_notes: this.consultationNotes,
      medicines: this.prescribedMedicines
    };

    console.log('END consultation payload:', payload);

    this.consultationService.endConsultationApi(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: any) => {
          console.log('End consultation response:', res);
          this.messageService.add({
            severity: 'success',
            summary: 'Completed',
            detail: 'Consultation finished successfully'
          });

          this.patientsServed++;
          this.resetConsultation();
          this.fetchDashboard();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error('End consultation error', err);
          this.messageService.add({
            severity: 'error',
            summary: 'Failed to Finish',
            detail: err?.error?.message || 'Could not finish consultation. Please try again.'
          });
        }
      });
  }

  // =========================
  // SKIP PATIENT
  // =========================
  skipPatient(): void {
    if (!this.currentPatient?.tokenId) return;

    const tokenId = this.currentPatient.tokenId;
    console.log('SKIP token_id:', tokenId);

    this.queueService.skipPatient(tokenId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: any) => {
          console.log('Skip patient response:', res);
          this.messageService.add({
            severity: 'info',
            summary: 'Patient Skipped',
            detail: `${this.currentPatient?.name} has been moved to skipped queue`
          });
          // Send notification to patient about token being skipped
          if (this.currentPatient?.token) {
            this.notificationService.sendTokenSkipped(this.currentPatient.token, 'the doctor');
          }
          this.resetConsultation();
          this.fetchDashboard();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error('Skip patient error', err);
          this.messageService.add({
            severity: 'error',
            summary: 'Skip Failed',
            detail: err?.error?.message || 'Could not skip patient. Please try again.'
          });
        }
      });
  }

  // =========================
  // RE-ADD FROM SKIPPED
  // =========================
  reAddFromSkipped(patient: UpcomingPatient): void {
    if (!patient.tokenId) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Patient token ID not found'
      });
      return;
    }

    console.log('RE-ADD token_id:', patient.tokenId);

    this.queueService.reAddToQueue(patient.tokenId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: any) => {
          console.log('Re-add patient response:', res);
          this.messageService.add({
            severity: 'success',
            summary: 'Re-added',
            detail: `${patient.token} - ${patient.name} added back to queue`
          });
          this.fetchDashboard();
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error('Re-add patient error', err);
          this.messageService.add({
            severity: 'error',
            summary: 'Re-add Failed',
            detail: err?.error?.message || 'Could not re-add patient. Please try again.'
          });
        }
      });
  }

  // =========================
  // RESET
  // =========================
  private resetConsultation(): void {
    this.consultationNotes = '';
    this.consultationStartTime = null;
    this.isConsultationActive = false;
    this.currentPatient = null;
    this.prescribedMedicines = [];
    this.clearMedicineSearch();
  }

  // =========================
  // INIT
  // =========================
  ngOnInit(): void {
    this.fetchDashboard();

    // Debounced medicine search → live suggestions from pharmacy stock
    this.medSearch$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap(q => {
          this.searchingMeds = true;
          this.cdr.markForCheck();
          return this.consultationService.searchMedicines(q);
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe({
        next: (res: any) => {
          this.medicineSuggestions = Array.isArray(res?.data) ? res.data : [];
          this.showSuggestions = true;
          this.searchingMeds = false;
          this.cdr.markForCheck();
        },
        error: () => {
          this.medicineSuggestions = [];
          this.searchingMeds = false;
          this.cdr.markForCheck();
        }
      });
  }

  // =========================
  // PRESCRIPTION / MEDICINES
  // =========================
  onMedicineQueryChange(): void {
    const q = this.medicineQuery.trim();
    if (!q) {
      this.medicineSuggestions = [];
      this.showSuggestions = false;
      this.cdr.markForCheck();
      return;
    }
    this.medSearch$.next(q);
  }

  addMedicineFromSuggestion(m: any): void {
    this.addMedicine({
      name: m.name,
      generic_name: m.generic_name,
      in_stock: !!m.in_stock,
      quantity_available: m.quantity_available,
      dosage: '',
      instructions: ''
    });
    this.clearMedicineSearch();
  }

  // Add whatever the doctor typed, even if not in pharmacy stock (out of stock).
  addCustomMedicine(): void {
    const name = this.medicineQuery.trim();
    if (!name) return;
    // If it exactly matches a suggestion, prefer that (keeps stock info).
    const match = this.medicineSuggestions.find(
      s => (s.name || '').toLowerCase() === name.toLowerCase()
    );
    if (match) {
      this.addMedicineFromSuggestion(match);
      return;
    }
    this.addMedicine({
      name, generic_name: '', in_stock: false, quantity_available: 0,
      dosage: '', instructions: ''
    });
    this.clearMedicineSearch();
  }

  private addMedicine(m: PrescribedMedicine): void {
    const exists = this.prescribedMedicines.some(
      x => x.name.toLowerCase() === m.name.toLowerCase()
    );
    if (!exists) this.prescribedMedicines.push(m);
    this.cdr.markForCheck();
  }

  removeMedicine(index: number): void {
    this.prescribedMedicines.splice(index, 1);
    this.cdr.markForCheck();
  }

  private clearMedicineSearch(): void {
    this.medicineQuery = '';
    this.medicineSuggestions = [];
    this.showSuggestions = false;
    this.cdr.markForCheck();
  }

  hideSuggestionsSoon(): void {
    // Delay so a suggestion click registers before the list hides.
    setTimeout(() => {
      this.showSuggestions = false;
      this.cdr.markForCheck();
    }, 200);
  }

  // =========================
  // DASHBOARD
  // =========================
  fetchDashboard(): void {
    if (typeof window === 'undefined') return;

    // Fallback from auth (may be overridden by API response below)
    const currentUser = this.authService.getCurrentUser();
    if (currentUser) {
      this.doctorName = currentUser.name || '';
      this.doctorId = currentUser.id || '';
    }

    this.ensureRealtimeConnection();

    this.staffService.getDoctorDashboard(20, 20)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: any) => {
          if (!res.success) return;

          const d = res.data;

          // ✅ Use doctor ID from API response — this is the authoritative source
          if (d.doctor?.id) {
            this.doctorId = d.doctor.id;
            this.doctorName = d.doctor.name || this.doctorName;
            this.specialty = d.doctor.department || '';
            this.ensureRealtimeConnection();
          }

          console.log('Doctor ID from API:', this.doctorId);

          // ─── STEP 1: Build raw upcoming list ───────────────────────────────
          let rawUpcoming: UpcomingPatient[] = [];

          if (d.upcoming_patients && Array.isArray(d.upcoming_patients)) {
            rawUpcoming = d.upcoming_patients.map((t: any) => ({
              token: t.token_number || t.token || '',
              name: t.patient_name || 'Unknown',
              age: this.parseAge(t.patient_age) || 0,
              reason: t.reason_for_visit || t.reason || '',
              waitTime: (t.estimated_wait_time || t.waiting_time_minutes || 0) + 'm',
              patientId: t.patient_id || t.mrn || '',
              tokenId: t.token_id || t.id || '',
              mrn: t.mrn || '',
              gender: t.patient_gender || 'Unknown',
              phone: t.phone || ''
            }));
          }

          // ─── STEP 2: Resolve current patient ──────────────────────────────
          if (d.current_consultation) {
            // Backend says there IS an active consultation — use it authoritatively
            const t = d.current_consultation;
            this.currentPatient = {
              name: t.patient_name || 'Unknown',
              age: this.parseAge(t.patient_age) || 0,
              gender: t.patient_gender || 'Unknown',
              reason: t.reason_for_visit || t.reason || t.visit_reason || '',
              phone: t.phone || t.patient_phone || '',
              token: t.token_number || t.token || '',
              patientId: t.patient_id || t.mrn || '',
              tokenId: t.token_id || t.id || '',
              mrn: t.mrn || ''
            };
            this.isConsultationActive = true;
            if (!this.consultationStartTime) {
              this.consultationStartTime = new Date();
            }
          } else if (!this.isConsultationActive) {
            // No active consultation running — promote first upcoming as current
            if (rawUpcoming.length > 0) {
              const first = rawUpcoming[0];
              this.currentPatient = {
                name: first.name,
                age: first.age,
                gender: first.gender || 'Unknown',
                reason: first.reason,
                phone: first.phone || '',
                token: first.token,
                patientId: first.patientId,
                tokenId: first.tokenId,
                mrn: first.mrn || ''
              };
            } else {
              this.currentPatient = null;
            }
          }
          // If isConsultationActive but no current_consultation from backend yet,
          // keep the existing this.currentPatient untouched.

          // ─── STEP 3: Always filter serving token out of upcoming ──────────
          // Filter by BOTH tokenId and token string to handle any mapping gaps
          const servingTokenId = this.currentPatient?.tokenId;
          const servingToken = this.currentPatient?.token;

          this.upcomingPatients = rawUpcoming.filter(p =>
            (servingTokenId ? p.tokenId !== servingTokenId : true) &&
            (servingToken ? p.token !== servingToken : true)
          );

          console.log('[DASHBOARD] currentPatient:', this.currentPatient?.tokenId,
            '| upcoming count:', this.upcomingPatients.length);

          // ─── STEP 4: Skipped patients ──────────────────────────────────────
          if (d.skipped_patients && Array.isArray(d.skipped_patients)) {
            this.skippedPatients = d.skipped_patients.map((t: any) => ({
              token: t.token_number || t.token || '',
              name: t.patient_name || 'Unknown',
              age: this.parseAge(t.patient_age) || 0,
              reason: t.reason_for_visit || t.reason || '',
              waitTime: '0m',
              patientId: t.patient_id || t.mrn || '',
              tokenId: t.token_id || t.id || '',
              mrn: t.mrn || '',
              gender: t.patient_gender || 'Unknown',
              phone: t.phone || ''
            }));
          }

          // ─── STEP 5: Stats cards ───────────────────────────────────────────
          if (d.cards) {
            this.waitingPatients = d.cards.waiting_in_queue || 0;
            this.patientsServed = d.cards.patients_served || 0;
          }
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.error('Error fetching doctor dashboard:', err);
          this.messageService.add({
            severity: 'warn',
            summary: 'Dashboard Error',
            detail: 'Could not load dashboard data. Retrying...'
          });
        }
      });
  }

  private parseAge(ageStr: any): number {
    if (!ageStr) return 0;
    if (typeof ageStr === 'number') return ageStr;
    const match = String(ageStr).match(/\d+/);
    return match ? parseInt(match[0], 10) : 0;
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  logout(): void {
    this.authService.logout();
  }

  viewPreviousHistory(): void {
    // Scope history to THIS patient only (not all of the doctor's patients).
    const patientId = this.currentPatient?.patientId;
    this.router.navigate(['../history'], {
      relativeTo: this.route,
      queryParams: patientId ? { patientId } : {}
    });
  }

  private ensureRealtimeConnection(): void {
    if (!this.doctorId) {
      return;
    }

    const room = `doctor_${this.doctorId}`;
    if (this.realtimeRoom === room) {
      return;
    }

    this.realtimeRoom = room;
    this.realtimeService.connect(room)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(message => {
        if (message?.type === 'ack') {
          return;
        }

        this.fetchDashboard();
      });
  }
}