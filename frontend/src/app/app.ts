import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import {
  AnswerProposal,
  BrowserApi,
  BrowserControl,
  BrowserInspection,
  BrowserSession,
  Profile,
} from './browser-api';

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  private readonly api = inject(BrowserApi);
  protected readonly title = signal('AI Survey Assistant');
  protected readonly profiles = signal<Profile[]>([]);
  protected readonly profileId = signal('');
  protected readonly profileName = signal('');
  protected readonly session = signal<BrowserSession | null>(null);
  protected readonly controls = signal<BrowserControl[]>([]);
  protected readonly selectedControlId = signal('');
  protected readonly proposal = signal<AnswerProposal | null>(null);
  protected readonly answerDraft = signal('');
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly error = signal('');
  protected readonly selectedControl = computed(
    () => this.controls().find((control) => control.control_id === this.selectedControlId()) ?? null,
  );

  ngOnInit(): void {
    void this.loadProfiles();
  }

  protected async loadProfiles(): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    try {
      this.profiles.set(await firstValueFrom(this.api.listProfiles()));
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async createProfile(): Promise<void> {
    const name = this.profileName().trim();
    if (!name) return;
    this.busy.set(true);
    this.error.set('');
    try {
      const profile = await firstValueFrom(this.api.createProfile(name));
      this.profiles.update((profiles) => [...profiles, profile]);
      this.profileId.set(profile.id);
      this.profileName.set('');
      this.message.set('Perfil creado.');
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async startSession(): Promise<void> {
    if (!this.profileId()) return;
    this.busy.set(true);
    this.error.set('');
    this.message.set('');
    try {
      const session = await firstValueFrom(this.api.createSession(this.profileId()));
      this.session.set(session);
      await firstValueFrom(this.api.navigate(session.session_id));
      await this.loadInspection(session.session_id);
      this.message.set('Formulario local inspeccionado. No se ha enviado.');
    } catch (error: unknown) {
      this.reportError(error);
      await this.refreshSessionStatus();
    } finally {
      this.busy.set(false);
    }
  }

  protected async inspectPage(): Promise<void> {
    const session = this.session();
    if (!session) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.loadInspection(session.session_id);
      this.message.set('Formulario inspeccionado. No se ha enviado.');
    } catch (error: unknown) {
      this.reportError(error);
      await this.refreshSessionStatus();
    } finally {
      this.busy.set(false);
    }
  }

  protected async propose(control: BrowserControl): Promise<void> {
    const session = this.session();
    if (!session) return;
    this.selectedControlId.set(control.control_id);
    this.proposal.set(null);
    this.answerDraft.set('');
    this.busy.set(true);
    this.error.set('');
    try {
      const proposal = await firstValueFrom(
        this.api.propose(session.session_id, control.control_id),
      );
      this.proposal.set(proposal);
      this.answerDraft.set(proposal.suggested_answer);
      this.message.set('Propuesta lista para revisión; todavía no está aprobada.');
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async approveProposal(): Promise<void> {
    const session = this.session();
    const profileId = this.profileId();
    const proposal = this.proposal();
    if (!session || !profileId || !proposal?.proposal_id) return;
    this.busy.set(true);
    this.error.set('');
    try {
      let candidate = proposal;
      if (this.answerDraft().trim() !== proposal.suggested_answer) {
        candidate = await firstValueFrom(
          this.api.correct(proposal.proposal_id, profileId, this.answerDraft()),
        );
        this.proposal.set(candidate);
      }
      const approved = await firstValueFrom(this.api.approve(proposal.proposal_id, profileId));
      this.proposal.set(approved);
      this.message.set('Respuesta aprobada por ti. Aún no se ha rellenado ni enviado.');
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async fillApproved(): Promise<void> {
    const session = this.session();
    const proposal = this.proposal();
    const control = this.selectedControl();
    if (!session || !control || !proposal?.proposal_id || proposal.status !== 'approved') return;
    this.busy.set(true);
    this.error.set('');
    try {
      await firstValueFrom(
        this.api.fillApproved(session.session_id, control.control_id, proposal.proposal_id),
      );
      this.message.set('Valor aprobado rellenado y verificado. El formulario no se envió.');
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  protected async stopSession(): Promise<void> {
    const session = this.session();
    if (!session) return;
    this.busy.set(true);
    this.error.set('');
    try {
      this.session.set(await firstValueFrom(this.api.stop(session.session_id)));
      this.message.set('Sesión del navegador detenida.');
    } catch (error: unknown) {
      this.reportError(error);
    } finally {
      this.busy.set(false);
    }
  }

  private reportError(error: unknown): void {
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail;
      this.error.set(typeof detail === 'string' ? detail : 'La solicitud al backend falló.');
      return;
    }
    this.error.set('No se pudo completar la acción.');
  }

  private async loadInspection(sessionId: string): Promise<void> {
    const result: BrowserInspection = await firstValueFrom(this.api.inspect(sessionId));
    this.controls.set(result.controls);
  }

  private async refreshSessionStatus(): Promise<void> {
    const session = this.session();
    if (!session) return;
    try {
      this.session.set(await firstValueFrom(this.api.getSession(session.session_id)));
    } catch (error: unknown) {
      this.reportError(error);
    }
  }
}
