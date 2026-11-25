# ResQGrid: Intelligent Emergency Response & Humanitarian Coordination Network

> **Tagline:** Connecting Help. Saving Lives.
> **Track:** World Problem Solver
> **Advanced Challenges:**
> - **Declared advanced challenge A02:** Intelligent Decisions & Optimization (explainable emergency priority and responder matching)
> - **Declared advanced challenge A07:** Automated Multi-Step Workflow (transactional incident lifecycle and failover reassignment)

---

> [!IMPORTANT]
> **SAFETY NOTICE & EMERGENCY DISCLAIMER:**
> ResQGrid is an intelligent emergency response and humanitarian coordination prototype designed for crisis triage and volunteer/shelter logistics. **It is NOT a replacement for official emergency services (such as Bangladesh 999 or international hotlines).** It does not directly connect to 999 emergency dispatch operators. In active life-threatening emergencies, citizens must always contact official state emergency hotlines. All demo responders and rescue units are clearly labeled as simulated.

---

## 1. Executive Summary & Problem Solved

During large-scale climate and civil emergencies in Bangladesh (such as monsoon flooding in Sylhet, coastal cyclones in Chattogram/Barishal, and urban structural fires or collapses in Dhaka), emergency call centers become overwhelmed. Key failures occur:
1. **Critical cases get buried** in simple FIFO queues, causing delayed dispatch for trapped victims and infants.
2. **Responders are misassigned** to emergencies where they lack mandatory equipment (e.g. sending a first-aid volunteer without a rescue boat into deep water).
3. **Manual reassignment creates orphan incidents** when a responder declines or is busy, leaving distressed families stranded without notification.
4. **Shelters become overcrowded or uncoordinated**, exceeding safe structural occupancy while neighboring shelters sit half-empty.

**ResQGrid** solves these crises through a robust, transparent, rule-based coordination network that deterministically scores emergency priority, strictly verifies responder equipment and capability filters, orchestrates automated failover reassignment, and guarantees atomic shelter capacity management.

---

## 2. Technology Stack

- **Backend:** Python 3.14 + Django 5.2
- **Database:** SQLite by default for local development; production can use a persistent database through `DATABASE_URL`
- **Frontend:** Responsive HTML5, Bootstrap 5.3, FontAwesome 6, Chart.js
- **Geospatial & Mapping:** Leaflet 1.9 + OpenStreetMap (actual saved coordinates for incidents and shelters)
- **Static Assets & Deployment:** WhiteNoise + Gunicorn (Render-ready deployment configuration)
- **Automated Testing:** Django TestCase framework with comprehensive coverage of all scenarios

---

## 3. Core Modules & Engineering Architecture

### Module A: Emergency SOS & Incident Management
- Citizens can report an emergency for themselves (`SELF`) or on behalf of others (`OTHER`).
- Collects emergency type, description, casualty counts (affected, injured, trapped), vulnerability indicators (infants, elderly, disabled), physical access difficulty, and coordinates.
- Supports both **manual coordinates / interactive Leaflet pin-dropping** and **browser GPS auto-detection** (`navigator.geolocation`).
- Generates unique incident IDs (e.g., `RSQ-20261122-8A2F`).
- Prevents accidental duplicate submissions within short intervals.

### Module B: Intelligent Priority Engine (Challenge A02)
- Rule-based, transparent, and audit-ready triage scoring engine:
  - **Immediate threat to life:** +35 pts
  - **Physically trapped casualties:** +20 pts base (+5 pts per additional, max +35 pts)
  - **Injured casualties:** +15 pts base (+3 pts per additional, max +25 pts)
  - **Population displacement scale:** +2 to +20 pts based on affected count
  - **High-vulnerability presence:** +15 pts (children, elderly, mobility limitations)
  - **Access terrain difficulty:** +5 to +15 pts (blocked roads, deep water)
  - **Dynamic delay penalty:** +2 pts per 15 minutes of unassigned waiting
- Tiers: `CRITICAL` (score >= 80), `HIGH` (score >= 55), `MEDIUM` (score >= 30), `LOW` (score < 30).
- Generates an itemized, human-readable breakdown explaining every point contribution.

