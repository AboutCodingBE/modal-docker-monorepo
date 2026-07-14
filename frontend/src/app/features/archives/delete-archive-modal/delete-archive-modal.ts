import { Component, input, output } from '@angular/core';
import { Archive } from '../../../models/archive.model';

@Component({
  selector: 'app-delete-archive-modal',
  templateUrl: './delete-archive-modal.html',
  styleUrl: './delete-archive-modal.css',
})
export class DeleteArchiveModal {
  archive = input.required<Archive>();

  confirmed = output<void>();
  cancelled = output<void>();

  onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.cancelled.emit();
    }
  }
}
