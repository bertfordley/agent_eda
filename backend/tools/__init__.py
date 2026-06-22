from tools.bigquery_tools import (
    bq_list_datasets, bq_list_tables, bq_describe_table,
    bq_run_query, bq_profile_dataset,
)
from tools.drive_tools import (
    sheet_from_url, drive_search_files, drive_read_sheet,
    drive_read_doc, drive_read_csv, drive_upload_file,
)
from tools.analysis_tools import (
    df_describe, df_correlations, df_value_counts,
    df_group_by, df_time_series, df_detect_outliers, df_compare,
    df_check_key,
)
from tools.viz_tools import (
    chart_bar, chart_line, chart_scatter,
    chart_histogram, chart_heatmap, chart_interactive,
)
from tools.report_tools import (
    report_start, report_add_section, report_add_chart,
    report_generate_html, report_generate_pdf, report_to_drive,
)

ALL_TOOLS = [
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
]
