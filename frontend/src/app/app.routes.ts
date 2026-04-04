import { Routes } from '@angular/router';
import { ArchiveBrowser } from './features/archives/archive-browser/archive-browser';

export const routes: Routes = [
  { path: '', redirectTo: 'archives', pathMatch: 'full' },
  { path: 'archives', component: ArchiveBrowser },
];
