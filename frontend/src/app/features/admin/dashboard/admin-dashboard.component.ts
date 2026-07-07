/**
 * Admin dashboard – overview of the system.
 *
 * TODO:
 *   1. Show remaining stats cards:
 *      - Active users count
 *      - Pending reports count
 *   2. Recent audit log entries (last 10 actions)
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AdminService } from '../../../core/services/admin.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [RouterLink, LoadingSpinnerComponent, ErrorDisplayComponent],
  templateUrl: './admin-dashboard.component.html',
})
export class AdminDashboardComponent implements OnInit {
  private readonly adminService = inject(AdminService);

  pendingCount = signal<number | null>(null);
  isLoading = signal(false);
  hasError = signal(false);

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);

    this.adminService.getPendingRegistrations().subscribe({
      next: (registrations) => {
        this.pendingCount.set(registrations.length);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }
}
