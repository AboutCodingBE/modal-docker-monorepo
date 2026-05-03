import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FolderFile } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

@Component({
  selector: 'app-file-detail',
  standalone: true,
  imports: [CommonModule, AnalysisSummary],
  templateUrl: './file-detail.html',
  styleUrl: './file-detail.css',
})
export class FileDetail {
  archiveId = input.required<string>();
  file = input.required<FolderFile>();
  currentFolderPath = input.required<string>();

  back = output<void>();

  formatSize(bytes: number | null): string {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }
}
