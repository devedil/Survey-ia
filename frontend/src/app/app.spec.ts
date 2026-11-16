import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { App } from './app';

describe('App', () => {
  let httpTesting: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
    fixture.detectChanges();
    httpTesting.expectOne('http://127.0.0.1:8000/api/v1/profiles').flush([]);
  });

  it('should render the controlled browser workflow', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    httpTesting.expectOne('http://127.0.0.1:8000/api/v1/profiles').flush([]);
    await fixture.whenStable();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('AI Survey Assistant');
    expect(compiled.textContent).toContain('Iniciar navegador de prueba');
    expect(compiled.textContent).toContain('La aplicación nunca pulsa «Enviar»');
    expect(compiled.textContent).not.toContain('Aprobar respuesta');
  });

  it('separates human approval from filling the form', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    httpTesting.expectOne('http://127.0.0.1:8000/api/v1/profiles').flush([
      { id: 'profile-1', name: 'Test profile' },
    ]);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const profileSelect = root.querySelector('#profile') as HTMLSelectElement;
    profileSelect.value = 'profile-1';
    profileSelect.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const startButton = Array.from(root.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Iniciar navegador de prueba'),
    );
    startButton?.click();
    fixture.detectChanges();
    httpTesting
      .expectOne('http://127.0.0.1:8000/api/v1/browser/sessions')
      .flush({
        session_id: 'session-1',
        profile_id: 'profile-1',
        status: 'active',
        current_url: null,
      });
    await fixture.whenStable();
    httpTesting
      .expectOne('http://127.0.0.1:8000/api/v1/browser/sessions/session-1/navigate')
      .flush({
        session_id: 'session-1',
        profile_id: 'profile-1',
        status: 'active',
        current_url: 'http://127.0.0.1:8000/api/v1/browser/test-site',
      });
    await fixture.whenStable();
    httpTesting
      .expectOne('http://127.0.0.1:8000/api/v1/browser/sessions/session-1/inspect')
      .flush({
        url: 'http://127.0.0.1:8000/api/v1/browser/test-site',
        title: 'Local form',
        controls: [
          {
            control_id: 'control-0',
            question_text: 'What city?',
            control_type: 'text',
            options: [],
            required: true,
            max_length: 80,
          },
        ],
      });
    await fixture.whenStable();
    fixture.detectChanges();

    const proposeButton = Array.from(root.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Proponer'),
    );
    proposeButton?.click();
    fixture.detectChanges();
    httpTesting
      .expectOne('http://127.0.0.1:8000/api/v1/browser/sessions/session-1/propose')
      .flush({
        proposal_id: 'proposal-1',
        status: 'pending',
        suggested_answer: 'Madrid',
        support_status: 'supported',
        confidence: 0.9,
        sources: [],
        needs_user_input: false,
        needs_review: true,
      });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root.textContent).toContain('Aprobar respuesta');
    expect(root.textContent).not.toContain('Rellenar campo aprobado');
    const approveButton = Array.from(root.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Aprobar respuesta'),
    );
    approveButton?.click();
    fixture.detectChanges();
    httpTesting
      .expectOne((request) => request.url.endsWith('/answers/proposal-1/approve'))
      .flush({
        proposal_id: 'proposal-1',
        status: 'approved',
        suggested_answer: 'Madrid',
        support_status: 'supported',
        confidence: 0.9,
        sources: [],
        needs_user_input: false,
        needs_review: false,
      });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(root.textContent).toContain('Aprobada explícitamente');
    expect(root.textContent).toContain('Rellenar campo aprobado');
    const fillButton = Array.from(root.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Rellenar campo aprobado'),
    );
    fillButton?.click();
    fixture.detectChanges();
    const fillRequest = httpTesting.expectOne(
      'http://127.0.0.1:8000/api/v1/browser/sessions/session-1/fill-approved',
    );
    expect(fillRequest.request.body).toEqual({
      control_id: 'control-0',
      proposal_id: 'proposal-1',
    });
    fillRequest.flush({ verified: true, status: 'filled' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('rellenado y verificado');
  });
});
