# EDA Agent — Frontend

React 19 + Vite + TypeScript SPA for the EDA Agent. Streams responses from the backend in real time, displays generated charts and reports in a dedicated workspace panel, and persists chat history locally in IndexedDB.

Requires the [eda-agent-backend](https://github.com/your-org/eda-agent-backend) running on `localhost:8000` (or the host configured in `.env`).

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Node.js | 18 LTS (20 or 22 recommended) |
| npm | 9+ |

---

## Project layout

```
eda-agent-frontend/
├── src/
│   ├── types/index.ts          # All shared TypeScript interfaces
│   ├── api/
│   │   ├── rest.ts             # fetchHealth, fetchCharts, fetchReports
│   │   └── wsClient.ts         # ChatStreamClient — WebSocket with auto-reconnect
│   ├── store/useAppStore.ts    # Zustand global state
│   ├── hooks/
│   │   ├── useChatStream.ts    # Singleton WS client + sendMessage
│   │   ├── useArtifactPolling.ts # Polls /charts & /reports every 4s
│   │   └── useMediaQuery.ts    # useIsDesktop() breakpoint hook
│   ├── lib/
│   │   ├── cn.ts               # clsx + tailwind-merge
│   │   ├── config.ts           # API_BASE_URL, WS_BASE_URL, toAbsoluteUrl()
│   │   ├── time.ts             # relativeLabel(), dateGroupLabel()
│   │   ├── uuid.ts             # crypto.randomUUID wrapper
│   │   ├── artifactDetection.ts # Parse agent text for chart/report paths
│   │   └── persistence.ts      # idb-keyval load/save
│   ├── components/
│   │   ├── ui/                 # Primitive components (Button, Badge, Tabs …)
│   │   ├── layout/             # TopBar, ConnectionBadge, AppShell
│   │   ├── history/            # HistorySidebar and sub-components
│   │   ├── chat/               # ChatColumn, MessageList, Composer …
│   │   └── workspace/          # WorkspacePanel, artifact + report renderers
│   └── data/mockData.ts        # Seed data shown before first real chat
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── .env.example
```

---

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
```

The defaults work as-is for local development with the backend on port 8000:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

Change these only if your backend runs on a different host or port.

### 3. Start the dev server

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The Vite dev server proxies `/health`, `/charts`, `/reports`, and `/chat` to the backend, so CORS is never an issue during development.

---

## Usage

The **connection badge** in the top bar shows the WebSocket status. It turns green ("Connected") within a second or two of the backend being reachable.

**Things to try in the chat:**

```
List my BigQuery datasets
Describe the schema of reporting.orders
Show me Q2 revenue by region as a bar chart
Build an HTML report of monthly trends
```

Generated **charts** appear as clickable chips below the assistant's message — click one to open it in the **Artifacts** panel on the right. Generated **HTML reports** appear in the **Reports** tab of the same panel.

**Drag and drop** any file onto the composer to register it as a local artifact (viewable in the Artifacts panel). Note: the current backend has no upload endpoint, so files are not sent to the agent — this is the forward-compatible seam for a future `/upload` route.

The app seeds itself with sample conversations, charts, and reports on first load so every panel renders immediately. Real data accumulates as you chat. History is stored in IndexedDB and survives page refreshes.

---

## Architecture notes

**Three-zone layout**

```
┌─────────────────┬────────────────────────────────────┬───────────────────────┐
│ HISTORY SIDEBAR │ CHAT COLUMN                        │ WORKSPACE PANEL       │
│ (280px, spring  │ (flex, min 480px)                  │ (40%, slides in on    │
│  collapse)      │                                    │  artifact/report open)│
└─────────────────┴────────────────────────────────────┴───────────────────────┘
```

On mobile (< 1024px) the sidebar and workspace panel become full-screen overlays; the chat column fills the viewport.

**WebSocket protocol**

The backend sends raw text tokens via `send_text()` and JSON control frames via `send_json()` on the same socket. `ChatStreamClient` disambiguates them by attempting `JSON.parse()` on every message and falling back to treating the payload as a literal token.

**Singleton WebSocket**

`useChatStream()` is called from multiple components (`App`, `Composer`, `ChatEmptyState`) but they all share a single module-level `ChatStreamClient` instance. Only the first mount opens the connection; only the last unmount closes it. No duplicate sockets are ever opened.

**Artifact discovery**

The backend has no structured artifact event channel — it only exposes `/charts` and `/reports` file-listing endpoints. `useArtifactPolling` polls these every 4 seconds, diffs against already-registered artifacts, and registers new ones. `artifactDetection.ts` additionally parses completed assistant messages for inline file path references (e.g. `charts/bar_a3f8.png`) and registers those immediately on message completion.

**Local persistence**

Chat history, artifacts, and reports are saved to IndexedDB (`idb-keyval`) with an 800ms debounce on every state change. The store hydrates from IndexedDB on startup; the mock seed data is only used when the database is empty.

---

## Production build

```bash
npm run build
```

Outputs a static site to `dist/`. Serve it with any static host (nginx, Vercel, Cloud Run, etc.), or mount it onto the FastAPI backend:

```python
# server.py addition
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="../eda-agent-frontend/dist", html=True), name="frontend")
```

---

## Development

```bash
# Type-check only (no emit)
npx tsc --noEmit

# Build for production
npm run build

# Preview the production build locally
npm run preview
```

### Adding a new artifact kind

1. Add a new literal to `ArtifactKind` in `src/types/index.ts`.
2. Add a new interface extending `ArtifactBase` in the same file and add it to the `Artifact` union.
3. Add a renderer component in `src/components/workspace/artifacts/`.
4. Add a case for it in `ArtifactViewer.tsx`.
5. Add an icon mapping entry in `ArtifactChip.tsx` and `ArtifactCard.tsx`.
6. Optionally add a detection regex in `src/lib/artifactDetection.ts`.

---

## Troubleshooting

**Connection badge stays red / "Connection error"**
Confirm the backend is running (`curl localhost:8000/health`) and that `VITE_WS_BASE_URL` in `.env` points to the right host. Restart the dev server after changing `.env`.

**Charts or reports don't appear after the agent generates them**
The artifact poller runs every 4 seconds and only detects files that already exist on disk. If the backend `CHARTS_DIR` or `REPORTS_DIR` is misconfigured, files won't be served by `/charts` or `/reports`. Check the backend logs.

**App shows only mock data**
That's expected on first load — mock data seeds the UI when IndexedDB is empty. Start chatting and the mock conversations will be replaced by real ones. To force a clean slate, open DevTools → Application → IndexedDB → delete the `eda-agent-state-v1` key.

**Composer send button is disabled**
The button requires the WebSocket to be in "connected" state. If the badge shows anything other than green, the backend isn't reachable. Check that `VITE_WS_BASE_URL` is correct and the backend is running.
