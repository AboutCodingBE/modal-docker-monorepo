import { Component, AfterViewInit, ElementRef, inject, input, output, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';
import * as d3 from 'd3';
import { ArchiveService, FolderFile, NerResult, TopicsResult } from '../../../services/archive.service';

interface DashboardNavigationState {
  selectedFile?: FolderFile | null;
  folderId?: string | null;
  currentPath?: string;
  folderName?: string;
}

interface TreemapItem {
  label: string;
  value: number;
  color: string;
  children?: TreemapItem[];
}

interface TreemapRect {
  label: string;
  value: number;
  color: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

@Component({
  selector: 'app-archive-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './archive-dashboard.html',
  styleUrl: './archive-dashboard.css',
})
export class ArchiveDashboard implements OnInit, AfterViewInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private archiveService = inject(ArchiveService);
  private elementRef = inject(ElementRef<HTMLElement>);

  archiveIdInput = input<string>('');
  selectedFileInput = input<FolderFile | null>(null);
  folderIdInput = input<string | null>(null);
  currentPathInput = input<string>('/');
  folderNameInput = input<string>('Root');
  closed = output<void>();

  archiveId = signal('');
  selectedFile = signal<FolderFile | null>(null);
  folderId = signal<string | null>(null);
  currentPath = signal('/');
  folderName = signal('Root');
  loading = signal(true);
  error = signal<string | null>(null);
  locationItems = signal<TreemapItem[]>([]);
  personItems = signal<TreemapItem[]>([]);
  organizationItems = signal<TreemapItem[]>([]);
  topicItems = signal<TreemapItem[]>([]);

  locationTreemapRects = signal<TreemapRect[]>([]);
  personTreemapRects = signal<TreemapRect[]>([]);
  organizationTreemapRects = signal<TreemapRect[]>([]);
  topicTreemapRects = signal<TreemapRect[]>([]);

  tooltipText = signal('');
  tooltipX = signal(0);
  tooltipY = signal(0);
  tooltipVisible = signal(false);

  ngOnInit(): void {
    const routeArchiveId = this.route.snapshot.paramMap.get('archiveId') ?? '';
    const archiveId = this.archiveIdInput() || routeArchiveId;
    const state = this.router.getCurrentNavigation()?.extras.state as DashboardNavigationState | undefined;

    const selectedFile = this.selectedFileInput() ?? state?.selectedFile ?? null;
    const folderId = this.folderIdInput() ?? state?.folderId ?? null;
    const currentPath = this.currentPathInput() !== '/' || this.folderIdInput() ? this.currentPathInput() : (state?.currentPath ?? '/');
    const folderName = this.folderNameInput() || state?.folderName || (currentPath === '/' ? 'Root' : currentPath.split('/').filter(Boolean).pop() ?? 'Root');

    this.archiveId.set(archiveId);
    this.selectedFile.set(selectedFile);
    this.folderId.set(folderId);
    this.currentPath.set(currentPath);
    this.folderName.set(folderName);

    this._loadData(archiveId, selectedFile, folderId, currentPath);
  }

  ngAfterViewInit(): void {
    this._renderAllTreemaps();
  }

  goBack(): void {
    this.closed.emit();
  }

  private _loadData(archiveId: string, selectedFile: FolderFile | null, folderId: string | null, currentPath: string): void {
    this.loading.set(true);
    this.error.set(null);

    if (selectedFile) {
      this._loadLocationsForFile(archiveId, selectedFile.id);
      return;
    }

    if (!folderId || folderId === 'root') {
      if (currentPath && currentPath !== '/') {
        this.archiveService.getFolder(archiveId, currentPath).subscribe({
          next: (folder) => {
            this.folderName.set(folder.path || currentPath);
            if (folder.folder_id) {
              this.folderId.set(folder.folder_id);
              this.archiveService.getFolderFiles(archiveId, folder.folder_id).subscribe({
                next: (data) => this._loadLocationsForFiles(archiveId, data.files),
                error: () => {
                  this.loading.set(false);
                  this.error.set('Kon de bestanden van deze map niet laden.');
                },
              });
            } else {
              this.locationItems.set([]);
              this.loading.set(false);
            }
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Kon de huidige map niet laden.');
          },
        });
      } else {
        this.archiveService.getRootFiles(archiveId).subscribe({
          next: (data) => this._loadLocationsForFiles(archiveId, data.files),
          error: () => {
            this.loading.set(false);
            this.error.set('Kon de bestanden van de rootmap niet laden.');
          },
        });
      }
      return;
    }

    this.archiveService.getFolderFiles(archiveId, folderId).subscribe({
      next: (data) => this._loadLocationsForFiles(archiveId, data.files),
      error: () => {
        this.loading.set(false);
        this.error.set('Kon de bestanden van deze map niet laden.');
      },
    });
  }

  private _loadLocationsForFile(archiveId: string, fileId: string): void {
    forkJoin({
      ner: this.archiveService.getNerForFile(archiveId, fileId),
      topics: this.archiveService.getTopicsForFile(archiveId, fileId),
    }).subscribe({
      next: ({ ner, topics }) => {
        this.locationItems.set(this._buildItemsFromNer(ner, 'locations'));
        this.personItems.set(this._buildItemsFromNer(ner, 'persons'));
        this.organizationItems.set(this._buildItemsFromNer(ner, 'organisations'));
        this.topicItems.set(this._buildItemsFromTopics(topics));
        this._syncTreemapRects();
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Kon de dashboardgegevens voor dit bestand niet laden.');
      },
    });
  }

  private _loadLocationsForFiles(archiveId: string, files: FolderFile[]): void {
    if (files.length === 0) {
      this.locationItems.set([]);
      this.personItems.set([]);
      this.organizationItems.set([]);
      this.topicItems.set([]);
      this.loading.set(false);
      return;
    }

    const requests = files.map((file) => forkJoin({
      ner: this.archiveService.getNerForFile(archiveId, file.id),
      topics: this.archiveService.getTopicsForFile(archiveId, file.id),
    }));

    forkJoin(requests).subscribe({
      next: (results) => {
        const locationCounts = new Map<string, number>();
        const personCounts = new Map<string, number>();
        const organizationCounts = new Map<string, number>();
        const topicCounts = new Map<string, number>();

        results.forEach(({ ner, topics }) => {
          this._addNerValues(locationCounts, ner.locations);
          this._addNerValues(personCounts, ner.persons);
          this._addNerValues(organizationCounts, ner.organisations);
          this._addTopicValues(topicCounts, topics.topics);
        });

        this.locationItems.set(this._buildItemsFromMap(locationCounts));
        this.personItems.set(this._buildItemsFromMap(personCounts));
        this.organizationItems.set(this._buildItemsFromMap(organizationCounts));
        this.topicItems.set(this._buildItemsFromMap(topicCounts));
        this._syncTreemapRects();
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Kon de dashboardgegevens voor deze map niet laden.');
      },
    });
  }

  private _buildItemsFromNer(data: NerResult, field: 'locations' | 'persons' | 'organisations'): TreemapItem[] {
    const counts = new Map<string, number>();
    this._addNerValues(counts, data[field] as string[]);
    return this._buildItemsFromMap(counts);
  }

  private _buildItemsFromTopics(data: TopicsResult): TreemapItem[] {
    const counts = new Map<string, number>();
    this._addTopicValues(counts, data.topics);
    return this._buildItemsFromMap(counts);
  }

  private _addNerValues(counts: Map<string, number>, values: string[]): void {
    values.forEach((value) => {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    });
  }

  private _addTopicValues(counts: Map<string, number>, values: string[]): void {
    values.forEach((value) => {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    });
  }

  private _buildItemsFromMap(counts: Map<string, number>): TreemapItem[] {
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, value], index) => ({
        label,
        value,
        color: this._colorForIndex(index),
      }));
  }

  private _colorForIndex(index: number): string {
    const palette = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#14b8a6', '#f97316', '#6366f1'];
    return palette[index % palette.length];
  }

  private _syncTreemapRects(): void {
    this.locationTreemapRects.set(this._computeTreemapRects(this.locationItems()));
    this.personTreemapRects.set(this._computeTreemapRects(this.personItems()));
    this.organizationTreemapRects.set(this._computeTreemapRects(this.organizationItems()));
    this.topicTreemapRects.set(this._computeTreemapRects(this.topicItems()));
    setTimeout(() => this._renderAllTreemaps());
  }

  private _computeTreemapRects(items: TreemapItem[]): TreemapRect[] {
    if (items.length === 0) return [];

    const hierarchy = d3.hierarchy<TreemapItem>({
      label: 'root',
      value: 0,
      color: '#ffffff',
      children: items,
    })
      .sum((d: TreemapItem) => d.value)
      .sort((a: d3.HierarchyNode<TreemapItem>, b: d3.HierarchyNode<TreemapItem>) => (b.value ?? 0) - (a.value ?? 0));

    const treemapLayout = d3.treemap<TreemapItem>()
      .tile(d3.treemapBinary)
      .size([320, 220])
      .paddingInner(3);

    const root = treemapLayout(hierarchy);

    return (root.leaves() as d3.HierarchyRectangularNode<TreemapItem>[]).map((leaf) => ({
      label: leaf.data.label,
      value: leaf.data.value,
      color: leaf.data.color,
      x: leaf.x0,
      y: leaf.y0,
      width: leaf.x1 - leaf.x0,
      height: leaf.y1 - leaf.y0,
    }));
  }

  private _renderAllTreemaps(): void {
    const svgNodes = Array.from(this.elementRef.nativeElement.querySelectorAll('svg.treemap')) as SVGSVGElement[];
    const svgMap = new Map<string, SVGSVGElement>();
    svgNodes.forEach((svg) => {
      const key = (svg.dataset as DOMStringMap)['treemapKey'];
      if (key) {
        svgMap.set(key, svg);
      }
    });

    const dataSets: Record<string, TreemapRect[]> = {
      locations: this.locationTreemapRects(),
      persons: this.personTreemapRects(),
      organisations: this.organizationTreemapRects(),
      topics: this.topicTreemapRects(),
    };

    Object.entries(dataSets).forEach(([key, items]) => {
      const svg = svgMap.get(key);
      if (!svg) return;

      const width = 320;
      const height = 220;
      d3.select<SVGSVGElement, TreemapRect>(svg).selectAll('*').remove();

      if (items.length === 0) return;

      const chart = d3.select<SVGSVGElement, TreemapRect>(svg)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet');

      chart.selectAll('rect')
        .data(items)
        .enter()
        .append('rect')
        .attr('x', (d: TreemapRect) => d.x)
        .attr('y', (d: TreemapRect) => d.y)
        .attr('width', (d: TreemapRect) => d.width)
        .attr('height', (d: TreemapRect) => d.height)
        .attr('fill', (d: TreemapRect) => d.color)
        .attr('stroke', 'rgba(255,255,255,0.7)')
        .attr('stroke-width', 1.5)
        .on('mouseover', (event: MouseEvent, d: TreemapRect) => {
          this.tooltipText.set(`${d.label}: ${d.value}`);
          this.tooltipX.set(event.clientX + 12);
          this.tooltipY.set(event.clientY + 12);
          this.tooltipVisible.set(true);
        })
        .on('mousemove', (event: MouseEvent) => {
          this.tooltipX.set(event.clientX + 12);
          this.tooltipY.set(event.clientY + 12);
        })
        .on('mouseout', () => {
          this.tooltipVisible.set(false);
        })
        .append('title')
        .text((d: TreemapRect) => `${d.label}: ${d.value}`);

      chart.selectAll('text')
        .data(items)
        .enter()
        .append('text')
        .attr('x', (d: TreemapRect) => d.x + 6)
        .attr('y', (d: TreemapRect) => d.y + 16)
        .attr('font-size', '11px')
        .attr('fill', 'white')
        .attr('font-weight', '600')
        .text((d: TreemapRect) => d.label.length > 15 ? `${d.label.slice(0, 12)}...` : d.label);
    });
  }

}
