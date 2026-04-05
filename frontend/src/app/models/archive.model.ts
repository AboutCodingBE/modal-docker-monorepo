export type ArchiveStatus = 'analysed' | 'ingested' | 'in_progress' | 'failed';

export interface Archive {
  id: string;
  name: string;
  date: string;
  files: number;
  status: ArchiveStatus;
  progress?: number;
}