### Module C: Responder Management & Intelligent Matching Engine
- Maintains responder profiles containing verified skills, ready equipment, availability, service radius, and active concurrent capacity.
- **Mandatory Capability Filters:**
  - Mandatory skill verification (e.g. `WATER_RESCUE`, `SEARCH_RESCUE`).
  - Mandatory equipment presence (e.g. `RESCUE_BOAT`, `HYDRAULIC_CUTTER`, `AMBULANCE`).
  - Administrative verification status must be `VERIFIED`.
  - Availability status must be `AVAILABLE`.
  - Current active missions must be less than `max_active_capacity`.
  - Pending assignments reserve responder capacity, and incidents outside the service radius are excluded.
- **Intelligent Candidate Ranking:**
  - Proximity calculation via Haversine spherical distance formula.
  - Workload headroom scoring.
  - Skill/equipment breadth score.
- **Explainability:** Generates a detailed match rationale for dispatchers and responders. If no candidate qualifies, safely falls back to `UNASSIGNED` with diagnostic reasons.

### Module D: Automated Emergency Workflow (Challenge A07)
- Multi-step state machine:
  `REPORTED` &rarr; `TRIAGED` &rarr; `ASSIGNED` &rarr; `ACCEPTED` &rarr; `RESPONDING` &rarr; `RESOLVED` (plus `UNASSIGNED` and `CANCELLED`).
- **Automated Failover Reassignment:** If a responder declines or is unavailable, the workflow engine automatically searches and dispatches the next highest-ranked eligible responder.
- **Safe Fallback:** If all eligible candidates are exhausted, the incident moves to `UNASSIGNED` and logs an emergency alert in the audit trail.
- **Audit Event Log:** Complete chronological log (`IncidentEvent`) recording timestamps, actors, status changes, and rationale.
- **Integrity Guards:** Prevents duplicate assignments and illegal status jumps.

### Module E: Shelter & Resource Management
- Directory of emergency shelters across Bangladesh (Dhaka, Sylhet, Chattogram, Khulna).
- Monitors total, occupied, and remaining available capacity, plus essential relief supplies (food, potable water, medical support).
- **Atomic Capacity Guarantee:** Uses `select_for_update()` database transactions to prevent over-allocation beyond shelter capacity.

---

## 4. User Roles & Access Control

| Role | Permissions & Dashboards |
| :--- | :--- |
| **Administrator** | Full mission control, view all incidents, filter & sort, manual dispatch override, verify responder profiles, allocate shelters, view live priority/status analytics charts. |
| **Emergency Responder** | Dedicated mission terminal, toggle duty availability (`AVAILABLE`/`BUSY`/`OFFLINE`), review pending assignments, accept/decline missions, update deployment progress to `RESPONDING`, resolve incidents with completion notes. |
| **Citizen** | Prominent "Report Emergency SOS" button, geolocation detection, personal incident tracking with live step progress bar, nearby safe evacuation shelters finder. |

---

## 5. Quick Start Instructions (Local Windows Setup)

The application runs locally on Windows using simple commands and standard Python:

### Step 1: Open Terminal in Project Directory
```powershell
cd "C:\Users\LAPTOP GADGET\.gemini\antigravity\scratch\resqgrid"
```

### Step 2: Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### Step 3: Run Database Migrations
```powershell
python manage.py migrate
```

### Step 4: (Optional) Seed Local Demo Data & Scenarios
```powershell
$env:RESQGRID_DEMO_PASSWORD = Read-Host "Enter a temporary demo password (12+ characters)"
python manage.py seed_demo_data
```

The seeder refuses to run without an environment-provided password. Use fictional demonstration data only; never run it against an operational database. Production seeding additionally requires explicit isolation and confirmation flags. Deployment builds do not seed demo users or reset shelter occupancy.

