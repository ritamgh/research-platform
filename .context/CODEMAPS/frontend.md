<!-- Generated: 2026-04-18 | Files scanned: 70 | Token estimate: ~320 -->

# Frontend (week4-adk branch only)

React 18 + TypeScript + Vite, served at :5173. Proxies `/api/*` → `http://localhost:8000`.

## Page Tree

```
App
├── Tab: RESEARCH
│   ├── SearchBar          — textarea, Shift+Enter newline, Enter submit
│   └── ResultPanel
│       ├── LoadingState   — skeleton while fetching
│       ├── RouteIndicator — shows "ADK COORDINATOR" badge
│       ├── AnswerCard     — final_answer markdown
│       ├── ContextChunks  — collapsible retrieved_context chunks
│       └── SourcesList    — numbered list; URLs → <a>, non-URLs → <span>
└── Tab: CORPUS
    └── CorpusPage
        ├── Ingest form: Title + URL inputs + file upload + textarea
        │   └── PDF upload → POST /api/corpus/upload → extracted text fills textarea
        │   └── .txt/.md → FileReader.readAsText() fills textarea
        └── Documents table: title | url | chunk_count
```

## API Layer

```
src/api/research.ts
  research(query) → POST /api/research → ResearchResponse{answer, sources, route, retrieved_context}

src/api/corpus.ts
  listDocuments()  → GET  /api/corpus
  ingestDocument() → POST /api/corpus   {title, content, url, collection}
  (upload)         → POST /api/corpus/upload  FormData{file}  (inline in CorpusPage)
```

## Key Files

- `frontend/src/App.tsx` — tab routing, query state, submit handler (83 lines)
- `frontend/src/components/CorpusPage.tsx` — ingest form, PDF extraction, doc table (179 lines)
- `frontend/src/components/SourcesList.tsx` — URL vs plain-text source rendering (30 lines)
- `frontend/vite.config.ts` — proxy `/api` → `:8000`, path alias `@/`
