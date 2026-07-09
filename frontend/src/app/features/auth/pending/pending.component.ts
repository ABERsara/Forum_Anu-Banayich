import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-pending-approval',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './pending.component.html',
  styleUrl: './pending.component.scss',
})
export class PendingApprovalComponent {}