### Step 5: Start the Local Development Server
```powershell
python manage.py runserver 127.0.0.1:8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your web browser.

---

## 6. Local Demo Accounts

After running the local seed command, the seeded demo accounts use the password entered in `RESQGRID_DEMO_PASSWORD`. In development, one-click demo login appears only when that variable is set. Demo login shortcuts are never rendered when `DEBUG=False`. Provide judge credentials privately, not in this public README.

| Role | Username | Purpose & Capabilities |
| :--- | :--- | :--- |
| **Administrator** | `admin` | Dispatch console, responder verification, shelter/resource management, and analytics. |
| **Resource Manager** | `resource_manager` | Shelter allocation and relief inventory management. |
| **Water Rescue Responder** | `responder_boat` | Verified responder with water-rescue skills and rescue equipment. |
| **Trauma Medic Responder** | `responder_medical` | Verified responder with medical skills and ambulance. |
| **USAR Responder** | `responder_usar` | Search-and-rescue responder with specialist equipment. |
| **Volunteer (No Gear)** | `responder_no_gear` | Demonstrates capability filtering for missing equipment. |
| **Citizen Reporter** | `citizen_karim` / `citizen_fatima` | Submit and track personal emergency reports. |

> **Judge access:** Configure isolated demo data and share the environment-specific password through the competition's private test-access field.

---

## 7. Deployment Configuration

- For Render, set `RESQGRID_ENV=production`, `DEBUG=False`, a generated `SECRET_KEY`, and `DATABASE_URL` pointing to a persistent PostgreSQL service. Production settings fail closed if the secret or PostgreSQL URL is missing, or if the URL selects a non-PostgreSQL database.
- Local development uses SQLite when `DATABASE_URL` is unset. Do not rely on SQLite or an ephemeral filesystem for deployed incident, responder, or shelter data.
- Configure `ALLOWED_HOSTS` for custom domains. Render's `RENDER_EXTERNAL_HOSTNAME` is added automatically and also enables Django's forwarded-HTTPS proxy setting. Add any custom HTTPS origins to `CSRF_TRUSTED_ORIGINS`.
- The Render blueprint enforces HTTPS redirects and sets a short initial HSTS policy. Confirm the provider's TLS/proxy behavior before increasing HSTS duration; enable subdomain or preload policies only after confirming every covered domain supports HTTPS.
- Database initialization and deployment commands:
  ```powershell
  python manage.py migrate
  python manage.py collectstatic --noinput
  python manage.py check --deploy
  ```
  Render runs migrations and collects static assets during its build. Its `/health/` check reports ready only when the configured database accepts a query. Confirm PostgreSQL persistence across a real service restart before treating deployment data as durable.
- Assign the `RESOURCE_MANAGER` role to authorized staff through Django Admin (`UserProfile.role`). Public registration does not grant this privileged role.
- Set `CARTO_API_KEY` to a CARTO-issued basemaps key to use CARTO Voyager by default and enable Positron and Dark Matter. CARTO now requires an issued key; without one, unauthenticated tiles show an API-key watermark. Keep the key in the deployment environment, never in source control, and restrict it to the application origin in CARTO's dashboard. Use a separate key for local development and production when host restrictions are enabled. Browser tile keys are visible to clients, so do not treat them as server-side secrets.
- When no CARTO key is configured, the maps use `https://tile.openstreetmap.org/{z}/{x}/{y}.png` as a fallback. Keep its OpenStreetMap attribution visible, allow the browser's normal `Referer` header, honor caching headers, and request only tiles the user is viewing. OSM tile service availability is best-effort; do not bulk-download tiles.
- CARTO usage limits and pricing depend on whether the deployment is commercial or non-commercial; select a plan permitted for the application's use.
- The deployment build does not seed demo accounts or reset shelter occupancy.

## 8. Verified Demonstration Scenarios

### Scenario 1: Critical Emergency Receives Higher Priority Than Normal Emergency
- **Action:** Compare incident `RSQ-DEMO-CRITICAL` (18 affected, 5 injured, 4 trapped, life-threat active) against `RSQ-DEMO-LOW` (2 affected, ankle-deep water, 0 injured).
- **Result:** Priority Engine calculates **CRITICAL** (score ~90+) for the building collapse versus **LOW** (score ~15) for the minor waterlogging, placing the critical incident at the top of the dispatch queue.

### Scenario 2: Responder Without Required Equipment Is Rejected by Matching Engine
- **Action:** A flood emergency requires mandatory equipment `RESCUE_BOAT`. `responder_no_gear` has the `WATER_RESCUE` skill, but only possesses `FIRST_AID_KIT`.
- **Result:** Matching Engine strictly filters out `responder_no_gear` and only recommends responders who possess the required boat.

### Scenario 3: Responder Rejects Assignment & System Automatically Tries Next Eligible Responder
- **Action:** Responder declines assignment on `RSQ-DEMO-REASSIGN`.
- **Result:** The system marks the assignment `REJECTED`, searches for the next best qualified responder, automatically creates a new `PENDING` assignment for the backup responder, and logs `AUTO_REASSIGNED` in the audit history.

