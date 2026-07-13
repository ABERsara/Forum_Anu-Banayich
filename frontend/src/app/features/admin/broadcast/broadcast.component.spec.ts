import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { BroadcastComponent } from './broadcast.component';
import { AdminService } from '../../../core/services/admin.service';
import { ForumPost } from '../../../core/models';

describe('BroadcastComponent', () => {
  let fixture: ComponentFixture<BroadcastComponent>;
  let component: BroadcastComponent;
  let sendBroadcastMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    sendBroadcastMock = vi.fn();

    await TestBed.configureTestingModule({
      imports: [BroadcastComponent],
      providers: [
        provideRouter([]),
        { provide: AdminService, useValue: { sendBroadcast: sendBroadcastMock } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(BroadcastComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should show field errors when submitting an empty form', () => {
    component.onSubmit();
    fixture.detectChanges();

    const errors = fixture.nativeElement.querySelectorAll('.field-error');
    expect(errors.length).toBeGreaterThan(0);
    expect(sendBroadcastMock).not.toHaveBeenCalled();
  });

  it('should call AdminService.sendBroadcast with the form values on submit', () => {
    sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();

    expect(sendBroadcastMock).toHaveBeenCalledWith({
      title: 'הודעה חשובה',
      content: 'תוכן ההודעה',
    });
  });

  it('should show a success message and reset the form after a successful send', () => {
    sendBroadcastMock.mockReturnValue(of({ id: 'p1' } as ForumPost));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.successMessage()).not.toBe('');
    expect(component.isLoading()).toBe(false);
    expect(component.form.value.title).toBeFalsy();
  });

  it('should show Hebrew error message and hide spinner on server error', () => {
    sendBroadcastMock.mockReturnValue(throwError(() => ({ error: { detail: 'שגיאת שרת' } })));
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('שגיאת שרת');
    expect(component.isLoading()).toBe(false);
    expect(fixture.nativeElement.querySelector('app-loading-spinner')).toBeNull();
  });

  it('should disable submit button while loading', () => {
    sendBroadcastMock.mockReturnValue(new Subject());
    component.form.setValue({ title: 'הודעה חשובה', content: 'תוכן ההודעה' });

    component.onSubmit();
    fixture.detectChanges();

    const btn = fixture.nativeElement.querySelector('.btn-submit') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
