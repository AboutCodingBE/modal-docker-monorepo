import { Routes } from '@angular/router';
import { ArchiveBrowser } from './features/archives/archive-browser/archive-browser';
import { ArchiveDetail } from './features/archives/archive-detail/archive-detail';
import { ArchiveDashboard } from './features/archives/archive-dashboard/archive-dashboard';
import { ConfigurationPage } from './features/configuration/configuration-page/configuration-page';
import { SemanticSearchPage } from './features/archives/semantic-search/semantic-search-page';

export const routes: Routes = [
  { path: '', redirectTo: 'archives', pathMatch: 'full' },
  { path: 'archives', component: ArchiveBrowser },
  { path: 'archives/:id', component: ArchiveDetail },
  { path: 'archives/:archiveId/dashboard', component: ArchiveDashboard },
  { path: 'archives/:archiveId/search', component: SemanticSearchPage },
  { path: 'config', component: ConfigurationPage },
];
