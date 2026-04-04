export type ArchiveStatus = 'analysed' | 'ingested' | 'in_progress' | 'failed';

export interface Archive {
  id: number;
  name: string;
  date: string;
  files: number;
  status: ArchiveStatus;
}
