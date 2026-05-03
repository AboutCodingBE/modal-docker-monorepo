export type ArchiveStatus = 'analysed' | 'ingested' | 'in_progress' | 'failed';

export interface AnalysisProgressEvent {
  task_id: string;
  status: string;
  total_files: number;
  processed: number;
  failed_count: number;
  current_file: string | null;
  percentage: number;
}

export interface Archive {
  id: string;
  name: string;
  date: string;
  files: number;
  status: ArchiveStatus;
  progress?: number;
  tika_task_id?: string;
  analysisEvent?: AnalysisProgressEvent | null;
}
