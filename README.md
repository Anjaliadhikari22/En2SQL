# En2SQL — Local-first Text-to-SQL Query Generator

En2SQL converts simple English prompts into SQL queries with explanation, validation, impact analysis, and MySQL/PostgreSQL dialect support.

The app now uses a single professional login page with email OTP verification, admin password protection, JWT authentication, and role-based access.

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
cp .env.example .env
cd backend
python app.py
```

### Frontend

Open with Live Server:

```text
frontend/index.html
```

Flow:

1. Open `frontend/index.html`.
2. Click `Get Started`.
3. Sign in at `frontend/login.html`.
4. Use `frontend/app.html` according to your role.

## Authentication flow

There is one login page: `frontend/login.html`.

1. Enter email.
2. Select role: `User` or `Admin`.
3. Click `Send OTP`.
4. Enter OTP.
5. User role logs in immediately after OTP verification.
6. Admin role must verify OTP, then create or enter the admin password.
7. On success, the frontend stores token, role, and email in `localStorage` and opens `app.html`.

For local development, OTPs are stored in memory. Production should use Redis or a database-backed OTP store.

## Admin email rule

Only this email can authenticate as admin:

```text
anjaliadhikari7890@gmail.com
```

If any other email selects the admin role:

- login is blocked;
- a friendly error is returned;
- an alert email is sent to the admin email when SMTP is configured;
- if SMTP is not configured, the alert body is logged for backend debugging.

All other valid emails can sign in as user.

## OTP setup

`.env.example` includes:

```text
ADMIN_EMAIL=anjaliadhikari7890@gmail.com
OTP_EXPIRY_MINUTES=5
```

If SMTP is not configured or email delivery fails, En2SQL does not crash. It returns a clear error instead of relying on a terminal OTP:

```json
{
  "success": false,
  "message": "Email OTP service is not configured properly. Please check SMTP settings."
}
```

## SMTP setup

Configure SMTP in `.env`:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM=your_email@gmail.com
```

For Gmail, use an app password rather than your normal account password.

OTP email subject:

```text
Your En2SQL Login OTP
```

## Role-based access

| Feature | Admin | User |
|---|---:|---:|
| Generate SQL | Yes | Yes |
| Multiple query options | Yes | Yes |
| MySQL/PostgreSQL dialect selection | Yes | Yes |
| Query explanation | Yes | Yes |
| Query validation | Yes | Yes |
| Optimization suggestions | Yes | Yes |
| Generic expected impact | Yes | Yes |
| Detailed impact / exact row counts | Yes | No |
| Affected tables | Yes | No |
| Affected columns | Yes | No |
| Load schema | Yes | No |
| Load history | Yes | No |
| Execute query | Yes | No |
| Execution results | Yes | No |

User mode note:

```text
User mode allows SQL generation and explanation only. Schema, history, and execution are restricted.
```

Admin-only backend APIs are protected with role checks. A user manually calling `/api/schema`, `/api/history`, or `/api/execute` receives `403 Access denied`.

Schema privacy note:

```text
User role never receives raw schema, table, column, required-table, or exact row-count metadata. Unsupported requests are shown as friendly guidance. Admin role can view schema details, affected tables, affected columns, history, and execution results.
```

## API endpoints

Authentication:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/send-otp` | Send OTP to email |
| POST | `/api/auth/verify-otp` | Verify OTP |
| POST | `/api/auth/admin-password-login` | Complete admin login after OTP |

Application:

| Method | Endpoint | Roles |
|---|---|---|
| POST | `/api/generate` | admin, user |
| POST | `/api/execute` | admin |
| GET | `/api/schema` | admin |
| GET | `/api/history` | admin |
| DELETE | `/api/history` | admin |

## Security features added

- Passwords are hashed with Werkzeug.
- JWT secret comes from environment variables.
- `.env` is ignored by Git.
- OTPs expire after a configurable time.
- Unauthorized admin attempts trigger an alert.
- Basic rate limiting:
  - send OTP: 5 per minute
  - verify OTP: 10 per minute
  - login: 5 per minute
  - generate SQL: 20 per minute
  - admin APIs: 10 per minute
- Unsafe SQL/object-modification requests are blocked.
- Users cannot access admin-only APIs even manually.

## Local-first privacy

En2SQL is local-first. By default, prompts and database data are not sent to external AI services.

Default:

```text
LLM_PROVIDER=rule_based
```

This uses the local rule-based backend only.

## Why En2SQL uses local schema packs instead of external APIs

En2SQL is local-first. It does not rely on external APIs for schema discovery or query generation. Common database domains are provided as local schema packs, making the project reliable, private, and suitable for offline/local demos.

## Supported schema packs

- HR
- E-Commerce
- University
- Healthcare
- Library
- Banking
- Hotel/Booking

En2SQL automatically detects the relevant schema/domain from the user’s prompt. Users do not need to select a schema manually. If the connected database does not contain the required tables, En2SQL safely refuses to generate fake SQL and suggests contacting the admin.

Schema pack SQL files are stored in:

```text
dataset/schema_packs/
```

## Adding a new schema pack

1. Create SQL schema file.
2. Add sample data.
3. Register schema metadata in `backend/schema_reader.py`.
4. Add domain keywords in `backend/prompt_processor.py` or the schema-pack registry.
5. Add SQL templates in `backend/query_generator.py`.
6. Add accuracy rules in `backend/query_accuracy_guard.py`.
7. Add tests.

## SQL Operation Safety Policy

- Users can generate read-only SELECT queries only.
- Admins can execute SELECT queries.
- Admins can perform INSERT, UPDATE, and DELETE only after confirmation.
- UPDATE and DELETE must include a WHERE condition.
- DROP, ALTER, TRUNCATE, GRANT, REVOKE, and CREATE USER are blocked for everyone.
- CREATE TABLE is not allowed from the normal workspace. New schemas should be added through approved schema pack SQL files.
- Schema/domain detection happens internally. Users do not manually select schemas.

## Llama / local LLM optional support

Optional local Llama support can be configured later with:

```text
LLM_PROVIDER=local_llama
LOCAL_LLM_URL=http://localhost:11434
LOCAL_LLM_MODEL=llama3
```

Any local LLM integration should receive only minimal metadata. It must never receive actual database rows, passwords, tokens, environment variables, or execution results.

## Existing SQL features preserved

- SQL generation
- Multiple query options
- MySQL/PostgreSQL syntax differences
- Query explanation bullet points
- Validation status
- Expected impact
- Unsupported schema warning
- Unsafe request warning
- Admin schema drawer
- Admin history drawer
- Admin execution and results

## Git hygiene

`.gitignore` excludes:

- `.env`
- `.venv/`
- `__pycache__/`
- `*.pyc`
- `backend/data/`

## License

Academic project — free to use for educational purposes.
