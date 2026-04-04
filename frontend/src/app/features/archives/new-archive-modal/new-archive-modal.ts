import { Component, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AgentService } from '../../../services/agent.service';
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

  private nextId = 100;

  constructor(private agentService: AgentService) {}

  close(): void {
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
    if (!this.archiveName() || !this.folderPath()) return;

    const archive: Archive = {
      id: this.nextId++,
      name: this.archiveName(),
      date: new Date().toISOString().split('T')[0],
      files: 0,
      status: 'ingested',
    };

    this.archiveCreated.emit(archive);
    this.reset();
  }

  private reset(): void {
    this.archiveName.set('');
    this.folderPath.set('');
    this.agentUnavailable.set(false);
  }
}
