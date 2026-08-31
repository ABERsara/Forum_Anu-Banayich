import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-pending-approval',
  standalone: true,
  imports: [RouterLink, TranslocoPipe],
  templateUrl: './pending.component.html',
  styleUrl: './pending.component.scss',
})
export class PendingApprovalComponent {}
