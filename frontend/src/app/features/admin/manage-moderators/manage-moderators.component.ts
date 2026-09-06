/**
 * Manage moderators – the admin's view of the moderator roster.
 *
 * Lists every appointed moderator with the cells they oversee, appoints new
 * ones over the group×sector matrix, edits an assignment, and removes a
 * moderator from the roster. The companion of the moderation module, from the
 * admin's side.
 */

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import {
  GROUP_VISIBILITY_LABELS,
  GroupVisibility,
  LabelKey,
  SECTOR_LABELS,
  Sector,
  UserType,
} from '../../../core/constants';
import {
  ModeratorAdminView,
  ModeratorCell,
  ModeratorCreateRequest,
  ModeratorUpdateRequest,
} from '../../../core/models';
import { LabelService } from '../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { AdminService } from '../../../core/services/admin.service';
import { ActionMessage } from '../action-message';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** A moderator with no cell ticked oversees nothing — the backend rejects it too. */
function atLeastOneCell(control: AbstractControl): ValidationErrors | null {
  const value: unknown = control.value;
  return Array.isArray(value) && value.length > 0 ? null : { required: true };
}

@Component({
  selector: 'app-manage-moderators',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslocoPipe,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './manage-moderators.component.html',
  styleUrl: './manage-moderators.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ManageModeratorsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly labels = inject(LabelService);
  private readonly adminService = inject(AdminService);

  readonly moderators = signal<ModeratorAdminView[]>([]);
  readonly isLoading = signal(false);
  readonly hasError = signal(false);
  /** What went wrong on save or remove, as a key of ours or the API's own sentence. */
  readonly actionError = signal<ScreenError>(NO_ERROR);
  /** Our own confirmation, held as a key and a name so it follows a language switch. */
  readonly successMessage = signal<ActionMessage | null>(null);
  readonly isSaving = signal(false);
  readonly isFormOpen = signal(false);
  /** The moderator being edited; null while the form is appointing a new one. */
  readonly editing = signal<ModeratorAdminView | null>(null);
  /** The moderator the confirm dialog is asking about; null while it is closed. */
  readonly pendingRemoval = signal<ModeratorAdminView | null>(null);
  readonly isRemoving = signal(false);

  /**
   * The axes of the matrix. Their declaration order is also the order the API
   * stores cells in, so a matrix read top-to-bottom already is the canonical
   * order and the backend never has to reorder what this form submits.
   */
  readonly groups = Object.values(UserType);
  readonly sectors = Object.values(Sector);
  readonly sectorLabels = SECTOR_LABELS;

  /**
   * A cell names a population, not a person, so it reads with the plural
   * audience labels ("אלמנות") rather than the personal ones ("אלמנה"). Every
   * UserType value is also a GroupVisibility value, which is what lets the
   * labels be derived here instead of spelled out a third time.
   */
  readonly groupLabels: Record<UserType, LabelKey> = {
    [UserType.WIDOWER]: GROUP_VISIBILITY_LABELS[GroupVisibility.WIDOWERS],
    [UserType.WIDOW]: GROUP_VISIBILITY_LABELS[GroupVisibility.WIDOWS],
    [UserType.ORPHAN_MALE]: GROUP_VISIBILITY_LABELS[GroupVisibility.ORPHANS_MALE],
    [UserType.ORPHAN_FEMALE]: GROUP_VISIBILITY_LABELS[GroupVisibility.ORPHANS_FEMALE],
  };

  /**
   * One form serves both modes. When editing, the identity controls are
   * disabled — name and email are not part of the PATCH contract — which also
   * keeps them out of `form.value` and out of the request body.
   */
  readonly form = this.fb.nonNullable.group({
    first_name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    last_name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    email: ['', [Validators.required, Validators.email]],
    alert_email: ['', Validators.email],
    moderator_cells: this.fb.nonNullable.control<ModeratorCell[]>([], atLeastOneCell),
  });

  private readonly identityControls = [
    this.form.controls.first_name,
    this.form.controls.last_name,
    this.form.controls.email,
  ];

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.adminService.getModerators().subscribe({
      next: (moderators) => {
        this.moderators.set(moderators);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Read helpers for the list
  // -------------------------------------------------------------------------

  fullName(moderator: ModeratorAdminView): string {
    return `${moderator.first_name} ${moderator.last_name}`;
  }

  /**
   * "אלמנות – ספרדי", the cell as it reads in the roster. Two labels joined
   * into one string, which is why it translates here rather than in the
   * template: there is no single key for the pair.
   */
  cellLabel(cell: ModeratorCell): string {
    const group = this.labels.label(this.groupLabels[cell.group]);
    const sector = this.labels.label(this.sectorLabels[cell.sector]);
    return `${group} – ${sector}`;
  }

  /** Where this moderator's report alerts land. */
  alertAddress(moderator: ModeratorAdminView): string {
    return moderator.alert_email ?? moderator.email;
  }

  // -------------------------------------------------------------------------
  // The cell matrix
  // -------------------------------------------------------------------------

  isCellSelected(group: UserType, sector: Sector): boolean {
    return this.form.controls.moderator_cells.value.some(
      (cell) => cell.group === group && cell.sector === sector,
    );
  }

  selectedCellCount(): number {
    return this.form.controls.moderator_cells.value.length;
  }

  toggleCell(group: UserType, sector: Sector): void {
    const control = this.form.controls.moderator_cells;
    const selected = control.value;

    control.setValue(
      this.isCellSelected(group, sector)
        ? selected.filter((cell) => !(cell.group === group && cell.sector === sector))
        : this.inMatrixOrder([...selected, { group, sector }]),
    );
    control.markAsTouched();
  }

  // -------------------------------------------------------------------------
  // Form
  // -------------------------------------------------------------------------

  openAddForm(): void {
    this.clearMessages();
    this.editing.set(null);
    this.form.reset();
    this.identityControls.forEach((control) => control.enable());
    this.isFormOpen.set(true);
  }

  openEditForm(moderator: ModeratorAdminView): void {
    this.clearMessages();
    this.editing.set(moderator);
    this.form.patchValue({
      alert_email: moderator.alert_email ?? '',
      moderator_cells: this.inMatrixOrder(moderator.moderator_cells),
    });
    this.identityControls.forEach((control) => control.disable());
    this.isFormOpen.set(true);
  }

  closeForm(): void {
    this.isFormOpen.set(false);
    this.editing.set(null);
  }

  save(): void {
    this.trimTextControls();
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const editing = this.editing();
    this.isSaving.set(true);
    this.clearMessages();

    const request$ = editing
      ? this.adminService.updateModerator(editing.id, this.assignmentBody())
      : this.adminService.addModerator(this.createBody());

    request$.subscribe({
      next: (saved) => {
        if (editing) {
          this.replaceRow(saved);
          this.successMessage.set({
            key: 'admin.manage_moderators.assignments_updated',
            name: this.fullName(saved),
          });
        } else {
          this.insertRow(saved);
          this.successMessage.set({
            key: 'admin.manage_moderators.appointed',
            name: this.fullName(saved),
          });
        }
        this.isSaving.set(false);
        this.closeForm();
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(screenErrorFrom(err, 'admin.errors.save_moderator_failed'));
        this.isSaving.set(false);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Removal
  // -------------------------------------------------------------------------

  askRemove(moderator: ModeratorAdminView): void {
    this.clearMessages();
    this.pendingRemoval.set(moderator);
  }

  cancelRemove(): void {
    this.pendingRemoval.set(null);
  }

  confirmRemove(): void {
    const moderator = this.pendingRemoval();
    if (!moderator) {
      return;
    }

    this.isRemoving.set(true);
    this.adminService.removeModerator(moderator.id).subscribe({
      next: () => {
        this.moderators.update((rows) => rows.filter((row) => row.id !== moderator.id));
        this.successMessage.set({
          key: 'admin.manage_moderators.removed',
          name: this.fullName(moderator),
        });
        // The form cannot stay open on a row that is no longer on the roster.
        if (this.editing()?.id === moderator.id) {
          this.closeForm();
        }
        this.isRemoving.set(false);
        this.pendingRemoval.set(null);
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(screenErrorFrom(err, 'admin.errors.remove_moderator_failed'));
        this.isRemoving.set(false);
        this.pendingRemoval.set(null);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  /**
   * Trim what the admin typed before it is judged: the request body carries
   * trimmed values, so a pasted `"  sara@example.com  "` must not be validated
   * as a different string from the one about to be sent — Validators.email
   * would reject it while the body would have been perfectly fine.
   */
  private trimTextControls(): void {
    [
      this.form.controls.first_name,
      this.form.controls.last_name,
      this.form.controls.email,
      this.form.controls.alert_email,
    ].forEach((control) => control.setValue(control.value.trim()));
  }

  /** Reading order of the matrix — the same order the API stores cells in. */
  private inMatrixOrder(cells: ModeratorCell[]): ModeratorCell[] {
    return [...cells].sort(
      (a, b) =>
        this.groups.indexOf(a.group) - this.groups.indexOf(b.group) ||
        this.sectors.indexOf(a.sector) - this.sectors.indexOf(b.sector),
    );
  }

  /** The two fields PATCH accepts — also the assignment half of the create body. */
  private assignmentBody(): Required<ModeratorUpdateRequest> {
    const value = this.form.getRawValue();
    return {
      moderator_cells: value.moderator_cells,
      // A blank field means "no separate alert address", not an empty one:
      // alerts then fall back to the moderator's own email.
      alert_email: value.alert_email.trim() || null,
    };
  }

  private createBody(): ModeratorCreateRequest {
    const value = this.form.getRawValue();
    return {
      first_name: value.first_name.trim(),
      last_name: value.last_name.trim(),
      email: value.email.trim(),
      ...this.assignmentBody(),
    };
  }

  private replaceRow(saved: ModeratorAdminView): void {
    this.moderators.update((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
  }

  /**
   * Keeps the list in the surname order the backend lists them in. Re-appointing
   * someone who was removed returns the row they already had, so an id already
   * on the list is replaced rather than duplicated.
   */
  private insertRow(saved: ModeratorAdminView): void {
    this.moderators.update((rows) =>
      [...rows.filter((row) => row.id !== saved.id), saved].sort(
        (a, b) =>
          a.last_name.localeCompare(b.last_name, 'he') ||
          a.first_name.localeCompare(b.first_name, 'he'),
      ),
    );
  }

  private clearMessages(): void {
    this.actionError.set(NO_ERROR);
    this.successMessage.set(null);
  }
}
