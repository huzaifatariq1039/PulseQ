import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, ActivatedRoute } from '@angular/router';
import { AuthService } from '../../../../../core/services/auth.service';
import { adminPath } from '../../../../../core/utils/portal-path.util';

@Component({
    selector: 'app-admin-sidebar',
    standalone: true,
    imports: [CommonModule, RouterModule],
    templateUrl: './admin-sidebar.component.html',
    styleUrls: ['./admin-sidebar.component.css']
})
export class AdminSidebarComponent {
    sidebarOpen = false;

    dashboardPath = adminPath('dashboard');
    completedConsultationsPath = adminPath('completed-consultations');
    manageDoctorsPath = adminPath('manage-doctors');
    manageDepartmentsPath = adminPath('manage-departments');
    pharmacySalesPath = adminPath('pharmacy-sales-revenue');

    constructor(private route: ActivatedRoute, private router: Router, private authService: AuthService) { }

    signOut(): void {
        this.authService.logout();
    }

    toggleSidebar(): void {
        this.sidebarOpen = !this.sidebarOpen;
    }
}
