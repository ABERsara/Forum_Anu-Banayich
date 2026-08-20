/**
 * Manage professionals – the admin's view of the professional catalog.
 *
 * Lists every professional (listed and unlisted alike), adds new ones, edits
 * their routing — which bereavement groups and which sectors they serve — and
 * flips them in and out of the member-facing catalog at /advice.
 */

import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import {
  AbstractControl,
  FormBuilder,
  FormControl,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  GROUP_VISIBILITY_LABELS,
  GroupVisibility,
  PROFESSIONAL_DOMAIN_LABELS,
  ProfessionalDomain,
  SECTOR_VISIBILITY_LABELS,
  SectorVisibility,
} from '../../../core/constants';
import {
  ProfessionalAdminView,
  ProfessionalCreateRequest,
  ProfessionalUpdateRequest,
} from '../../../core/models';
import { AdminService } from '../../../core/services/admin.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

/** Mirrors PROFESSIONAL_DESCRIPTION_MAX_LENGTH in backend/app/schemas/user.py. */
const DESCRIPTION_MAX_LENGTH = 500;

/** An audience (groups or sectors) with nothing ticked reaches no member at all. */
export function atLeastOneSelected(control: AbstractControl): ValidationErrors | null {
  const value: unknown = control.value;
  return Array.isArray(value) && value.length > 0 ? null : { required: true };
}

