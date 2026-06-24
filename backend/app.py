"""
Flask application entry point — Natural Language to SQL Generator.

Pipeline orchestration (each step in its own module):
  1. prompt_processor  — rule-based NLP intent detection
  2. query_generator   — SQL template builders
  3. validator         — sqlparse syntax + risk checks
  4. query_explainer   — plain-English explanation
  5. impact_analyzer   — tables, columns, expected output
  6. history           — persist to JSON file

Run: cd backend && python app.py
URL: http://localhost:5000
"""

import os
import traceback

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import Config
from database import execute_query, is_db_connected, test_connection
from history import add_entry, clear_history, get_history
from impact_analyzer import analyze_impact
from prompt_processor import process_prompt
from query_explainer import generate_explanation
from query_generator import generate_all_queries
from schema_reader import get_schema_details, get_table_names, load_schema
from validator import validate_query, get_statement_type

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config.from_object(Config)
CORS(app)


def _normalize_database_type(raw: str) -> str:
    """Accept 'mysql', 'postgresql', or 'postgres' and return canonical form."""
    db_type = (raw or Config.DEFAULT_DB_TYPE).lower()
    if db_type in ("postgres", "postgresql"):
        return "postgresql"
    if db_type == "mysql":
        return "mysql"
    raise ValueError(f"Unsupported database_type: {raw}")


def _run_pipeline(prompt: str, database_type: str) -> dict:
    """
    Execute the full NL → SQL pipeline and return the API response dict.

    Steps follow the viva-friendly orchestration order:
      prompt → generate → validate → explain → impact → history
    """
    schema = load_schema(database_type)
    known_tables = get_table_names(schema)

    # Step 1: Rule-based NLP
    intent = process_prompt(prompt, known_tables, schema)

    if intent.get("invalid_prompt"):
        return {
            "user_prompt": prompt,
            "database_type": database_type,
            "query_type": "INVALID_PROMPT",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "Please enter a clear request in English.",
                "Example: Show all employees whose salary is greater than 50000.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because the prompt was empty or unclear.",
            "validation": "Please enter a clear request.",
            "optimization_suggestion": "Try a complete prompt such as: Show all employees whose salary is greater than 50000.",
            "warning": "Invalid prompt.",
        }

    if intent.get("unsafe_request"):
        return {
            "user_prompt": prompt,
            "database_type": database_type,
            "query_type": "UNSAFE_REQUEST",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request may modify or remove database objects.",
                "For safety, En2SQL did not generate this query automatically.",
                "Please use a clear and safe request.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because the request may be unsafe.",
            "validation": "Unsafe request detected.",
            "optimization_suggestion": "Use a safe read-only request or a clearly supported update/delete request.",
            "warning": "Unsafe request detected.",
        }

    if intent.get("multiple_prompts_detected"):
        return {
            "user_prompt": prompt,
            "database_type": database_type,
            "query_type": "MULTIPLE_PROMPTS_DETECTED",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "I found more than one request in your input.",
                "Please enter one SQL request at a time so the generated query is accurate.",
                "Generate the first query, then enter the next request separately.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No SQL query was generated because multiple prompts were entered together.",
            "validation": "Please enter one request at a time.",
            "optimization_suggestion": "Split your input into separate prompts and generate them one by one.",
            "warning": "Multiple prompts detected.",
        }

    if intent.get("unsupported_schema"):
        return {
            "user_prompt": prompt,
            "database_type": database_type,
            "query_type": "UNSUPPORTED_SCHEMA",
            "generated_queries": [],
            "selected_query": "",
            "explanation": [
                "This request needs tables that are not available in the current database.",
                "No SQL query was generated to avoid an incorrect result.",
                "Use the available HR tables such as employees, departments, jobs, locations, countries, regions, and dependents.",
            ],
            "affected_tables": [],
            "affected_columns": [],
            "expected_output": "No query generated because required schema is missing.",
            "validation": "Unsupported schema",
            "optimization_suggestion": "Add the required schema or use one of the available demo tables.",
            "warning": "Unsupported schema.",
        }

    # Step 2: SQL generation (user-facing queries only)
    generated_queries = generate_all_queries(intent, schema, database_type)
    selected_query = generated_queries[0]

    # Step 3: Validation (sqlparse — preserves clean academic SQL format)
    validation_result = validate_query(selected_query, schema)

    # Step 4: Explanation
    explanation = generate_explanation(intent, selected_query, database_type)

    # Step 5: Impact analysis (COUNT(*) used internally, not in generated_queries)
    impact = analyze_impact(selected_query, intent, schema, database_type)

    # Step 6: Save to history
    add_entry(
        user_prompt=prompt,
        generated_sql=selected_query,
        database_type=database_type,
        query_type=intent.get("action", "SELECT"),
        explanation=explanation,
        expected_output=impact["expected_output"],
        affected_tables=impact["affected_tables"],
        metadata={
            "affected_columns": impact["affected_columns"],
            "validation": validation_result["validation_message"],
            "warning": validation_result["warning_message"],
        },
    )

    return {
        "user_prompt": prompt,
        "database_type": database_type,
        "query_type": intent.get("action", "SELECT"),
        "generated_queries": generated_queries,
        "selected_query": selected_query,
        "explanation": explanation,
        "affected_tables": impact["affected_tables"],
        "affected_columns": impact["affected_columns"],
        "expected_output": impact["expected_output"],
        "validation": validation_result["validation_message"],
        "optimization_suggestion": validation_result["optimization_message"],
        "warning": validation_result["warning_message"],
    }


