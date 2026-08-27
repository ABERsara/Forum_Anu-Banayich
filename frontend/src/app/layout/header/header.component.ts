import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TranslocoModule } from '@jsverse/transloco';

import { AuthService } from '../../core/services/auth.service';
import { LocaleService } from '../../core/services/locale.service';

@Component({
  selector: 'app-header',
  imports: [RouterLink, RouterLinkActive, TranslocoModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  readonly auth = inject(AuthService);
  readonly locale = inject(LocaleService);

  readonly isHebrew = computed(() => this.locale.lang() === 'he');

  logout(): void {
    this.auth.logout();
  }

  toggleLang(): void {
    this.locale.toggleLang();
  }
}
