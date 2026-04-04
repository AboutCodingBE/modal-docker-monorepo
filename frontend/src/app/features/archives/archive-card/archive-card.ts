import { Component, input } from '@angular/core';
import { Archive } from '../../../models/archive.model';

@Component({
  selector: 'app-archive-card',
  templateUrl: './archive-card.html',
  styleUrl: './archive-card.css',
})
export class ArchiveCard {
  archive = input.required<Archive>();

  get statusLabel(): string {
    return this.archive().status.toUpperCase().replace('_', ' ');
  }

  get statusClass(): string {
    return `status-${this.archive().status}`;
  }
}
