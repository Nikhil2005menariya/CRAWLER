# Knowledge Sync Engine - SaaS Frontend Planner

The goal of this phase is to transform our Knowledge Sync Engine backend into a full-fledged SaaS platform with strict adherence to the **Saniti Design System**. It introduces local MongoDB for user management, separates roles into Client and Admin, and provides beautiful visual interfaces for the Knowledge Graph and chatbot.

## User Review Required

> [!IMPORTANT]
> Please review this planner carefully. It dictates the entire frontend scope, database integrations (MongoDB), and the specific backend APIs we will build. Once you approve, I will begin execution by building the Backend APIs first, followed by the Vite React frontend.

## Open Questions

> [!WARNING]
> 1. **MongoDB Connection**: Should we assume MongoDB is running locally on the default port (`mongodb://localhost:27017`), or do you prefer using Docker for it like Neo4j?
> 2. **CSS Approach**: Since the system guidelines restrict TailwindCSS without explicit request, I plan to use **Vanilla CSS Modules** strictly mapped to the `DESIGN.md` tokens (CSS Variables) to ensure high-fidelity compliance. Is this acceptable?

---

## 1. System Architecture Additions

### Database: MongoDB (Local)
We will introduce MongoDB to handle stateful frontend data, isolating it from our knowledge stores (Neo4j/Chroma/SQLite).
- **Users Collection**: Stores `_id`, `email`, `hashed_password`, `role` (admin/client).
- **Sessions Collection**: Stores JWT tokens or session hashes.
- **Chats Collection**: Stores `session_id`, `user_id`, `messages` (array of role/content), `created_at`.

---

## 2. Backend API Plan (`backend/api/`)

We will create new FastAPI routers to support the frontend.

### A. Authentication (`routes/auth.py`)
- `POST /api/auth/register`: Create a new user (Admin or Client).
- `POST /api/auth/login`: Return a JWT token.
- `GET /api/auth/me`: Validate JWT and return user role.

### B. Chat & Sessions (`routes/chat.py`)
- `POST /api/chat/session`: Create a new chat thread for the logged-in user.
- `GET /api/chat/sessions`: Retrieve all historical chat threads for the user.
- `GET /api/chat/session/{id}`: Load message history for a specific chat.
- `POST /api/chat/message`: Send a message to the ReAct Agent, save to MongoDB, and return the response (along with used tools).

### C. Admin Dashboard (`routes/admin.py`)
- `GET /api/admin/crawl/records`: Fetch recent crawl data from SQLite (`data/crawl.db`).
- `POST /api/admin/crawl/trigger`: Trigger the `reset_and_verify` or `ingest_router` background pipeline.

---

## 3. Frontend Planner (Vite + React)

The frontend will be a React Single Page Application (SPA) utilizing `waldenburgNormal` and `ibmPlexMono` fonts as defined in `DESIGN.md`.

### Theme & Styling Strategy (Saniti Design System)
*   **Colors**: Strict use of `{colors.canvas}` (#0b0b0b) for dark sections and `{colors.canvas-light}` (#ffffff) for light sections. Coral-red `{colors.brand}` (#f36458) reserved purely for primary CTAs and accents.
*   **Typography**: Editorial display headers with tight negative tracking. IBM Plex Mono for technical eyebrows.
*   **Depth**: No heavy drop shadows; depth is achieved via polarity flips (dark to light backgrounds) and sharp vs. rounded borders (`{rounded.marketing}` vs `{rounded.app-lg}`).

### A. Client Portal (Customer)
**Target Aesthetic**: Immersive, dark-mode, editorial chat experience.
- **Login/Register View**: Minimalist dark `{marketing-section-dark}` with `{text-input-dark}` fields and a `{button-primary}`.
- **Chat Dashboard**:
  - **Sidebar**: List of previous chat sessions (Session History).
  - **Main Window**: Chat interface styling inspired by developer documentation. Agent responses will be formatted elegantly, utilizing `{typography.body}` and mono-spaced code blocks.
  - **Interactions**: Users can create new chats, switch between historical chats, and ask questions.

### B. Admin Portal
**Target Aesthetic**: Technical trade-journal style, utilizing both dark mode and light inversion for dense data.
- **Overview Dashboard**: Dark mode metrics display (Total Products, Graph Nodes, Sync Status).
- **Crawl Management**: Light mode comparison table (`{comparison-table-row}`) to display SQLite crawl data. Includes a `{button-brand}` to "Trigger Recrawl".
- **Admin Chat Access**: Admins can also interact with the bot directly to test agent capabilities.

---

## 4. Implementation Workflow (Phase 1 to 3)

1. **Phase 1: Backend & DB**
   - Install `motor` (Async MongoDB driver) and `pyjwt` or `fastapi-users`.
   - Build MongoDB connection logic.
   - Implement Auth, Chat, and Admin FastAPI routes.
2. **Phase 2: Frontend Scaffold & Design System**
   - Initialize `npx -y create-vite@latest frontend --template react-ts`.
   - Setup vanilla `index.css` mapping every token from `DESIGN.md` into CSS Variables.
   - Create base UI components (Buttons, Inputs, Cards, Layouts) matching the design specs exactly.
3. **Phase 3: Frontend Integration**
   - Build Authentication flows.
   - Build Client Chat UI and connect to `/api/chat`.
   - Build Admin Dashboard, Graph Visualizer, and connect to `/api/admin`.