@Component({
  selector: 'app-manage-professionals',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    ButtonComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './manage-professionals.component.html',
  styleUrl: './manage-professionals.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ManageProfessionalsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly adminService = inject(AdminService);

  readonly professionals = signal<ProfessionalAdminView[]>([]);
  readonly isLoading = signal(false);
  readonly hasError = signal(false);
  readonly actionError = signal('');
  readonly successMessage = signal('');
  readonly isSaving = signal(false);
  readonly isFormOpen = signal(false);
  /** The professional being edited; null while the form is adding a new one. */
  readonly editing = signal<ProfessionalAdminView | null>(null);
  /** Row whose active toggle is in flight, so only its own button is disabled. */
  readonly togglingId = signal<string | null>(null);

  readonly domainLabels = PROFESSIONAL_DOMAIN_LABELS;
  readonly groupLabels = GROUP_VISIBILITY_LABELS;
  readonly sectorLabels = SECTOR_VISIBILITY_LABELS;
  readonly domains = Object.values(ProfessionalDomain);
  readonly groupOptions = Object.values(GroupVisibility);
  readonly sectorOptions = Object.values(SectorVisibility);
  readonly allGroups = GroupVisibility.ALL;
  readonly allSectors = SectorVisibility.ALL;
  readonly descriptionMaxLength = DESCRIPTION_MAX_LENGTH;

  /**
   * One form serves both modes. When editing, the identity controls are
   * disabled — name and email are not part of the PUT contract — which also
   * keeps them out of `form.value` and out of the request body.
   */
  readonly form = this.fb.nonNullable.group({
    first_name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    last_name: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    email: ['', [Validators.required, Validators.email]],
    phone: ['', [Validators.minLength(9), Validators.maxLength(15)]],
    professional_domain: [ProfessionalDomain.LAWYER, Validators.required],
    professional_groups: this.fb.nonNullable.control<GroupVisibility[]>(
      [GroupVisibility.ALL],
      atLeastOneSelected,
    ),
    professional_sectors: this.fb.nonNullable.control<SectorVisibility[]>(
      [SectorVisibility.ALL],
      atLeastOneSelected,
    ),
    professional_description: ['', Validators.maxLength(DESCRIPTION_MAX_LENGTH)],
    is_active_professional: [true],
  });

  private readonly identityControls = [
    this.form.controls.first_name,
    this.form.controls.last_name,
    this.form.controls.email,
    this.form.controls.phone,
  ];

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.adminService.getProfessionals().subscribe({
      next: (professionals) => {
        this.professionals.set(professionals);
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

  fullName(professional: ProfessionalAdminView): string {
    return `${professional.first_name} ${professional.last_name}`;
  }

  domainLabel(professional: ProfessionalAdminView): string {
    return professional.professional_domain
      ? this.domainLabels[professional.professional_domain]
      : 'ללא תחום';
  }

  /** "אלמנות, יתומות" – who this professional is offered to. */
  audienceLabel(values: string[], labels: Record<string, string>): string {
    return values.map((value) => labels[value] ?? value).join(', ');
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

  openEditForm(professional: ProfessionalAdminView): void {
    this.clearMessages();
    this.editing.set(professional);
    this.form.patchValue({
      professional_domain: professional.professional_domain ?? ProfessionalDomain.OTHER,
      professional_groups: professional.professional_groups,
      professional_sectors: professional.professional_sectors,
      professional_description: professional.professional_description ?? '',
      is_active_professional: professional.is_active_professional,
    });
    this.identityControls.forEach((control) => control.disable());
    this.isFormOpen.set(true);
  }

  closeForm(): void {
    this.isFormOpen.set(false);
    this.editing.set(null);
  }

  isChecked<T extends string>(control: FormControl<T[]>, option: T): boolean {
    return control.value.includes(option);
  }

  /**
   * Tick or untick one audience option. "כולם" and a narrower pick contradict
   * each other, so choosing either one drops the other.
   */
  toggleAudience<T extends GroupVisibility | SectorVisibility>(
    control: FormControl<T[]>,
    option: T,
    all: T,
  ): void {
    const selected = control.value;
    let next: T[];
    if (selected.includes(option)) {
      next = selected.filter((value) => value !== option);
    } else if (option === all) {
      next = [all];
    } else {
      next = [...selected.filter((value) => value !== all), option];
    }
    control.setValue(next);
    control.markAsTouched();
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const editing = this.editing();
    this.isSaving.set(true);
    this.clearMessages();

    const request$ = editing
      ? this.adminService.updateProfessional(editing.id, this.profileBody())
      : this.adminService.addProfessional(this.createBody());

    request$.subscribe({
      next: (saved) => {
        if (editing) {
          this.replaceRow(saved);
          this.successMessage.set(`הפרטים של ${this.fullName(saved)} עודכנו.`);
        } else {
          this.insertRow(saved);
          this.successMessage.set(`${this.fullName(saved)} נוסף לקטלוג אנשי המקצוע.`);
        }
        this.isSaving.set(false);
        this.closeForm();
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFrom(err, 'אירעה שגיאה בשמירת איש המקצוע. נסה שוב.'));
        this.isSaving.set(false);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Active toggle
  // -------------------------------------------------------------------------

  toggleActive(professional: ProfessionalAdminView): void {
    this.clearMessages();
    this.togglingId.set(professional.id);

    const body: ProfessionalUpdateRequest = {
      is_active_professional: !professional.is_active_professional,
    };

    this.adminService.updateProfessional(professional.id, body).subscribe({
      next: (saved) => {
        this.replaceRow(saved);
        this.successMessage.set(
          saved.is_active_professional
            ? `${this.fullName(saved)} מופיע שוב בקטלוג.`
            : `${this.fullName(saved)} הושבת ואינו מופיע בקטלוג.`,
        );
        this.togglingId.set(null);
      },
      error: (err: HttpErrorResponse) => {
        this.actionError.set(this.messageFrom(err, 'אירעה שגיאה בעדכון הסטטוס. נסה שוב.'));
        this.togglingId.set(null);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  /** The five fields PUT accepts — also the profile half of the create body. */
  private profileBody(): Required<ProfessionalUpdateRequest> {
    const value = this.form.getRawValue();
    return {
      professional_domain: value.professional_domain,
      professional_groups: value.professional_groups,
      professional_sectors: value.professional_sectors,
      // A blank textarea means "no description", not an empty one.
      professional_description: value.professional_description.trim() || null,
      is_active_professional: value.is_active_professional,
    };
  }

  private createBody(): ProfessionalCreateRequest {
    const value = this.form.getRawValue();
    return {
      first_name: value.first_name.trim(),
      last_name: value.last_name.trim(),
      email: value.email.trim(),
      phone: value.phone.trim() || null,
      ...this.profileBody(),
    };
  }

  private replaceRow(saved: ProfessionalAdminView): void {
    this.professionals.update((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
  }

  /** Keeps the list in the surname order the backend lists them in. */
  private insertRow(saved: ProfessionalAdminView): void {
    this.professionals.update((rows) =>
      [...rows, saved].sort(
        (a, b) =>
          a.last_name.localeCompare(b.last_name, 'he') ||
          a.first_name.localeCompare(b.first_name, 'he'),
      ),
    );
  }

  private messageFrom(err: HttpErrorResponse, fallback: string): string {
    const detail: unknown = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }

  private clearMessages(): void {
    this.actionError.set('');
    this.successMessage.set('');
  }
}
