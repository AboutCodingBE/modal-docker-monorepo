import { Routes } from '@angular/router';
import { ArchiveBrowser } from './features/archives/archive-browser/archive-browser';
import { ArchiveDetail } from './features/archives/archive-detail/archive-detail';

export const routes: Routes = [
  { path: '', redirectTo: 'archives', pathMatch: 'full' },
  { path: 'archives', component: ArchiveBrowser },
  { path: 'archives/:id', component: ArchiveDetail },
];
