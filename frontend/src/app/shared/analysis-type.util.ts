export interface AnalysisTypeConfig {
  type: string;
  model: string;
}

export interface AnalysisTypeMeta {
  label: string;
  description: string;
  icon: string;
}

export const ANALYSIS_TYPE_META: Record<string, AnalysisTypeMeta> = {
  SUMMARY: {
    label: 'Samenvatting',
    description: 'AI-gegenereerde samenvattingen per bestand en map.',
    icon: '📝',
  },
  NER: {
    label: 'NER',
    description: 'Detecteert personen, locaties en organisaties.',
    icon: '🔍',
  },
  TOPIC_DETECTION: {
    label: 'Topics',
    description: 'Identificeert de belangrijkste onderwerpen per bestand.',
    icon: '🏷',
  },
};

export interface AnalysisSplit {
  done: AnalysisTypeConfig[];
  pending: AnalysisTypeConfig[];
  allCompleted: boolean;
}

/**
 * Splits the full set of configured analysis types into "done" and "pending"
 * for a given archive, based on archive.completed_analysis_types.
 *
 * Both sides use the same uppercase casing already — no normalization needed.
 */
export function splitAnalysisTypes(
  configuration: AnalysisTypeConfig[],
  completedTypes: string[],
): AnalysisSplit {
  const done = configuration.filter((c) => completedTypes.includes(c.type));
  const pending = configuration.filter((c) => !completedTypes.includes(c.type));
  return {
    done,
    pending,
    allCompleted: configuration.length > 0 && pending.length === 0,
  };
}
