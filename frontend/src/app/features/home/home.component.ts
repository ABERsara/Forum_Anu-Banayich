import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { UserRole } from '../../core/constants';
import { AuthService } from '../../core/services/auth.service';
import { CardComponent } from '../../shared/components/card/card.component';

@Component({
  selector: 'app-home',
  imports: [CardComponent, RouterLink],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  readonly auth = inject(AuthService);
  readonly UserRole = UserRole;
}
