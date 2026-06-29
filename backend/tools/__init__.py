from collections.abc import Callable

from tools.analysis_tools import (
    df_check_key,
    df_compare,
    df_correlations,
    df_describe,
    df_detect_outliers,
    df_group_by,
    df_time_series,
    df_value_counts,
)
from tools.bigquery_tools import (
    bq_describe_table,
    bq_list_datasets,
    bq_list_tables,
    bq_profile_dataset,
    bq_run_query,
)
from tools.drive_tools import (
    drive_read_csv,
    drive_read_doc,
    drive_read_sheet,
    drive_search_files,
    drive_upload_file,
    sheet_from_url,
)
from tools.report_tools import (
    report_add_chart,
    report_add_section,
    report_generate_html,
    report_generate_pdf,
    report_start,
    report_to_drive,
)
from tools.skill_tools import load_skill
from tools.viz_tools import (
    chart_bar,
    chart_heatmap,
    chart_histogram,
    chart_interactive,
    chart_line,
    chart_scatter,
)

ALL_TOOLS: list[Callable] = [
    # Data ingestion
    bq_list_datasets, bq_list_tables, bq_describe_table,
    bq_run_query, bq_profile_dataset,
    sheet_from_url,                        # ← Google Sheet URL drop-in
    drive_search_files, drive_read_sheet,
    drive_read_doc, drive_read_csv, drive_upload_file,
    # Analysis — df_check_key listed before df_compare so the agent
    # learns to call it first when building a join key.
    df_check_key, df_describe, df_correlations, df_value_counts,
    df_group_by, df_time_series, df_detect_outliers, df_compare,
    # Visualisation
    chart_bar, chart_line, chart_scatter,
    chart_histogram, chart_heatmap, chart_interactive,
    # Reports
    report_start, report_add_section, report_add_chart,
    report_generate_html, report_generate_pdf, report_to_drive,
    # Skills (progressive disclosure of analysis playbooks)
    load_skill,
]
