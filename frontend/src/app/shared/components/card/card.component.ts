import { Component, input } from '@angular/core';

@Component({
  selector: 'app-card',
  templateUrl: './card.component.html',
  styleUrl: './card.component.scss',
})
export class CardComponent {
  /**
   * Card heading — already translated by the caller:
   * `<app-card [title]="'home.forum.title' | transloco">`. The card holds no
   * text of its own, so it carries no translation keys.
   */
  title = input<string>('');
  /** Card sub-heading — already translated by the caller. */
  subtitle = input<string>('');
  elevated = input(false);
}
