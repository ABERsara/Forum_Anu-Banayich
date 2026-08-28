import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { LocaleService } from '../../core/services/locale.service';
import { LanguageToggleComponent } from '../../shared/components/language-toggle/language-toggle.component';

@Component({
  selector: 'app-header',
  imports: [RouterLink, RouterLinkActive, LanguageToggleComponent],
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
