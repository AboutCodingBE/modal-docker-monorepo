import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ArchiveService, FolderFile } from '../../../services/archive.service';
import { LiteralSearchService, LiteralSearchResult } from '../../../services/literal-search.service';
import { FileDetail } from '../archive-detail/file-detail/file-detail';
import { FileContentModal } from '../archive-detail/file-content-modal/file-content-modal';

@Component({
  selector: 'app-literal-search-page',
  imports: [CommonModule, FormsModule, FileDetail, FileContentModal],
  templateUrl: './literal-search-page.html',
  styleUrl: './literal-search-page.css',
})
export class LiteralSearchPage implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private archiveService = inject(ArchiveService);
  private searchService = inject(LiteralSearchService);

  archiveId = signal('');
  archiveName = signal('');

  query = signal('');
  searching = signal(false);
  loadingMore = signal(false);
  searchError = signal(false);

  results = signal<LiteralSearchResult[] | null>(null);
  hasNext = signal(false);
  nextCursorId = signal<string | null>(null);
  nextCursorValue = signal<string | null>(null);

  selectedResult = signal<LiteralSearchResult | null>(null);
  selectedFile = signal<FolderFile | null>(null);
  modalFile = signal<FolderFile | null>(null);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('archiveId') ?? '';
    this.archiveId.set(id);
    this.archiveService.getStats(id).subscribe({
      next: (stats) => this.archiveName.set(stats.name),
    });
  }

  goBack(): void {
    this.router.navigate(['/archives', this.archiveId()]);
  }

  runSearch(): void {
    const q = this.query().trim();
    if (!q || this.searching()) return;
    this.searching.set(true);
    this.searchError.set(false);
    this.selectedResult.set(null);
    this.selectedFile.set(null);

    this.searchService.search(this.archiveId(), q).subscribe({
      next: (res) => {
        this.results.set(res.files);
        this.hasNext.set(res.has_next);
        this.nextCursorId.set(res.next_cursor_id);
        this.nextCursorValue.set(res.next_cursor_value);
        this.searching.set(false);
      },
      error: () => {
        this.searchError.set(true);
        this.searching.set(false);
      },
    });
  }

  loadMore(): void {
    if (this.loadingMore() || !this.hasNext()) return;
    this.loadingMore.set(true);

    this.searchService
      .search(this.archiveId(), this.query().trim(), this.nextCursorId(), this.nextCursorValue())
      .subscribe({
        next: (res) => {
          this.results.update((prev) => [...(prev ?? []), ...res.files]);
          this.hasNext.set(res.has_next);
          this.nextCursorId.set(res.next_cursor_id);
          this.nextCursorValue.set(res.next_cursor_value);
          this.loadingMore.set(false);
        },
        error: () => this.loadingMore.set(false),
      });
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') this.runSearch();
  }

  selectResult(result: LiteralSearchResult): void {
    const isSame = this.selectedResult()?.id === result.id;
    if (isSame) {
      this.selectedResult.set(null);
      this.selectedFile.set(null);
    } else {
      this.selectedResult.set(result);
      this.selectedFile.set(this._toFolderFile(result));
    }
  }

  openModal(result: LiteralSearchResult): void {
    this.modalFile.set(this._toFolderFile(result));
  }

  closeModal(): void {
    this.modalFile.set(null);
  }

  private _toFolderFile(result: LiteralSearchResult): FolderFile {
    return {
      id: result.id,
      name: result.name,
      relative_path: result.relative_path,
      extension: null,
      size_bytes: null,
      mime_type: null,
      category: null,
      language: null,
      author: null,
      content_created_at: null,
    };
  }
}
