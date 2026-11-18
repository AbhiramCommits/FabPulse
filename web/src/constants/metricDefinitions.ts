/** Plain-language definitions shown in KPI tooltips and the report glossary. */
export const METRIC_DEFINITIONS: Record<string, string> = {
  uptime_pct:
    'Share of observed time the tool spent processing wafers (productive intervals divided by all intervals).',
  availability_pct:
    'OEE-style availability: productive time divided by planned production time, excluding scheduled maintenance but including standby, engineering and unplanned downtime.',
  mtbf_hours:
    'Mean time between failures: productive hours divided by the number of unscheduled-down episodes.',
  mttr_hours:
    'Mean time to repair: unscheduled-down hours divided by the number of unscheduled-down episodes.',
  throughput:
    'Wafers per productive hour. The fleet card shows the median across tool-days, which is robust to a single slow tool.',
  yield_pct:
    'Mean daily yield across tool-days. The ± value is one standard deviation, showing normal day-to-day spread.',
  wafers_processed:
    'Total wafers processed in the filtered window, summed over productive intervals.',
  fault_events:
    'Count of event intervals that carry a fault code; longer downtime blocks contribute one count per interval.',
}
