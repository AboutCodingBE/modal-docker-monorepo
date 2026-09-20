import {
  Component,
  computed,
  effect,
  inject,
  input,
  OnDestroy,
  output,
  signal,
  untracked,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScrollingModule, CdkVirtualScrollViewport } from '@angular/cdk/scrolling';
import { Subject, debounceTime, filter, switchMap, takeUntil } from 'rxjs';
import { ArchiveService, FolderFile } from '../../../../services/archive.service';

type SortField = 'content_created_at' | 'relative_path' | 'category';
type SortDir = 'asc' | 'desc';

const ENTITY_TYPES = [
  { label: 'Persoon', value: 'persons' },
  { label: 'Locatie', value: 'locations' },
  { label: 'Organisatie', value: 'organisations' },
  { label: 'Overige', value: 'misc' },
] as const;

const ENTITY_LABEL: Record<string, string> = {
  persons: 'Persoon',
  locations: 'Locatie',
  organisations: 'Organisatie',
  misc: 'Overige',
};

export const ROW_HEIGHT = 32;

interface Badge {
  facet: 'category' | 'language' | 'entity' | 'topic';
  value: string;
  label: string;
}

@Component({
  selector: 'app-list-view',
  standalone: true,
  imports: [CommonModule, ScrollingModule],
  templateUrl: './list-view.html',
  styleUrl: './list-view.css',
})
export class ListView implements OnDestroy {
  @ViewChild(CdkVirtualScrollViewport) viewport!: CdkVirtualScrollViewport;

  archiveId = input.required<string>();
  folderPath = input<string>('/');

  fileSelected = output<FolderFile>();

  private archiveService = inject(ArchiveService);

  readonly entityTypes = ENTITY_TYPES;
  readonly rowHeight = ROW_HEIGHT;

  // ── Sort ──
  sortBy = signal<SortField>('content_created_at');
  sortDir = signal<SortDir>('desc');

  // ── Active filters ──
  activeCategories = signal<string[]>([]);
  activeLanguages = signal<string[]>([]);
  activeEntities = signal<string[]>([]);   // 'type:text' format
  activeTopics = signal<string[]>([]);

  // ── Pagination / data ──
  files = signal<FolderFile[]>([]);
  cursorId = signal<string | null>(null);
  cursorValue = signal<string | null>(null);
  hasNext = signal(false);
  loading = signal(false);
  loadingMore = signal(false);

  // ── Selected row ──
  selectedFileId = signal<string | null>(null);

  // ── Popover state ──
  klassePopoverOpen = signal(false);
  taalPopoverOpen = signal(false);
  tempCategories = signal<string[]>([]);
  tempLanguages = signal<string[]>([]);

  // ── Autocomplete ──
  entityType = signal('persons');
  entityDropdownOpen = signal(false);
  entitySuggestions = signal<string[]>([]);
  topicDropdownOpen = signal(false);
  topicSuggestions = signal<string[]>([]);

  // ── Derived ──
  availableCategories = computed(() =>
    [...new Set(this.files().map(f => f.category).filter((c): c is string => !!c))].sort()
  );

  availableLanguages = computed(() =>
    [...new Set(this.files().map(f => f.language).filter((l): l is string => !!l))].sort()
  );

  badges = computed<Badge[]>(() => [
    ...this.activeCategories().map(v => ({ facet: 'category' as const, value: v, label: `Klasse: ${v}` })),
    ...this.activeLanguages().map(v => ({ facet: 'language' as const, value: v, label: `Taal: ${v}` })),
    ...this.activeEntities().map(v => {
      const [type, ...rest] = v.split(':');
      return { facet: 'entity' as const, value: v, label: `${ENTITY_LABEL[type] ?? type}: ${rest.join(':')}` };
    }),
    ...this.activeTopics().map(v => ({ facet: 'topic' as const, value: v, label: `Topic: ${v}` })),
  ]);

  hasActiveFilters = computed(() => this.badges().length > 0);

  private entityInput$ = new Subject<string>();
  private topicInput$ = new Subject<string>();
  private destroy$ = new Subject<void>();