# ---------------------------------------------------------------------------
# Routes — Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    """Serve the main HTML page."""
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    """Health check with database connectivity status."""
    db_type = request.args.get("database_type", Config.DEFAULT_DB_TYPE)
    try:
        db_type = _normalize_database_type(db_type)
    except ValueError:
        db_type = Config.DEFAULT_DB_TYPE

    connection = test_connection(db_type)
    return jsonify({
        "status": "ok",
        "app": "Natural Language to SQL Generator",
        "database": connection,
    })


@app.route("/api/schema", methods=["GET"])
def schema():
    """
    Return HR schema details for:
    regions, countries, locations, jobs, departments, employees, dependents.
    """
    try:
        details = get_schema_details()
        return jsonify(details)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Core endpoint: natural language → SQL + full analysis.

    Request JSON:
        {
            "prompt": "Show all employees whose salary is greater than 50000",
            "database_type": "mysql"
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or "").strip()

        try:
            database_type = _normalize_database_type(
                data.get("database_type") or data.get("db_type")
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        response = _run_pipeline(prompt, database_type)
        return jsonify(response)

    except Exception as exc:
        if Config.DEBUG:
            traceback.print_exc()
        return jsonify({"error": f"Generation failed: {exc}"}), 500


@app.route("/api/execute", methods=["POST"])
def execute():
    """
    Execute a validated SQL query against the database (or demo mode).

    Request JSON:
        {
            "query": "SELECT ...",
            "database_type": "mysql"
        }

    Response JSON:
        {
            "status": "success" | "error",
            "columns": [],
            "rows": [],
            "message": ""
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or data.get("sql") or "").strip()

        if not query:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": "Field 'query' is required and cannot be empty.",
            }), 400

        try:
            database_type = _normalize_database_type(
                data.get("database_type") or data.get("db_type")
            )
        except ValueError as exc:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": str(exc),
            }), 400

        # Validate before execution
        validation = validate_query(query)
        if not validation["validation"]["valid"]:
            return jsonify({
                "status": "error",
                "columns": [],
                "rows": [],
                "message": validation["validation_message"],
            }), 400

        is_read = get_statement_type(query) in ("SELECT", "UNKNOWN")
        result = execute_query(database_type, query, fetch=is_read)

        if result["success"]:
            mode_note = ""
            if result.get("mode") == "demo":
                mode_note = " (demo mode — no live database connected)"
            msg = result.get("message") or (
                f"Query executed successfully{mode_note}. "
                f"{result['row_count']} row(s) affected/returned."
            )
            return jsonify({
                "status": "success",
                "columns": result["columns"],
                "rows": result["rows"],
                "message": msg,
            })

        return jsonify({
            "status": "error",
            "columns": [],
            "rows": [],
            "message": result.get("error", "Query execution failed."),
        }), 500

    except Exception as exc:
        if Config.DEBUG:
            traceback.print_exc()
        return jsonify({
            "status": "error",
            "columns": [],
            "rows": [],
            "message": f"Execution failed: {exc}",
        }), 500


@app.route("/api/history", methods=["GET"])
def history_list():
    """
    Return all previous prompts with generated SQL, explanation,
    expected output, database type, and timestamp.
    """
    try:
        limit = request.args.get("limit", 100, type=int)
        entries = get_history(limit=limit)
        return jsonify({"history": entries, "count": len(entries)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["DELETE"])
def history_clear():
    """Clear all stored history entries."""
    clear_history()
    return jsonify({"success": True, "message": "History cleared."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(os.path.dirname(Config.HISTORY_FILE), exist_ok=True)
    demo_mode = not is_db_connected("mysql") and not is_db_connected("postgresql")
    print("=" * 60)
    print("  Natural Language to SQL Generator")
    print(f"  Running at: http://localhost:5000")
    print(f"  Database mode: {'DEMO (no live DB)' if demo_mode else 'LIVE'}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
