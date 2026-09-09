import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FileUploadComponent } from './file-upload.component';
import { HEBREW, translocoTesting } from '../../../../testing/transloco-testing';

const MB = 1024 * 1024;

function makeFile(name: string, type: string, sizeMb: number): File {
  const blob = new Blob([new ArrayBuffer(sizeMb * MB)], { type });
  return new File([blob], name, { type });
}

function triggerChange(fixture: ComponentFixture<FileUploadComponent>, file: File): void {
  const input = fixture.nativeElement.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(input, 'files', {
    value: { 0: file, length: 1, item: () => file },
    configurable: true,
  });
  input.dispatchEvent(new Event('change'));
  fixture.detectChanges();
}

describe('FileUploadComponent', () => {
  let fixture: ComponentFixture<FileUploadComponent>;
  let component: FileUploadComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FileUploadComponent, translocoTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(FileUploadComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // validation
  // ---------------------------------------------------------------------------

  describe('validation', () => {
    it('should emit validationError when file exceeds maxSizeMb', () => {
      const spy = vi.spyOn(component.validationError, 'emit');

      triggerChange(fixture, makeFile('big.jpg', 'image/jpeg', 6));

      // first call: '' (clear previous error), second call: actual error message
      expect(spy).toHaveBeenCalledTimes(2);
      expect(spy.mock.calls[1][0]).toBe('הקובץ גדול מדי. הגודל המקסימלי הוא 5 MB');
    });

    it('emits the size complaint in the active language, with the limit filled in', () => {
      TestBed.inject(TranslocoService).setActiveLang('en');
      const spy = vi.spyOn(component.validationError, 'emit');

      triggerChange(fixture, makeFile('big.jpg', 'image/jpeg', 6));

      expect(spy.mock.calls[1][0]).toBe('The file is too large. The maximum size is 5 MB');
    });

    it('should not emit fileSelected when file exceeds maxSizeMb', () => {
      const spy = vi.spyOn(component.fileSelected, 'emit');

      triggerChange(fixture, makeFile('big.jpg', 'image/jpeg', 6));

      expect(spy).not.toHaveBeenCalled();
    });

    it('should emit empty string to clear previous error on new file selection', () => {
      const spy = vi.spyOn(component.validationError, 'emit');

      triggerChange(fixture, makeFile('valid.jpg', 'image/jpeg', 2));

      expect(spy.mock.calls[0][0]).toBe('');
    });

    it('should clear previous preview when the next file exceeds maxSizeMb', () => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

      triggerChange(fixture, makeFile('valid.jpg', 'image/jpeg', 2));
      expect(component.previewUrl).toBe('blob:fake-url');

      triggerChange(fixture, makeFile('big.jpg', 'image/jpeg', 6));

      expect(component.previewUrl).toBeNull();
    });

    it('should clear previous filename when the next file exceeds maxSizeMb', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));
      expect(component.selectedFileName).toBe('document.pdf');

      triggerChange(fixture, makeFile('big.jpg', 'image/jpeg', 6));

      expect(component.selectedFileName).toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // image file
  // ---------------------------------------------------------------------------

  describe('image file', () => {
    beforeEach(() => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    });

    it('should set previewUrl', () => {
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));

      expect(component.previewUrl).toBe('blob:fake-url');
    });

    it('should not set selectedFileName', () => {
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));

      expect(component.selectedFileName).toBeNull();
    });

    it('should emit fileSelected with the file', () => {
      const spy = vi.spyOn(component.fileSelected, 'emit');
      const file = makeFile('photo.jpg', 'image/jpeg', 2);

      triggerChange(fixture, file);

      expect(spy).toHaveBeenCalledWith(file);
    });

    it('should show preview image in DOM', () => {
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));

      const img = fixture.nativeElement.querySelector('img');
      expect(img).toBeTruthy();
    });
  });

  // ---------------------------------------------------------------------------
  // pdf file
  // ---------------------------------------------------------------------------

  describe('pdf file', () => {
    it('should set selectedFileName', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));

      expect(component.selectedFileName).toBe('document.pdf');
    });

    it('should not set previewUrl', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));

      expect(component.previewUrl).toBeNull();
    });

    it('should not show preview image in DOM', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));

      const img = fixture.nativeElement.querySelector('img');
      expect(img).toBeNull();
    });

    it('should show filename in DOM', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));

      const span = fixture.nativeElement.querySelector('.file-upload__filename');
      expect(span?.textContent?.trim()).toBe('document.pdf');
    });
  });

  // ---------------------------------------------------------------------------
  // clear
  // ---------------------------------------------------------------------------

  describe('clear', () => {
    beforeEach(() => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    });

    it('should reset previewUrl', () => {
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));
      fixture.nativeElement.querySelector('.file-upload__clear').click();
      fixture.detectChanges();

      expect(component.previewUrl).toBeNull();
    });

    it('should reset selectedFileName', () => {
      triggerChange(fixture, makeFile('document.pdf', 'application/pdf', 1));
      fixture.nativeElement.querySelector('.file-upload__clear').click();
      fixture.detectChanges();

      expect(component.selectedFileName).toBeNull();
    });

    it('should call revokeObjectURL', () => {
      const revokeSpy = vi.spyOn(URL, 'revokeObjectURL');
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));
      fixture.nativeElement.querySelector('.file-upload__clear').click();

      expect(revokeSpy).toHaveBeenCalledWith('blob:fake-url');
    });

    it('should emit empty validationError on clear', () => {
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));
      const spy = vi.spyOn(component.validationError, 'emit');
      fixture.nativeElement.querySelector('.file-upload__clear').click();

      expect(spy).toHaveBeenCalledWith('');
    });
  });

  // ---------------------------------------------------------------------------
  // variant
  // ---------------------------------------------------------------------------

  describe('variant', () => {
    it('does not add the primary modifier class by default', () => {
      const btn = fixture.nativeElement.querySelector('.file-upload__btn');
      expect(btn.classList.contains('file-upload__btn--primary')).toBe(false);
    });

    it('adds the primary modifier class when variant is "primary"', () => {
      fixture.componentRef.setInput('variant', 'primary');
      fixture.detectChanges();

      const btn = fixture.nativeElement.querySelector('.file-upload__btn');
      expect(btn.classList.contains('file-upload__btn--primary')).toBe(true);
    });
  });

  // ---------------------------------------------------------------------------
  // destroy
  // ---------------------------------------------------------------------------

  describe('destroy', () => {
    it('should call revokeObjectURL on destroy when previewUrl exists', () => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
      const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));
      fixture.destroy();

      expect(revokeSpy).toHaveBeenCalledWith('blob:fake-url');
    });
  });

  // ---------------------------------------------------------------------------
  // text
  // ---------------------------------------------------------------------------

  describe('text', () => {
    function buttonText(): string {
      return fixture.nativeElement.querySelector('.file-upload__btn').textContent.trim();
    }

    it('falls back to a generic Hebrew button label', () => {
      expect(buttonText()).toBe('בחר קובץ');
    });

    /** Un-migrated call sites still pass a Hebrew literal; it must survive. */
    it('renders a caller-supplied label verbatim, translated or not', () => {
      fixture.componentRef.setInput('label', 'בחר/י תעודת פטירה');
      fixture.detectChanges();

      expect(buttonText()).toBe('בחר/י תעודת פטירה');
    });

    it('renders its own text in English under an English locale', () => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
      triggerChange(fixture, makeFile('photo.jpg', 'image/jpeg', 2));

      TestBed.inject(TranslocoService).setActiveLang('en');
      fixture.detectChanges();

      expect(buttonText()).toBe('Choose file');
      expect(fixture.nativeElement.querySelector('.file-upload__clear').textContent.trim()).toBe(
        'Clear',
      );
      expect(fixture.nativeElement.querySelector('img').getAttribute('alt')).toBe('Preview');
      expect((fixture.nativeElement as HTMLElement).textContent ?? '').not.toMatch(HEBREW);
    });
  });
});