  constructor() {
    // Refetch when folder, sort, or any filter changes
    effect(() => {
      this.folderPath();
      this.sortBy();
      this.sortDir();
      this.activeCategories();
      this.activeLanguages();
      this.activeEntities();
      this.activeTopics();
      untracked(() => this._fetchFiles(true));
    });

    // Entity autocomplete
    this.entityInput$
      .pipe(
        debounceTime(250),
        filter(q => q.length >= 1),
        switchMap(q =>
          this.archiveService.autocompleteEntities(this.archiveId(), this.entityType(), q)
        ),
        takeUntil(this.destroy$),
      )
      .subscribe(res => {
        this.entitySuggestions.set(res.suggestions);
        this.entityDropdownOpen.set(res.suggestions.length > 0);
      });

    // Topic autocomplete
    this.topicInput$
      .pipe(
        debounceTime(250),
        filter(q => q.length >= 1),
        switchMap(q => this.archiveService.autocompleteTopics(this.archiveId(), q)),
        takeUntil(this.destroy$),
      )
      .subscribe(res => {
        this.topicSuggestions.set(res.suggestions);
        this.topicDropdownOpen.set(res.suggestions.length > 0);
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ── Sort ──

  onSort(field: SortField): void {
    if (this.sortBy() === field) {
      this.sortDir.update(d => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      this.sortBy.set(field);
      this.sortDir.set('desc');
    }
    // effect handles refetch
  }

  sortArrow(field: SortField): string {
    if (this.sortBy() !== field) return '↕';
    return this.sortDir() === 'desc' ? '↓' : '↑';
  }

  // ── Klasse popover ──

  openKlassePopover(): void {
    this.tempCategories.set([...this.activeCategories()]);
    this.klassePopoverOpen.set(true);
    this.taalPopoverOpen.set(false);
  }

  toggleTempCategory(value: string): void {
    this.tempCategories.update(arr =>
      arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value]
    );
  }

  applyKlasse(): void {
    this.activeCategories.set([...this.tempCategories()]);
    this.klassePopoverOpen.set(false);
  }

  clearKlasse(): void {
    this.activeCategories.set([]);
    this.tempCategories.set([]);
    this.klassePopoverOpen.set(false);
  }

  // ── Taal popover ──

  openTaalPopover(): void {
    this.tempLanguages.set([...this.activeLanguages()]);
    this.taalPopoverOpen.set(true);
    this.klassePopoverOpen.set(false);
  }

  toggleTempLanguage(value: string): void {
    this.tempLanguages.update(arr =>
      arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value]
    );
  }

  applyTaal(): void {
    this.activeLanguages.set([...this.tempLanguages()]);
    this.taalPopoverOpen.set(false);
  }

  clearTaal(): void {
    this.activeLanguages.set([]);
    this.tempLanguages.set([]);
    this.taalPopoverOpen.set(false);
  }

  // ── Entity autocomplete ──

  onEntityTypeChange(event: Event): void {
    this.entityType.set((event.target as HTMLSelectElement).value);
    this.entitySuggestions.set([]);
    this.entityDropdownOpen.set(false);
  }

  onEntityInput(event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    if (!val.trim()) {
      this.entityDropdownOpen.set(false);
      return;
    }
    this.entityInput$.next(val.trim());
  }

  selectEntity(text: string, inputEl: HTMLInputElement): void {
    const entry = `${this.entityType()}:${text}`;
    if (!this.activeEntities().includes(entry)) {
      this.activeEntities.update(arr => [...arr, entry]);
    }
    inputEl.value = '';
    this.entityDropdownOpen.set(false);
    this.entitySuggestions.set([]);
  }

  // ── Topic autocomplete ──

  onTopicInput(event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    if (!val.trim()) {
      this.topicDropdownOpen.set(false);
      return;
    }
    this.topicInput$.next(val.trim());
  }

  selectTopic(topic: string, inputEl: HTMLInputElement): void {
    if (!this.activeTopics().includes(topic)) {
      this.activeTopics.update(arr => [...arr, topic]);
    }
    inputEl.value = '';
    this.topicDropdownOpen.set(false);
    this.topicSuggestions.set([]);
  }

  // ── Badge removal ──

  removeBadge(badge: Badge): void {
    switch (badge.facet) {
      case 'category':
        this.activeCategories.update(arr => arr.filter(v => v !== badge.value));
        break;
      case 'language':
        this.activeLanguages.update(arr => arr.filter(v => v !== badge.value));
        break;
      case 'entity':
        this.activeEntities.update(arr => arr.filter(v => v !== badge.value));
        break;
      case 'topic':
        this.activeTopics.update(arr => arr.filter(v => v !== badge.value));
        break;
    }
  }

  // ── Row selection ──

  onRowClick(file: FolderFile): void {
    this.selectedFileId.set(file.id);
    this.fileSelected.emit(file);
  }

  closePopovers(): void {
    this.klassePopoverOpen.set(false);
    this.taalPopoverOpen.set(false);
  }

  closeDropdowns(): void {
    this.entityDropdownOpen.set(false);
    this.topicDropdownOpen.set(false);
  }

  // ── Infinite scroll ──

  onScrolledIndexChange(_index: number): void {
    if (!this.viewport) return;
    const end = this.viewport.getRenderedRange().end;
    if (end >= this.files().length - 5 && this.hasNext() && !this.loadingMore() && !this.loading()) {
      this._loadMore();
    }
  }

  // ── Formatting helpers ──

  formatSize(bytes: number | null): string {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }

  formatDate(iso: string | null): string {
    if (!iso) return '—';
    return iso.split('T')[0];
  }

  formatPath(relativePath: string): string {
    const parts = relativePath.split('/');
    parts.pop(); // remove filename
    return parts.length === 0 || (parts.length === 1 && parts[0] === '')
      ? '/'
      : '/' + parts.join('/') + '/';
  }

  isCategoryActive(value: string): boolean {
    return this.activeCategories().includes(value);
  }

  isLanguageActive(value: string): boolean {
    return this.activeLanguages().includes(value);
  }

  isTempCategoryChecked(value: string): boolean {
    return this.tempCategories().includes(value);
  }

  isTempLanguageChecked(value: string): boolean {
    return this.tempLanguages().includes(value);
  }

  // ── Private fetch logic ──

  private _folderPathParam(): string | undefined {
    const path = this.folderPath();
    if (path === '/') return undefined;
    return path.replace(/^\//, '');
  }

  private _fetchFiles(reset: boolean): void {
    if (reset) {
      this.files.set([]);
      this.cursorId.set(null);
      this.cursorValue.set(null);
      this.hasNext.set(false);
      this.selectedFileId.set(null);
    }

    this.loading.set(true);

    this.archiveService
      .listFiles(this.archiveId(), {
        folder_path: this._folderPathParam(),
        sort_by: this.sortBy(),
        sort_dir: this.sortDir(),
        categories: this.activeCategories(),
        languages: this.activeLanguages(),
        entities: this.activeEntities(),
        topics: this.activeTopics(),
        cursor_id: this.cursorId() ?? undefined,
        cursor_value: this.cursorValue() ?? undefined,
      })
      .subscribe({
        next: res => {
          this.files.update(existing => [...existing, ...res.files]);
          this.cursorId.set(res.next_cursor_id);
          this.cursorValue.set(res.next_cursor_value);
          this.hasNext.set(res.has_next);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  private _loadMore(): void {
    if (!this.cursorId()) return;
    this.loadingMore.set(true);

    this.archiveService
      .listFiles(this.archiveId(), {
        folder_path: this._folderPathParam(),
        sort_by: this.sortBy(),
        sort_dir: this.sortDir(),
        categories: this.activeCategories(),
        languages: this.activeLanguages(),
        entities: this.activeEntities(),
        topics: this.activeTopics(),
        cursor_id: this.cursorId()!,
        cursor_value: this.cursorValue() ?? undefined,
      })
      .subscribe({
        next: res => {
          this.files.update(existing => [...existing, ...res.files]);
          this.cursorId.set(res.next_cursor_id);
          this.cursorValue.set(res.next_cursor_value);
          this.hasNext.set(res.has_next);
          this.loadingMore.set(false);
        },
        error: () => this.loadingMore.set(false),
      });
  }
}
