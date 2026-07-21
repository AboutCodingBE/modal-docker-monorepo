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

interface FileSizeBar {
  name: string;
  size: number;
  category: string;
  color: string;
}

interface HeatmapCell {
  topic: string;
  organization: string;
  value: number;
}

type ItemScope = 'files' | 'folders' | 'both';

interface DashboardEntity {
  id: string;
  name: string;
  relative_path: string;
  size_bytes: number | null;
  category: string | null;
  is_directory: boolean;
}

interface ItemAnalytics {
  ner: { organisations: string[]; persons: string[]; locations: string[]; misc: string[] };
  topics: { topics: string[] };
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
  barChartItems = signal<FileSizeBar[]>([]);
  barChartLegendItems = signal<{ category: string; color: string }[]>([]);
  heatmapTopics = signal<string[]>([]);
  heatmapOrganizations = signal<string[]>([]);
  heatmapCells = signal<HeatmapCell[]>([]);

  tooltipText = signal('');
  tooltipX = signal(0);
  tooltipY = signal(0);
  tooltipVisible = signal(false);
  itemScope = signal<ItemScope>('both');
  allEntities = signal<DashboardEntity[]>([]);

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
    this._renderAllCharts();
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

    this._loadDashboardForFolderContext(archiveId, folderId, currentPath);
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
        this.barChartItems.set([]);
        this._syncTreemapRects();
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Kon de dashboardgegevens voor dit bestand niet laden.');
      },
    });
  }

  private _loadDashboardForFolderContext(archiveId: string, folderId: string | null, currentPath: string): void {
    const folderPath = currentPath && currentPath !== '/' ? currentPath : '/';
    this.archiveService.getFolder(archiveId, folderPath).subscribe({
      next: (folderData) => {
        this.folderName.set(folderData.path || folderPath);
        const activeFolderId = folderId && folderId !== 'root' ? folderId : folderData.folder_id;
        if (activeFolderId) {
          this.folderId.set(activeFolderId);
        }

        const filesRequest = activeFolderId
          ? this.archiveService.getFolderFiles(archiveId, activeFolderId)
          : this.archiveService.getRootFiles(archiveId);

        filesRequest.subscribe({
          next: (data) => {
            const fileEntities: DashboardEntity[] = data.files.map((file) => ({
              id: file.id,
              name: file.name,
              relative_path: file.relative_path,
              size_bytes: file.size_bytes,
              category: file.category ?? null,
              is_directory: false,
            }));

            if (folderData.subfolders.length === 0) {
              this.allEntities.set(fileEntities);
              this._loadLocationsForEntities(archiveId, this._entitiesForScope(fileEntities));
              return;
            }

            const subfolderRequests = folderData.subfolders.map((subfolder) =>
              this.archiveService.getFolder(archiveId, subfolder.path)
            );

            forkJoin(subfolderRequests).subscribe({
              next: (subfolderDetails) => {
                const folderEntities: DashboardEntity[] = subfolderDetails
                  .map((detail, index): DashboardEntity | null => {
                    if (!detail.folder_id) return null;
                    return {
                      id: detail.folder_id,
                      name: folderData.subfolders[index]?.name ?? detail.path,
                      relative_path: folderData.subfolders[index]?.path ?? detail.path,
                      size_bytes: null,
                      category: 'Folder',
                      is_directory: true,
                    };
                  })
                  .filter((entry): entry is DashboardEntity => entry !== null);

                const entities = [...fileEntities, ...folderEntities];
                this.allEntities.set(entities);
                this._loadLocationsForEntities(archiveId, this._entitiesForScope(entities));
              },
              error: () => {
                this.loading.set(false);
                this.error.set('Kon de submappen van deze map niet laden.');
              },
            });
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Kon de bestanden van deze map niet laden.');
          },
        });
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Kon de huidige map niet laden.');
      },
    });
  }

  onScopeChange(scope: ItemScope): void {
    if (this.itemScope() === scope) return;
    this.itemScope.set(scope);

    if (this.selectedFile()) {
      return;
    }

    const scopedEntities = this._entitiesForScope(this.allEntities());
    this.loading.set(true);
    this.error.set(null);
    this._loadLocationsForEntities(this.archiveId(), scopedEntities);
  }

  private _entitiesForScope(entities: DashboardEntity[]): DashboardEntity[] {
    const scope = this.itemScope();
    if (scope === 'files') return entities.filter((entry) => !entry.is_directory);
    if (scope === 'folders') return entities.filter((entry) => entry.is_directory);
    return entities;
  }

  private _loadLocationsForEntities(archiveId: string, entities: DashboardEntity[]): void {
    if (entities.length === 0) {
      this.locationItems.set([]);
      this.personItems.set([]);
      this.organizationItems.set([]);
      this.topicItems.set([]);
      this.barChartItems.set([]);
      this.barChartLegendItems.set([]);
      this.heatmapTopics.set([]);
      this.heatmapOrganizations.set([]);
      this.heatmapCells.set([]);
      this._syncTreemapRects();
      this.loading.set(false);
      return;
    }

    const requests = entities.map((entry) => forkJoin({
      ner: entry.is_directory
        ? this.archiveService.getNerForFolder(archiveId, entry.id)
        : this.archiveService.getNerForFile(archiveId, entry.id),
      topics: entry.is_directory
        ? this.archiveService.getTopicsForFolder(archiveId, entry.id)
        : this.archiveService.getTopicsForFile(archiveId, entry.id),
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
        const barItems = this._buildBarChartItems(entities.filter((entry) => !entry.is_directory));
        this.barChartItems.set(barItems);
        this.barChartLegendItems.set(this._buildBarChartLegend(barItems));

        const topTopics = this._topKeysFromMap(topicCounts, 10);
        const topOrganizations = this._topKeysFromMap(organizationCounts, 10);
        this.heatmapTopics.set(topTopics);
        this.heatmapOrganizations.set(topOrganizations);
        this.heatmapCells.set(this._buildHeatmapCells(results as ItemAnalytics[], topTopics, topOrganizations));

        this._syncTreemapRects();
        setTimeout(() => this._renderAllCharts());
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
    setTimeout(() => this._renderAllCharts());
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

      chart.selectAll('rect.treemap-cell')
        .data(items)
        .enter()
        .append('rect')
        .attr('class', 'treemap-cell')
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
        .attr('y', (d: TreemapRect) => d.y + 6)
        .attr('dominant-baseline', 'hanging')
        .attr('font-size', '11px')
        .attr('fill', 'white')
        .attr('font-weight', '600')
        .text((d: TreemapRect) => d.label)
        .each((d: TreemapRect, index: number, groups: SVGTextElement[] | ArrayLike<SVGTextElement>) => {
          this._fitTreemapLabel(groups[index] as SVGTextElement, d);
        });
    });
  }

  private _fitTreemapLabel(textNode: SVGTextElement, rect: TreemapRect): void {
    const baseFontSize = 11;
    const minFontSize = 6;
    const maxWidth = Math.max(0, rect.width - 12);
    const maxHeight = Math.max(0, rect.height - 8);

    if (maxWidth === 0 || maxHeight === 0) {
      textNode.textContent = '';
      return;
    }

    textNode.textContent = rect.label;
    textNode.setAttribute('font-size', `${baseFontSize}px`);

    const fullWidth = textNode.getComputedTextLength();
    const fullHeight = textNode.getBBox().height;
    const widthScale = fullWidth > 0 ? maxWidth / fullWidth : 1;
    const heightScale = fullHeight > 0 ? maxHeight / fullHeight : 1;
    const scale = Math.min(1, widthScale, heightScale);
    const scaledFontSize = baseFontSize * scale;

    if (scaledFontSize >= minFontSize) {
      textNode.setAttribute('font-size', `${scaledFontSize}px`);
      return;
    }

    textNode.setAttribute('font-size', `${minFontSize}px`);
    textNode.textContent = this._truncateTreemapLabel(textNode, rect.label, maxWidth, maxHeight);
  }

  private _truncateTreemapLabel(
    textNode: SVGTextElement,
    label: string,
    maxWidth: number,
    maxHeight: number,
  ): string {
    let low = 0;
    let high = label.length;
    let best = 0;

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const candidate = label.slice(0, mid);
      textNode.textContent = candidate;

      if (this._treemapTextFits(textNode, maxWidth, maxHeight)) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    return label.slice(0, best);
  }

  private _treemapTextFits(textNode: SVGTextElement, maxWidth: number, maxHeight: number): boolean {
    const width = textNode.getComputedTextLength();
    const height = textNode.getBBox().height;
    return width <= maxWidth && height <= maxHeight;
  }

  private _renderBarChart(): void {
    const svg = this.elementRef.nativeElement.querySelector('svg.bar-chart') as SVGSVGElement | null;
    if (!svg) return;

    const data = this.barChartItems();
    const width = 820;
    const height = 360;
    const margin = { top: 24, right: 18, bottom: 60, left: 120 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    d3.select<SVGSVGElement, FileSizeBar>(svg).selectAll('*').remove();

    if (data.length === 0) {
      d3.select<SVGSVGElement, FileSizeBar>(svg)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#6b7280')
        .attr('font-size', '13px')
        .text('Geen bestanden beschikbaar voor size grafiek.');
      return;
    }

    const xScale = d3.scaleLinear()
      .domain([0, d3.max(data, (item) => item.size) ?? 0])
      .nice()
      .range([0, chartWidth]);

    const yScale = d3.scaleBand<string>()
      .domain(data.map((item) => item.name))
      .range([0, chartHeight])
      .padding(0.18);

    const g = d3.select<SVGSVGElement, FileSizeBar>(svg)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    g.append('g')
      .call(d3.axisLeft(yScale).tickSize(0))
      .selectAll('text')
      .attr('font-size', '12px')
      .attr('fill', '#1f2937')
      .text((d) => {
        const label = String(d);
        return label.length > 24 ? `${label.slice(0, 21)}...` : label;
      })
      .append('title')
      .text((d) => String(d));

    g.append('g')
      .attr('transform', `translate(0,${chartHeight})`)
      .call(d3.axisBottom(xScale).ticks(5).tickFormat((value) => `${d3.format('~s')(value as number)}B`))
      .selectAll('text')
      .attr('font-size', '12px')
      .attr('fill', '#6b7280');

    const bars = g.selectAll('rect.bar')
      .data(data)
      .enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('x', 0)
      .attr('y', (item) => yScale(item.name) ?? 0)
      .attr('width', (item) => xScale(item.size))
      .attr('height', yScale.bandwidth())
      .attr('fill', (item) => item.color)
      .attr('rx', 6);

    bars.append('title')
      .text((item) => `${item.name}: ${d3.format(',')(item.size)} bytes`);

    g.selectAll('text.bar-value')
      .data(data)
      .enter()
      .append('text')
      .attr('class', 'bar-value')
      .attr('x', (item) => xScale(item.size) + 8)
      .attr('y', (item) => (yScale(item.name) ?? 0) + yScale.bandwidth() / 2 + 4)
      .attr('font-size', '11px')
      .attr('fill', '#111827')
      .text((item) => `${d3.format(',')(item.size)} B`);
  }

  private _buildBarChartItems(entities: DashboardEntity[]): FileSizeBar[] {
    const colorMap = this._buildCategoryColorMap(entities);

    return [...entities]
      .filter((entry) => entry.size_bytes !== null)
      .map((entry) => {
        const category = entry.category ?? 'Unknown';
        return {
          name: entry.name,
          size: entry.size_bytes ?? 0,
          category,
          color: colorMap.get(category) ?? this._categoryColor(0),
        };
      })
      .sort((a, b) => b.size - a.size);
  }

  private _buildBarChartLegend(items: FileSizeBar[]): { category: string; color: string }[] {
    const legendMap = new Map<string, string>();
    items.forEach((item) => {
      if (!legendMap.has(item.category)) {
        legendMap.set(item.category, item.color);
      }
    });
    return [...legendMap.entries()].map(([category, color]) => ({ category, color }));
  }

  private _buildCategoryColorMap(entities: DashboardEntity[]): Map<string, string> {
    const categories = Array.from(new Set(entities.map((entry) => entry.category ?? 'Unknown')));
    return new Map<string, string>(
      categories.map((category, index) => [category, this._categoryColor(index)])
    );
  }

  private _topKeysFromMap(counts: Map<string, number>, limit: number): string[] {
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([key]) => key);
  }

  private _buildHeatmapCells(
    results: ItemAnalytics[],
    topTopics: string[],
    topOrganizations: string[]
  ): HeatmapCell[] {
    const counts = new Map<string, number>();

    results.forEach(({ ner, topics }) => {
      const topicSet = new Set(topics.topics);
      const orgSet = new Set(ner.organisations);
      topTopics.forEach((topic) => {
        if (!topicSet.has(topic)) return;
        topOrganizations.forEach((organization) => {
          if (!orgSet.has(organization)) return;
          const key = `${topic}|||${organization}`;
          counts.set(key, (counts.get(key) ?? 0) + 1);
        });
      });
    });

    const cells: HeatmapCell[] = [];
    topTopics.forEach((topic) => {
      topOrganizations.forEach((organization) => {
        const key = `${topic}|||${organization}`;
        cells.push({
          topic,
          organization,
          value: counts.get(key) ?? 0,
        });
      });
    });

    return cells;
  }

  private _renderHeatmap(): void {
    const svg = this.elementRef.nativeElement.querySelector('svg.heatmap') as SVGSVGElement | null;
    if (!svg) return;

    const topics = this.heatmapTopics();
    const organizations = this.heatmapOrganizations();
    const cells = this.heatmapCells();

    const width = 820;
    const height = 420;
    const margin = { top: 60, right: 16, bottom: 80, left: 160 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    d3.select<SVGSVGElement, HeatmapCell>(svg).selectAll('*').remove();

    if (topics.length === 0 || organizations.length === 0) {
      d3.select<SVGSVGElement, HeatmapCell>(svg)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet')
        .append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#6b7280')
        .attr('font-size', '13px')
        .text('Geen heatmapgegevens beschikbaar.');
      return;
    }

    const maxValue = d3.max(cells, (item) => item.value) ?? 0;
    const colorScale = d3.scaleLinear<string>()
      .domain([0, maxValue || 1])
      .range(['#7f1d1d', '#fee2e2']);

    const xScale = d3.scaleBand<string>()
      .domain(organizations)
      .range([0, chartWidth])
      .padding(0.05);

    const yScale = d3.scaleBand<string>()
      .domain(topics)
      .range([0, chartHeight])
      .padding(0.05);

    const g = d3.select<SVGSVGElement, HeatmapCell>(svg)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    g.append('g')
      .selectAll('rect')
      .data(cells)
      .enter()
      .append('rect')
      .attr('x', (item) => xScale(item.organization) ?? 0)
      .attr('y', (item) => yScale(item.topic) ?? 0)
      .attr('width', xScale.bandwidth())
      .attr('height', yScale.bandwidth())
      .attr('fill', (item) => colorScale(item.value))
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 1)
      .append('title')
      .text((item) => `${item.topic} / ${item.organization}: ${item.value}`);

    g.append('g')
      .attr('transform', `translate(0,${chartHeight})`)
      .call(d3.axisBottom(xScale).tickSize(0))
      .selectAll('text')
      .attr('font-size', '11px')
      .attr('fill', '#111827')
      .attr('text-anchor', 'end')
      .attr('transform', 'rotate(-45)');

    g.append('g')
      .call(d3.axisLeft(yScale).tickSize(0))
      .selectAll('text')
      .attr('font-size', '12px')
      .attr('fill', '#111827');

    g.append('text')
      .attr('x', chartWidth / 2)
      .attr('y', -26)
      .attr('text-anchor', 'middle')
      .attr('fill', '#111827')
      .attr('font-size', '13px')
      .attr('font-weight', '600')
      .text('Top 10 topics × top 10 organisaties');
  }

  private _renderAllCharts(): void {
    this._renderAllTreemaps();
    this._renderBarChart();
    this._renderHeatmap();
  }

  private _categoryColor(index: number): string {
    const palette = ['#2563eb', '#16a34a', '#d97706', '#7c3aed', '#0f766e', '#be123c', '#6b7280', '#8b5cf6'];
    return palette[index % palette.length];
  }
}
