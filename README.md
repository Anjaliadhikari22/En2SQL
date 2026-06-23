# Natural Language to SQL Generator

An academic full-stack project that converts plain English sentences into SQL queries for **MySQL** and **PostgreSQL**. The system uses **rule-based NLP** and **SQL templates** — no external paid APIs — so every step is explainable during viva presentations.

---

## Features

| # | Feature | Module |
|---|---------|--------|
| 1 | Generated SQL query | `query_generator.py` |
| 2 | Human-readable explanation | `query_explainer.py` |
| 3 | Affected tables | `impact_analyzer.py` |
| 4 | Affected columns | `impact_analyzer.py` |
| 5 | Expected output / impact | `impact_analyzer.py` |
| 6 | SQL validation (sqlparse) | `validator.py` |
| 7 | Optimization suggestions | `validator.py` |
| 8 | Risk warnings | `validator.py` |
| 9 | Optional query execution | `database.py` + `/api/execute` |
| 10 | Query history | `history.py` |

---

## Project Structure

```
sql-generator/
├── backend/
│   ├── app.py               # Flask routes — orchestrates the pipeline
│   ├── config.py            # Environment & database configuration
│   ├── database.py          # SQLAlchemy connections (MySQL / PostgreSQL)
│   ├── schema_reader.py     # Reads table/column metadata
│   ├── prompt_processor.py  # Rule-based NLP intent detection
│   ├── query_generator.py   # SQL template builders
│   ├── query_explainer.py   # Plain-English explanations
│   ├── impact_analyzer.py   # Tables, columns, and impact analysis
│   ├── validator.py         # sqlparse validation & risk detection
│   ├── history.py           # JSON-based query history
│   └── requirements.txt
├── frontend/
│   ├── index.html           # UI layout
│   ├── style.css            # Styling
│   └── script.js            # API calls & result rendering
├── sample_database/
│   ├── mysql_schema.sql     # MySQL CREATE TABLE scripts
│   ├── postgresql_schema.sql
│   └── sample_data.sql      # Demo seed data
├── tests/
│   ├── conftest.py          # Pytest path setup
│   └── test_query_generation.py
└── README.md
```

---

## Architecture

```
User Input (English)
       │
       ▼
 prompt_processor.py   ← keyword matching, intent detection
       │
       ▼
 query_generator.py    ← SQL templates (MySQL / PostgreSQL)
       │
       ├──► query_explainer.py    → explanation
       ├──► impact_analyzer.py   → tables, columns, impact
       ├──► validator.py         → syntax, risks, optimizations
       └──► history.py            → save to JSON
       │
       ▼
  Flask API Response  →  frontend/script.js  →  UI
```

---

## Prerequisites

- Python 3.10+
- MySQL 8+ **or** PostgreSQL 14+ (optional for offline demo)
- pip

---

## Setup

### 1. Clone / open the project

```bash
cd sql-generator
```

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure database (optional)

Set environment variables or edit defaults in `backend/config.py`:

```bash
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=yourpassword
export MYSQL_DATABASE=university_db
```

For PostgreSQL:

```bash
export POSTGRES_HOST=localhost
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=yourpassword
export POSTGRES_DATABASE=university_db
```

### 4. Load sample schema and data

**MySQL:**

```bash
mysql -u root -p < ../sample_database/mysql_schema.sql
mysql -u root -p university_db < ../sample_database/sample_data.sql
```

**PostgreSQL:**

```bash
psql -U postgres -d university_db -f ../sample_database/postgresql_schema.sql
psql -U postgres -d university_db -f ../sample_database/sample_data.sql
```

### 5. Run the application

```bash
cd backend
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Example Prompts

| Natural Language | Expected Action |
|-----------------|-----------------|
| Show all students | SELECT from students |
| List students where age greater than 20 | SELECT with WHERE |
| Count number of courses | SELECT with COUNT |
| Show top 5 students order by name | SELECT with ORDER BY + LIMIT |
| Delete students where age equals 18 | DELETE with WHERE (risky) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Frontend UI |
| GET | `/api/health` | Health check + DB connectivity |
| GET | `/api/schema?db_type=mysql` | Available tables |
| POST | `/api/generate` | Generate SQL from natural language |
| POST | `/api/execute` | Execute a validated query |
| GET | `/api/history` | Query history |
| DELETE | `/api/history` | Clear history |

### Generate request example

```json
POST /api/generate
{
  "prompt": "show all students where age greater than 20",
  "db_type": "mysql"
}
```

---

## Viva Talking Points

1. **Why rule-based NLP?** — Transparent keyword matching; every decision traceable in `prompt_processor.py`.
2. **Why sqlparse?** — Industry-standard SQL tokenizer; validates structure without executing.
3. **Why SQLAlchemy?** — Single ORM layer supports both MySQL and PostgreSQL with dialect-specific URIs.
4. **Safety** — Destructive queries require explicit confirmation; risk detection in `validator.py`.
5. **Modularity** — Each concern in its own file; Flask `app.py` only orchestrates.

---

## Running Tests

Automated tests verify SQL generation for MySQL and PostgreSQL using pytest.

```bash
cd backend
pip install -r requirements.txt
python -m pytest ../tests
```

Tests cover SELECT, COUNT, UPDATE, DELETE, INNER JOIN, LEFT JOIN, and TRANSACTION prompts across both database types.

---

## Current Status

Core pipeline is implemented with automated test coverage. Remaining enhancements:

- [ ] Full schema file parsing in `schema_reader.py`
- [ ] Index-aware optimization suggestions

---

## License

Academic project — free to use for educational purposes.
