import { Component, OnDestroy, OnInit, computed, signal } from '@angular/core';
import {
  ConfigurationService,
  DownloadProgressEvent,
  ModelEntry,
} from '../../../services/configuration.service';

type DownloadState = 'idle' | 'downloading' | 'success' | 'already-added' | 'error';
type SaveState = 'idle' | 'saving' | 'saved' | 'error';

@Component({
  selector: 'app-configuration-page',
  imports: [],
  templateUrl: './configuration-page.html',
  styleUrl: './configuration-page.css',
})
export class ConfigurationPage implements OnInit, OnDestroy {
  // ── Download section ────────────────────────────────────────────────────
  modelInput = signal('');
  downloadState = signal<DownloadState>('idle');
  downloadModel = signal('');
  downloadProgress = signal<DownloadProgressEvent | null>(null);
  private downloadSource: EventSource | null = null;

  downloadPercentage = computed(() => {
    const p = this.downloadProgress();
    if (!p?.completed_bytes || !p?.total_bytes) return null;
    return Math.round((p.completed_bytes / p.total_bytes) * 100);
  });

  // ── Default models section ──────────────────────────────────────────────
  modelsByType = signal<Record<string, ModelEntry[]>>({});
  selectedIds = signal<Record<string, string>>({});
  modelsLoadError = signal(false);
  modelsSaveState = signal<SaveState>('idle');

  readonly typeOrder = ['SUMMARY', 'NER', 'TOPIC_DETECTION'];
  readonly typeLabels: Record<string, { name: string; desc: string }> = {
    SUMMARY: { name: 'Samenvatting', desc: 'AI samenvattingen' },
    NER: { name: 'NER', desc: 'Entiteitsherkenning' },
    TOPIC_DETECTION: { name: 'Topics', desc: 'Onderwerpdetectie' },
  };

  // ── Processing settings section ─────────────────────────────────────────
  minTextLength = signal(0);
  summaryTopicCharLimit = signal(1000);
  nerCharLimit = signal(6000);
  processingLoadError = signal(false);
  processingSaveState = signal<SaveState>('idle');

  constructor(private configService: ConfigurationService) {}

  ngOnInit(): void {
    this._loadModels();
    this._loadProcessingSettings();
  }

  ngOnDestroy(): void {
    this.downloadSource?.close();
  }

  // ── Download ────────────────────────────────────────────────────────────

  startDownload(): void {
    const model = this.modelInput().trim();
    if (!model || this.downloadState() === 'downloading') return;

    this.downloadState.set('downloading');
    this.downloadModel.set(model);
    this.downloadProgress.set(null);
    this.downloadSource?.close();

    this.configService.startOllamaDownload(model).subscribe({
      next: ({ download_id }) => {
        const source = new EventSource(`/api/models/ollama/${download_id}/progress`);
        this.downloadSource = source;

        source.onmessage = (event) => {
          const data = JSON.parse(event.data) as DownloadProgressEvent;
          this.downloadProgress.set(data);

          if (data.done) {
            source.close();
            this.downloadSource = null;
            if (data.error) {
              this.downloadState.set('error');
            } else if (data.status === 'already added') {
              this.downloadState.set('already-added');
            } else {
              this.downloadState.set('success');
              this._loadModels();
            }
          }
        };

        source.onerror = () => {
          source.close();
          this.downloadSource = null;
          this.downloadProgress.set({
            status: '',
            completed_bytes: null,
            total_bytes: null,
            done: true,
            error: 'Verbinding met server verbroken.',
          });
          this.downloadState.set('error');
        };
      },
      error: () => {
        this.downloadProgress.set({
          status: '',
          completed_bytes: null,
          total_bytes: null,
          done: true,
          error: 'Kon de download niet starten.',
        });
        this.downloadState.set('error');
      },
    });
  }

  resetDownload(): void {
    this.downloadSource?.close();
    this.downloadSource = null;
    this.downloadState.set('idle');
    this.downloadModel.set('');
    this.downloadProgress.set(null);
    this.modelInput.set('');
  }

  formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  // ── Default models ──────────────────────────────────────────────────────

  private _loadModels(): void {
    this.configService.getModels().subscribe({
      next: (models) => {
        this.modelsByType.set(models);
        const ids: Record<string, string> = {};
        for (const type of this.typeOrder) {
          const entries = models[type] ?? [];
          const defaultEntry = entries.find((e) => e.is_default) ?? entries[0];
          if (defaultEntry) ids[type] = defaultEntry.id;
        }
        this.selectedIds.set(ids);
        this.modelsLoadError.set(false);
      },
      error: () => this.modelsLoadError.set(true),
    });
  }

  onModelSelect(type: string, id: string): void {
    this.selectedIds.update((ids) => ({ ...ids, [type]: id }));
  }

  saveDefaultModels(): void {
    if (this.modelsSaveState() === 'saving') return;
    const ids = Object.values(this.selectedIds()).filter(Boolean);
    if (ids.length === 0) return;

    this.modelsSaveState.set('saving');
    this.configService.setDefaultModels(ids).subscribe({
      next: (models) => {
        this.modelsByType.set(models);
        this.modelsSaveState.set('saved');
        setTimeout(() => this.modelsSaveState.set('idle'), 2000);
      },
      error: () => {
        this.modelsSaveState.set('error');
        setTimeout(() => this.modelsSaveState.set('idle'), 3000);
      },
    });
  }

  // ── Processing settings ─────────────────────────────────────────────────

  private _loadProcessingSettings(): void {
    this.configService.getProcessingSettings().subscribe({
      next: (s) => {
        this.minTextLength.set(s.minimum_text_length);
        this.summaryTopicCharLimit.set(s.summary_char_limit);
        this.nerCharLimit.set(s.ner_llm_char_limit);
        this.processingLoadError.set(false);
      },
      error: () => this.processingLoadError.set(true),
    });
  }

  saveProcessingSettings(): void {
    if (this.processingSaveState() === 'saving') return;
    this.processingSaveState.set('saving');
    this.configService
      .updateProcessingSettings({
        summary_char_limit: this.summaryTopicCharLimit(),
        topic_char_limit: this.summaryTopicCharLimit(),
        ner_llm_char_limit: this.nerCharLimit(),
        minimum_text_length: this.minTextLength(),
      })
      .subscribe({
        next: () => {
          this.processingSaveState.set('saved');
          setTimeout(() => this.processingSaveState.set('idle'), 2000);
        },
        error: () => {
          this.processingSaveState.set('error');
          setTimeout(() => this.processingSaveState.set('idle'), 3000);
        },
      });
  }
}
