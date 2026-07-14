import { ChangeDetectionStrategy, ChangeDetectorRef, Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, ActivatedRoute, RouterModule } from '@angular/router';
import { AdminSidebarComponent } from '../shared/components/admin-sidebar/admin-sidebar.component';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

// PrimeNG
import { CardModule } from 'primeng/card';
import { ChartModule } from 'primeng/chart';
import { ToastModule } from 'primeng/toast';

// Services
import { StaffPortalService } from '../../../core/services/staff-portal.service';
import { AuthService } from '../../../core/services/auth.service';
import { RealtimeService } from '../../../core/services/realtime.service';

/**
 * AdminDashboardComponent - Displays system overview and metrics
 * DOES NOT HANDLE (Delegated to specific components):
 * - Doctor management → AdminManageDoctorsComponent
 * - Department management → AdminManageDepartmentsComponent
 * - Other features → Dedicated components
 */
@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterModule,
    AdminSidebarComponent,
    CardModule,
    ChartModule,
    ToastModule
  ],
  templateUrl: './admin-dashboard.component.html',
  styleUrl: './admin-dashboard.component.css'
})
export class AdminDashboardComponent implements OnInit, OnDestroy {
  // Dashboard Metrics
  metrics = [
    { label: 'Total Patients Today', value: '0', icon: 'pi-users', bgColor: '#e0f2fe', iconColor: '#3b82f6', note: 'Patients' },
    { label: 'Active Doctors', value: '0', icon: 'pi-heart', bgColor: '#dcfce7', iconColor: '#22c55e', note: 'Doctors' },
    { label: 'Avg Wait Time', value: '0m', icon: 'pi-clock', bgColor: '#ffedd5', iconColor: '#f97316', note: 'Average' },
    { label: 'Departments', value: '0', icon: 'pi-building', bgColor: '#f3e8ff', iconColor: '#a855f7', note: 'Units' }
  ];

  // Chart Configuration
  chartData: any;
  chartOptions: any;

  // System Logs
  logEntries: { message: string; time: string }[] = [];

  private destroy$ = new Subject<void>();

  constructor(
    public router: Router,
    private activatedRoute: ActivatedRoute,
    private staffService: StaffPortalService,
    private authService: AuthService,
    private realtimeService: RealtimeService,
    private cdr: ChangeDetectorRef
  ) { }

  ngOnInit(): void {
    this.initChart();
    this.fetchDashboardData();

    // Real-time sync: refresh dashboard on queue/queue-update events from any portal
    const hospitalId = this.getHospitalId();
    if (hospitalId) {
      this.realtimeService.connect(`hospital_${hospitalId}`)
        .pipe(takeUntil(this.destroy$))
        .subscribe((message: any) => {
          if (message?.type && message.type !== 'ack') {
            this.fetchDashboardData();
          }
        });
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private getHospitalId(): string {
    const user: any = this.authService.getCurrentUser();
    return user?.hospitalId || user?.hospital_id || '';
  }

  // ─────────────────────────────────────────────────────────────
  // DASHBOARD DATA LOADING
  // ─────────────────────────────────────────────────────────────
  fetchDashboardData(): void {
    if (typeof window === 'undefined') return;

    const currentUser = this.authService.getCurrentUser();
    const hospitalId = (currentUser as any)?.hospitalId || '';

    this.staffService.getAdminDashboard(hospitalId, 10).subscribe({
      next: (res: any) => {
        const data = res?.data || res;
        if (!data) return;

        // Parse metrics from API response
        const cards = data.cards || data.metrics || data;
        this.metrics[0].value = String(cards.total_patients_today ?? cards.total_patients ?? 0);
        this.metrics[1].value = String(cards.active_doctors ?? cards.availableDoctors ?? 0);
        const waitMin = cards.avg_wait_time_minutes ?? cards.avg_wait_time;
        this.metrics[2].value = waitMin != null ? `${waitMin}m` : 'N/A';
        this.metrics[3].value = String(cards.departments ?? cards.active_departments ?? cards.departments_count ?? 0);

        // Parse patient flow chart data
        const flowData: { hour: string; count: number }[] = data.patient_flow_today || [];
        if (flowData.length > 0) {
          const labels = flowData.map((e: any) => e.hour);
          const counts = flowData.map((e: any) => Number(e.count));
          const maxVal = Math.max(...counts, 5);

          this.chartData = {
            labels,
            datasets: [{
              label: 'Patients',
              data: counts,
              fill: true,
              backgroundColor: '#3b82f6',
              borderColor: '#3b82f6',
              borderRadius: 4,
              borderSkipped: false
            }]
          };

          this.chartOptions = {
            maintainAspectRatio: false,
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              y: {
                beginAtZero: true,
                max: maxVal + 2,
                ticks: { stepSize: Math.max(1, Math.ceil((maxVal + 2) / 4)) },
                grid: { color: '#f3f4f6' }
              },
              x: { grid: { display: false } }
            }
          };
        }

        // Parse system logs
        const logsRaw: any[] = data.live_system_logs || [];
        if (logsRaw.length > 0) {
          this.logEntries = logsRaw.map((log: any) => ({
            message: log.message || `${log.action || 'System'} action`,
            time: log.time_ago || log.created_at || ''
          }));
        }
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Failed to load dashboard data', err);
      }
    });
  }

  // ─────────────────────────────────────────────────────────────
  // CHART INITIALIZATION
  // ─────────────────────────────────────────────────────────────
  private initChart(): void {
    this.chartData = {
      labels: ['8am', '9am', '10am', '11am', '12pm', '1pm', '2pm', '3pm'],
      datasets: [{
        label: 'Patients',
        data: [0, 0, 0, 0, 0, 0, 0, 0],
        fill: true,
        backgroundColor: '#3b82f6',
        borderColor: '#3b82f6',
        borderRadius: 4,
        borderSkipped: false
      }]
    };

    this.chartOptions = {
      maintainAspectRatio: false,
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          max: 60,
          ticks: { stepSize: 15 },
          grid: { color: '#f3f4f6' }
        },
        x: { grid: { display: false } }
      }
    };
  }

  // ─────────────────────────────────────────────────────────────
  // UTILITY METHODS
  // ─────────────────────────────────────────────────────────────

  /** Extracts token from log message (e.g., "A-011") */
  extractToken(message: string): string {
    const match = message.match(/Token\s+(\S+)/);
    return match ? match[1] : '';
  }

  /** Returns the part after "Token X-XXX" */
  extractLogSuffix(message: string): string {
    const match = message.match(/Token\s+\S+\s+(.*)/);
    return match ? match[1] : message;
  }
}