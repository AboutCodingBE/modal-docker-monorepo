import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FolderData } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

@Component({
  selector: 'app-folder-detail',
  standalone: true,
  imports: [CommonModule, AnalysisSummary],
  templateUrl: './folder-detail.html',
  styleUrl: './folder-detail.css',
})
export class FolderDetail {
  archiveId = input.required<string>();
  folderId = input<string | null>(null);
  folderData = input.required<FolderData>();
  loading = input<boolean>(false);
}
