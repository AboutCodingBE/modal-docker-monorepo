import { Component, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AgentService } from '../../../services/agent.service';
import { ArchiveService } from '../../../services/archive.service';
import { Archive } from '../../../models/archive.model';

@Component({
  selector: 'app-new-archive-modal',
  imports: [FormsModule],
  templateUrl: './new-archive-modal.html',
  styleUrl: './new-archive-modal.css',
})
export class NewArchiveModal {
  isOpen = input.required<boolean>();

  closed = output<void>();
  archiveCreated = output<Archive>();

  archiveName = signal('');
  folderPath = signal('');
  agentUnavailable = signal(false);
  selectingFolder = signal(false);
  submitting = signal(false);
  submitError = signal<string | null>(null);

  constructor(
    private agentService: AgentService,
    private archiveService: ArchiveService,
  ) {}

  close(): void {
    if (this.submitting()) return;
    this.reset();
    this.closed.emit();
  }

  onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.close();
    }
  }

  selectFolder(): void {
    this.agentUnavailable.set(false);
    this.selectingFolder.set(true);

    this.agentService.checkHealth().subscribe((status) => {
      if (!status.available) {
        this.agentUnavailable.set(true);
        this.selectingFolder.set(false);
        return;
      }

      this.agentService.pickFolder().subscribe({
        next: (result) => {
          this.folderPath.set(result.path);
          this.selectingFolder.set(false);
        },
        error: () => {
          this.agentUnavailable.set(true);
          this.selectingFolder.set(false);
        },
      });
    });
  }

  submit(): void {
    if (!this.archiveName() || !this.folderPath() || this.submitting()) return;

    this.submitting.set(true);
    this.submitError.set(null);

    this.archiveService.create(this.archiveName(), this.folderPath()).subscribe({
      next: (archive) => {
        this.archiveCreated.emit(archive);
        this.reset();
      },
      error: (err) => {
        this.submitError.set(err.error?.detail ?? 'Er is een fout opgetreden.');
        this.submitting.set(false);
      },
    });
  }

  private reset(): void {
    this.archiveName.set('');
    this.folderPath.set('');
    this.agentUnavailable.set(false);
    this.submitError.set(null);
    this.submitting.set(false);
  }
}