### Scenario 4: No Eligible Responder Exists & Incident Remains Unassigned With Explanation
- **Action:** Incident `RSQ-DEMO-UNASSIGNED` in remote delta island requires specialized equipment not available within service range.
- **Result:** Incident status is set to `UNASSIGNED`, `assigned_responder` is cleared, and `unassigned_reason` records a transparent diagnostic explanation for human dispatchers.

### Scenario 5: Shelter Cannot Accept More People Than Its Remaining Capacity
- **Action:** Sylhet Osmani Nagar Flood Shelter has total capacity 200 and currently houses 195 people (5 free spots). An operator attempts to allocate a family of 10 people.
- **Result:** Database transaction lock rejects the operation with `ValidationError: Cannot allocate 10 people. Shelter only has 5 free spots`, preventing hazardous over-occupancy.

---

## 9. Running Automated Tests

Run the core Django test suite, including workflow and security regressions:

```powershell
python manage.py test core.tests
```

### Judge walkthrough (A02 + A07)

1. Sign in as a citizen and report an emergency with casualties and location.
2. Compare the resulting score breakdown with a low-severity seeded scenario; the priority factors are visible and deterministic.
3. Sign in as the dispatched responder, decline an assignment, and verify that the next eligible responder receives it.
4. Demonstrate the infeasible-match scenario: the incident remains unassigned with a diagnostic explanation rather than selecting an unqualified responder.
5. Accept a mission and complete the responding-to-resolved lifecycle; the audit event timeline records transitions.
6. For failure recovery, run `python manage.py test core.tests.WorkflowIntegrityAndTransitionTests` and show the tests that prove failed audit writes roll back dispatch/acceptance changes atomically.

These are simulation workflows, not real emergency dispatch. The seeded people, organizations, incidents, and resources are fictional.

### Requirement map

| Competition requirement | Demonstrable implementation |
|---|---|
| M01 Functional system | Citizen, responder, administrator, shelter, and relief-resource workflows |
| M02 Database persistence/CRUD | Django relational models; incident, shelter, resource, and allocation operations |
| M03 Authentication/authorization | Django sessions, role-scoped views, login throttling, password change |
| M04 Business logic | Explainable priority scoring, capability-constrained matching, incident state machine |
| M05 Dynamic processing | Search/filter/sort, live aggregates, responder ranking, capacity calculations |
| M06 Errors/edge cases | Form validation, duplicate-report protection, capacity/range constraints, rollback tests |
| M07 Responsive/accessibility | Bootstrap responsive layouts, keyboard-friendly forms, skip link, ARIA status messages |
| M08 Deployment/docs | Render blueprint, PostgreSQL service, setup instructions; actual live URL must be supplied by the entrant |

Only **A02 and A07** are declared for the advanced 40-point section. A02 handles infeasible responder matches with an explained unassigned outcome. A07 uses atomic workflow transactions; regression tests inject audit-write failures and verify earlier state changes roll back.

---

## 10. Cloud Deployment (Render.com)
ResQGrid includes deployment configuration for Render:
1. `render.yaml` binds Gunicorn to `0.0.0.0:$PORT` and configures `/health/` as the service health check; `Procfile` contains the same bind behavior.
2. The build installs `requirements.txt`, applies migrations, and collects compressed static files without seeding demo data. WhiteNoise serves the compressed assets.
3. Configure a persistent PostgreSQL `DATABASE_URL`; production startup/settings reject a missing URL or SQLite configuration. Database SSL is required when `DEBUG=False`.
4. Configure `RESQGRID_ENV=production`, `DEBUG=False`, and a generated `SECRET_KEY`; Render's assigned hostname is added to `ALLOWED_HOSTS` and trusted HTTPS origins automatically.
5. HTTPS redirect and HSTS remain opt-in until the deployed hostname/proxy has been checked. A local configuration check does not verify a live Render deployment or PostgreSQL restart durability.

---

## 11. Known Limitations & Future Improvements

1. **SMS / Offline Fallback:** Currently operates over web protocols. Future iterations could integrate SMS gateways (e.g. Twilio / local telecom USSD) for citizens without active internet connections.
2. **Real-Time WebSockets:** Incident status updates currently refresh on navigation or AJAX polling; adding WebSockets (Django Channels) would enable instant push alerts.
3. **Multi-Agency Federation:** Expandable to allow cross-agency coordination with Bangladesh Red Crescent, Fire Service & Civil Defense (FSCD), and international NGOs.
