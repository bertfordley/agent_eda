import type {
  User, Conversation, ChatMessage, Artifact,
  ChartImageArtifact, ChartInteractiveArtifact, TableArtifact, Report,
} from "@/types";

const NOW = Date.now();

export const mockUser: User = {
  id: "u_1",
  email: "analyst@acme.com",
  displayName: "Bert Analyst",
  avatarUrl: null,
};

export const mockArtifacts: Artifact[] = [
  {
    id: "a_1", kind: "chart_image", title: "Revenue by Region (Q2)",
    url: "http://localhost:8000/charts/bar_demo01.png", filename: "bar_demo01.png",
    createdAt: NOW - 110000, messageId: "m_2",
  } satisfies ChartImageArtifact,
  {
    id: "a_2", kind: "chart_interactive", title: "Monthly Revenue Trend",
    url: "http://localhost:8000/charts/interactive_demo02.html", filename: "interactive_demo02.html",
    createdAt: NOW - 60000, messageId: "m_4",
  } satisfies ChartInteractiveArtifact,
  {
    id: "a_3", kind: "chart_image", title: "Churn Correlation Heatmap",
    url: "http://localhost:8000/charts/heatmap_demo03.png", filename: "heatmap_demo03.png",
    createdAt: NOW - 93600000, messageId: "m_6",
  } satisfies ChartImageArtifact,
  {
    id: "a_4", kind: "table", title: "Region Revenue Table",
    columns: ["region", "revenue_usd", "orders"],
    rows: [["West", 4200000, 1820], ["East", 3100000, 1455], ["Central", 2050000, 990], ["South", 1780000, 860]],
    createdAt: NOW - 115000, messageId: "m_2",
  } satisfies TableArtifact,
];

export const mockReports: Report[] = [
  {
    id: "r_1", title: "Q2 Revenue Report", filename: "q2_revenue_report_a3f8c1.html",
    url: "http://localhost:8000/reports/q2_revenue_report_a3f8c1.html",
    format: "html", createdAt: NOW - 180000,
  },
  {
    id: "r_2", title: "Churn Analysis", filename: "churn_analysis_b7d2e9.html",
    url: "http://localhost:8000/reports/churn_analysis_b7d2e9.html",
    format: "html", createdAt: NOW - 97200000,
  },
];

export const mockMessages: ChatMessage[] = [
  { id: "m_1", role: "user", content: "Pull Q2 revenue by region from the sales table", status: "complete", createdAt: NOW - 120000, artifactIds: [], errorText: null },
  { id: "m_2", role: "assistant", content: "I queried `reporting.orders` and aggregated revenue by region for Q2 2024. Revenue peaked in the West region at $4.2M. Here's the breakdown:", status: "complete", createdAt: NOW - 110000, artifactIds: ["a_1", "a_4"], errorText: null },
  { id: "m_3", role: "user", content: "Now show me the monthly trend as a line chart", status: "complete", createdAt: NOW - 75000, artifactIds: [], errorText: null },
  { id: "m_4", role: "assistant", content: "Here's the monthly revenue trend across Q2. November shows the strongest month at $4.2M, with a gradual climb through the quarter.", status: "complete", createdAt: NOW - 60000, artifactIds: ["a_2"], errorText: null },
  { id: "m_5", role: "user", content: "What's driving churn this quarter?", status: "complete", createdAt: NOW - 93700000, artifactIds: [], errorText: null },
  { id: "m_6", role: "assistant", content: "I analyzed the churn cohort table. The top driver is support-ticket volume, correlated at 0.78 with churn. See the correlation heatmap below.", status: "complete", createdAt: NOW - 93600000, artifactIds: ["a_3"], errorText: null },
  { id: "m_7", role: "user", content: "Compare our spend against the targets sheet", status: "complete", createdAt: NOW - 432000000, artifactIds: [], errorText: null },
];

export const mockConversations: Conversation[] = [
  { id: "c_1", title: "Q2 Revenue Analysis", createdAt: NOW - 120000, updatedAt: NOW - 60000, messageIds: ["m_1", "m_2", "m_3", "m_4"] },
  { id: "c_2", title: "Customer Churn Drivers", createdAt: NOW - 93700000, updatedAt: NOW - 93600000, messageIds: ["m_5", "m_6"] },
  { id: "c_3", title: "Marketing Spend ROI", createdAt: NOW - 432000000, updatedAt: NOW - 432000000, messageIds: ["m_7"] },
];
