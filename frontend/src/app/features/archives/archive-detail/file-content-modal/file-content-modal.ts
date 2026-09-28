import { Component, input, output, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FolderFile, ArchiveService } from '../../../../services/archive.service';

@Component({
  selector: 'app-file-content-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './file-content-modal.html',
  styleUrl: './file-content-modal.css',
})
export class FileContentModal implements OnInit {
  file = input.required<FolderFile>();

  closed = output<void>();

  content = signal<string | null>(null);
  loading = signal(true);
  fetchError = signal(false);
  fullText = signal(false);

  private readonly PREVIEW_LENGTH = 1000;

  constructor(private archiveService: ArchiveService) {}

  ngOnInit(): void {
    this.archiveService.getFileContent(this.file().id).subscribe({
      next: (resp) => {
        this.content.set(resp.content);
        this.loading.set(false);
      },
      error: () => {
        this.fetchError.set(true);
        this.loading.set(false);
      },
    });
  }

  displayedContent(): string | null {
    const c = this.content();
    if (c === null) return null;
    if (this.fullText()) return c;
    return c.slice(0, this.PREVIEW_LENGTH);
  }

  isTruncated(): boolean {
    const c = this.content();
    return c !== null && !this.fullText() && c.length > this.PREVIEW_LENGTH;
  }

  toggleFullText(): void {
    this.fullText.update(v => !v);
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.closed.emit();
  }
}
