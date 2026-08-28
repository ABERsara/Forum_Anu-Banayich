import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { TranslocoModule } from '@jsverse/transloco';

/**
 * Button that toggles the UI language between Hebrew and English.
 *
 * Usage:
 *   <app-language-toggle [isHebrew]="locale.lang() === 'he'" (toggled)="locale.toggleLang()" />
 *
 * Dumb component (see copy-text.component.ts for the shared-component pattern):
 * no LocaleService/TranslocoService injection here — the parent owns the
 * language state, this component only renders it and emits an intent to switch.
 */
@Component({
  selector: 'app-language-toggle',
  imports: [TranslocoModule],
  templateUrl: './language-toggle.component.html',
  styleUrl: './language-toggle.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LanguageToggleComponent {
  readonly isHebrew = input.required<boolean>();
  readonly toggled = output<void>();
}
