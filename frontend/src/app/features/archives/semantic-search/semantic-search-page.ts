import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ArchiveService } from '../../../services/archive.service';
import { SemanticSearchService, SearchResultGroup, SearchChunk } from '../../../services/semantic-search.service';
import { SseProgressEvent } from '../../../shared/progress-bar/progress-bar';

type DownloadState = 'idle' | 'downloading' | 'done' | 'error';
type AnalysisState = 'idle' | 'running' | 'done' | 'error';

@Component({
  selector: 'app-semantic-search-page',
  imports: [CommonModule, FormsModule],
  templateUrl: './semantic-search-page.html',
  styleUrl: './semantic-search-page.css',
})
export class SemanticSearchPage implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private archiveService = inject(ArchiveService);
  private searchService = inject(SemanticSearchService);

  archiveId = signal('');
  archiveName = signal('');
  embeddingReady = signal(false);

  // Step 1 — model download
  downloadState = signal<DownloadState>('idle');
  downloadCompleted = signal<number | null>(null);
  downloadTotal = signal<number | null>(null);
  downloadError = signal<string | null>(null);
  private downloadSource: EventSource | null = null;

  downloadPercent = computed(() => {
    const c = this.downloadCompleted();
    const t = this.downloadTotal();
    if (c == null || t == null || t === 0) return 0;
    return Math.round((c / t) * 100);
  });

  downloadProgressText = computed(() => {
    const c = this.downloadCompleted();
    const t = this.downloadTotal();
    if (c == null || t == null) return 'Downloaden...';
    return `${this._formatBytes(c)} / ${this._formatBytes(t)}`;
  });

  step1Done = computed(() => this.downloadState() === 'done');

  // Step 2 — embedding analysis
  analysisState = signal<AnalysisState>('idle');
  analysisProgress = signal<SseProgressEvent | null>(null);
  private analysisSource: EventSource | null = null;

  analysisPercent = computed(() => this.analysisProgress()?.percentage ?? 0);
  analysisProgressText = computed(() => {
    const p = this.analysisProgress();
    if (!p) return '';
    const file = p.current_file ? p.current_file.split('/').pop() : null;
    return file ? `${p.processed}/${p.total_files} — ${file}` : `${p.processed}/${p.total_files}`;
  });

  // Search
  query = signal('');
  searching = signal(false);
  searchError = signal(false);
  results = signal<SearchResultGroup[] | null>(null);
  selectedGroup = signal<SearchResultGroup | null>(null);
  modalChunk = signal<SearchChunk | null>(null);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('archiveId') ?? '';
    this.archiveId.set(id);
    this.archiveService.getStats(id).subscribe({
      next: (stats) => {
        this.archiveName.set(stats.name);
        this.embeddingReady.set(stats.completed_analysis_types.includes('EMBEDDING'));
      },
    });
  }

  ngOnDestroy(): void {
    this.downloadSource?.close();
    this.analysisSource?.close();
  }

  goBack(): void {
    this.router.navigate(['/archives', this.archiveId()]);
  }

  // ── Step 1: download model ────────────────────────────────────────────────

  startDownload(): void {
    if (this.downloadState() === 'downloading') return;
    this.downloadState.set('downloading');
    this.downloadError.set(null);
    this.downloadSource?.close();

    this.searchService.downloadEmbeddingModel().subscribe({
      next: ({ download_id }) => {
        const source = new EventSource(`/api/models/ollama/${download_id}/progress`);
        this.downloadSource = source;

        source.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.error) {
            this.downloadState.set('error');
            this.downloadError.set(data.error);
            source.close();
            return;
          }
          if (data.completed_bytes != null) this.downloadCompleted.set(data.completed_bytes);
          if (data.total_bytes != null) this.downloadTotal.set(data.total_bytes);
          if (data.done) {
            this.downloadState.set('done');
            source.close();
          }
        };

        source.onerror = () => {
          this.downloadState.set('error');
          this.downloadError.set('Verbinding verbroken');
          source.close();
        };
      },
      error: () => {
        this.downloadState.set('error');
        this.downloadError.set('Kon download niet starten');
      },
    });
  }

  // ── Step 2: run embedding analysis ───────────────────────────────────────

  startAnalysis(): void {
    if (this.analysisState() === 'running') return;
    this.analysisState.set('running');
    this.analysisSource?.close();

    this.searchService.startEmbeddingAnalysis(this.archiveId()).subscribe({
      next: ({ task_ids }) => {
        if (!task_ids.length) {
          // Already completed
          this.analysisState.set('done');
          this.embeddingReady.set(true);
          return;
        }
        const taskId = task_ids[0];
        const source = new EventSource(`/api/analysis/tasks/${taskId}/progress`);
        this.analysisSource = source;

        source.onmessage = (event) => {
          const data = JSON.parse(event.data) as SseProgressEvent;
          this.analysisProgress.set(data);
          if (data.status === 'completed') {
            this.analysisState.set('done');
            this.embeddingReady.set(true);
            source.close();
          } else if (data.status === 'failed') {
            this.analysisState.set('error');
            source.close();
          }
        };

        source.onerror = () => {
          this.analysisState.set('error');
          source.close();
        };
      },
      error: () => this.analysisState.set('error'),
    });
  }

  // ── Search ────────────────────────────────────────────────────────────────

  runSearch(): void {
    const q = this.query().trim();
    if (!q || this.searching()) return;
    this.searching.set(true);
    this.searchError.set(false);
    this.selectedGroup.set(null);

    this.searchService.search(this.archiveId(), q).subscribe({
      next: (raw) => {
        this.results.set(this.searchService.groupResults(raw));
        this.searching.set(false);
      },
      error: () => {
        this.searchError.set(true);
        this.searching.set(false);
      },
    });
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') this.runSearch();
  }

  selectGroup(group: SearchResultGroup): void {
    this.selectedGroup.set(group === this.selectedGroup() ? null : group);
  }

  openModal(chunk: SearchChunk): void {
    this.modalChunk.set(chunk);
  }

  closeModal(): void {
    this.modalChunk.set(null);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private _formatBytes(bytes: number): string {
    if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`;
    return `${(bytes / 1_000).toFixed(0)} KB`;
  }
}
