"""
Rule-based Natural Language Processing for SQL intent detection.

Maps English prompts to structured intent using keyword rules.
Column names are normalized to academic PascalCase schema names.
"""

import re
from typing import Any, Optional

from query_generator import normalize_column


ACTION_KEYWORDS: dict[str, list[str]] = {
    "SELECT": ["show", "list", "get", "find", "display", "select", "fetch", "retrieve", "give"],
    "INSERT": ["add", "insert", "create", "register", "enroll", "new"],
    "UPDATE": ["update", "change", "modify", "set", "edit", "increase", "raise"],
    "DELETE": ["delete", "remove", "drop"],
    "TRANSACTION": ["transfer", "transaction", "move money", "send money"],
}

AGGREGATE_KEYWORDS: dict[str, list[str]] = {
    "COUNT": ["count", "number of", "how many"],
    "SUM": ["sum", "total"],
    "AVG": ["average", "avg", "mean"],
    "MAX": ["maximum", "max", "highest"],
    "MIN": ["minimum", "min", "lowest"],
}

TABLE_ALIASES: dict[str, list[str]] = {
    "employees": ["employee", "employees", "staff", "worker", "workers"],
    "departments": ["department", "departments", "dept"],
    "jobs": ["job", "jobs", "job title", "job titles"],
    "locations": ["location", "locations", "city", "cities"],
    "countries": ["country", "countries"],
    "regions": ["region", "regions"],
    "dependents": ["dependent", "dependents"],
}

UNSUPPORTED_DOMAIN_KEYWORDS: tuple[str, ...] = (
    "product",
    "products",
    "category",
    "categories",
    "order",
    "orders",
    "sales",
    "revenue",
    "customer",
    "customers",
    "invoice",
    "payment",
    "account",
    "accounts",
    "student",
    "students",
    "cgpa",
    "attendance",
)

# Natural-language token → schema column (PascalCase)
COLUMN_ALIASES: dict[str, list[str]] = {
    "salary": ["salary", "salaries", "pay", "wage", "income"],
    "first_name": ["first name", "employee name", "name"],
    "last_name": ["last name", "surname"],
    "employee_id": ["employee id", "employeeid", "id"],
    "department_id": ["department id", "dept id"],
    "department_name": ["department name", "dept name", "department"],
    "job_title": ["job title", "title"],
    "hire_date": ["hire date", "hired", "hire"],
    "city": ["city"],
}


DIRECT_SQL_RE = re.compile(
    r"^\s*(SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

DANGEROUS_SQL_RE = re.compile(
    r"\b("
    r"DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE\b|ALTER\s+TABLE|CREATE\s+USER|GRANT\b|REVOKE\b|"
    r"DELETE\s+FROM\b"
    r")",
    re.IGNORECASE,
)


def normalize_prompt(prompt: str) -> str:
    """
    Clean common natural-language input noise before intent detection.

    Direct SQL-looking input is only whitespace-normalized so SQL symbols are not damaged.
    """
    text = (prompt or "").strip()
    if DIRECT_SQL_RE.match(text):
        return re.sub(r"\s+", " ", text)

    cleaned = _normalize_numeric_separators(text)
    cleaned = re.sub(r"[@#*~`]+", " ", cleaned)
    cleaned = re.sub(r"\b(over)\b", "greater than", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\brandomly\s+selected\b", "random", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdepartment\s+wise\b", "within each department", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bper\s+department\b", "within each department", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_text(text: str) -> str:
    """Normalize prompt text for case-insensitive rule matching."""
    return normalize_prompt(text).lower()


def _normalize_numeric_separators(text: str) -> str:
    """Join accidental separators inside numeric values in natural-language prompts."""
    numeric_chunk = re.compile(r"\d(?:[\d,*]|\s+(?=\d))*")

    def clean_match(match: re.Match[str]) -> str:
        chunk = match.group(0)
        if not re.search(r"[,\*\s]", chunk):
            return chunk
        return re.sub(r"[,\*\s]+", "", chunk)

    return numeric_chunk.sub(clean_match, text)


REQUEST_START_RE = re.compile(
    r"^\s*(?:"
    r"(?:\d+[\).]\s*)?"
    r"(show|find|get|list|display|select|fetch|retrieve|give|count|how many|"
    r"what|which|increase|update|delete|add|insert|create)\b"
    r")",
    re.IGNORECASE,
)


def _looks_like_request(fragment: str) -> bool:
    """Return True when a text fragment reads like a standalone user request."""
    cleaned = fragment.strip()
    if not cleaned:
        return False
    return bool(REQUEST_START_RE.search(cleaned))


def detect_multiple_prompts(text: str) -> bool:
    """Detect when the user entered multiple independent natural-language requests."""
    raw = text.strip()
    if not raw:
        return False

    non_empty_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(non_empty_lines) >= 2 and sum(_looks_like_request(line) for line in non_empty_lines) >= 2:
        return True

    if len(re.findall(r"(?:^|\s)\d+[\).]\s+\S+", raw)) >= 2:
        return True

    semicolon_parts = [part.strip() for part in raw.split(";") if part.strip()]
    if len(semicolon_parts) >= 2 and sum(_looks_like_request(part) for part in semicolon_parts) >= 2:
        return True

    sentence_parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", raw)
        if part.strip()
    ]
    if len(sentence_parts) >= 2 and sum(_looks_like_request(part) for part in sentence_parts) >= 2:
        return True

    return False


def is_invalid_prompt(text: str) -> bool:
    """Return True for empty or symbol-only prompts."""
    cleaned = normalize_prompt(text)
    return not cleaned or not re.search(r"[A-Za-z0-9]", cleaned)


def is_unsafe_request(text: str) -> bool:
    """Return True for dangerous SQL/object-modification requests."""
    return bool(DANGEROUS_SQL_RE.search(text or ""))


def needs_unsupported_schema(text: str) -> bool:
    """Return True when the prompt asks for tables outside the demo schema."""
    normalized = normalize_text(text)
    supported_hr_terms = (
        "employee", "employees", "department", "departments", "job", "jobs",
        "location", "locations", "country", "countries", "region", "regions",
        "dependent", "dependents",
    )
    if any(re.search(rf"\b{term}\b", normalized) for term in supported_hr_terms):
        return bool(re.search(
            r"\b(?:product|products|order|orders|customer|customers|invoice|invoices|payment|payments|revenue|account|accounts)\b",
            normalized,
        ))
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", normalized)
        for keyword in UNSUPPORTED_DOMAIN_KEYWORDS
    )


def detect_action(text: str) -> str:
    """Identify SQL action from keywords."""
    normalized = normalize_text(text)

    for kw in ACTION_KEYWORDS["TRANSACTION"]:
        if kw in normalized:
            return "TRANSACTION"

    for action, keywords in ACTION_KEYWORDS.items():
        if action == "TRANSACTION":
            continue
        for kw in keywords:
            if kw in normalized:
                return action

    return "SELECT"


def detect_aggregates(text: str) -> list[str]:
    """Return aggregate functions mentioned in the prompt."""
    normalized = normalize_text(text)
    found = []

    # "top N ... highest X" is ORDER BY, not MAX(*)
    if re.search(r"(?:top|first)\s+\d+", normalized) and any(
        w in normalized for w in ("highest", "lowest", "maximum", "minimum")
    ):
        return found

    for agg, keywords in AGGREGATE_KEYWORDS.items():
        for kw in keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, normalized):
                if agg not in found:
                    found.append(agg)
    return found


def detect_tables(text: str, known_tables: Optional[list[str]] = None) -> list[str]:
    """Match table names from aliases."""
    normalized = normalize_text(text)
    matched: list[str] = []

    pool = set(known_tables or [])
    pool.update(TABLE_ALIASES.keys())

    for table in pool:
        aliases = TABLE_ALIASES.get(table, [table.lower()])
        for alias in sorted(aliases, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                canonical = _canonical_table_name(table, known_tables)
                if canonical not in matched:
                    matched.append(canonical)
                break

    return matched


def _canonical_table_name(table: str, known_tables: Optional[list[str]]) -> str:
    if not known_tables:
        return table
    for kt in known_tables:
        if kt.lower() == table.lower():
            return kt
    return table


def detect_columns(text: str, schema_columns: Optional[list[str]] = None) -> list[str]:
    """Detect column names and return PascalCase schema names."""
    normalized = normalize_text(text)
    found: list[str] = []

    search_cols = set(schema_columns or [])
    search_cols.update(COLUMN_ALIASES.keys())

    for col in search_cols:
        aliases = COLUMN_ALIASES.get(col, [col.lower()])
        for alias in sorted(aliases, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                canonical = col if col in COLUMN_ALIASES else normalize_column(col)
                if canonical not in found:
                    found.append(canonical)
                break

    return found


def extract_conditions(text: str) -> list[dict[str, str]]:
    """Extract WHERE-like conditions; column keys stay as raw tokens for normalization later."""
    conditions: list[dict[str, str]] = []
    normalized = normalize_text(text)

    operator_pattern = re.compile(
        r"\b(\w+)\s*(>=|<=|!=|=|>|<)\s*('?[a-z0-9_.@-]+'?|\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for m in operator_pattern.finditer(normalized):
        conditions.append({
            "column": m.group(1),
            "operator": m.group(2),
            "value": m.group(3).strip("'"),
        })

    whose_pattern = re.compile(
        r"whose\s+(\w+)\s+is\s+"
        r"(?:(?:greater than|more than|above)\s+(\d+(?:\.\d+)?)|"
        r"(?:less than|below|under)\s+(\d+(?:\.\d+)?)|"
        r"(?:equal to|equals)\s+([\w.]+))",
        re.IGNORECASE,
    )
    for m in whose_pattern.finditer(normalized):
        col = m.group(1)
        if m.group(2):
            conditions.append({"column": col, "operator": ">", "value": m.group(2)})
        elif m.group(3):
            conditions.append({"column": col, "operator": "<", "value": m.group(3)})
        elif m.group(4):
            conditions.append({"column": col, "operator": "=", "value": m.group(4)})

    comp_pattern = re.compile(
        r"(\w+)\s+(?:is\s+)?(?:greater than|more than|above)\s+(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for m in comp_pattern.finditer(normalized):
        col, val = m.group(1), m.group(2)
        if not any(c["column"] == col for c in conditions):
            conditions.append({"column": col, "operator": ">", "value": val})

    lt_pattern = re.compile(
        r"(\w+)\s+(?:is\s+)?(?:less than|below|under)\s+(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for m in lt_pattern.finditer(normalized):
        col, val = m.group(1), m.group(2)
        if not any(c["column"] == col for c in conditions):
            conditions.append({"column": col, "operator": "<", "value": val})

    eq_pattern = re.compile(
        r"(\w+)\s+(?:equals|equal to|is)\s+([\w@.]+)",
        re.IGNORECASE,
    )
    for m in eq_pattern.finditer(normalized):
        col, val = m.group(1), m.group(2)
        if col in ("department", "dept", "it"):
            continue
        if not any(c["column"] == col for c in conditions):
            conditions.append({"column": col, "operator": "=", "value": val})

    dept_match = re.search(
        r"\b(it|hr|finance|sales|marketing|cs|cse|computer science)\b(?:\s+department)?"
        r"|(?:in\s+)?(it|hr|finance|sales|marketing|cs|cse|computer science)\s+department"
        r"|department\s+(it|hr|finance|sales|marketing|cs|cse|computer science)\b",
        normalized,
    )
    if dept_match:
        dept_name = next(g for g in dept_match.groups() if g).upper()
        if dept_name == "COMPUTER SCIENCE":
            dept_name = "CS"
        conditions.append({"column": "department_name", "operator": "=", "value": dept_name})

    return conditions


def _wants_left_join_text(normalized: str) -> bool:
    return bool(
        re.search(r"\bleft\s+join\b", normalized)
        or re.search(r"\beven\s+if\b", normalized)
        or "display all departments" in normalized
        or ("all departments" in normalized and "no employee" in normalized)
    )


def detect_grouped_ranking(text: str) -> Optional[dict[str, Any]]:
    """Detect top-N employee salary ranking inside each department."""
    normalized = normalize_text(text)

    has_department_group = re.search(
        r"\b(?:within|in|inside|for|by)\s+each\s+departments?\b"
        r"|\bper\s+departments?\b"
        r"|\beach\s+departments?\b",
        normalized,
    )
    has_salary_rank = (
        re.search(r"\bhighest(?:\s|-)?paid\b", normalized)
        or re.search(r"\bhighest\s+salar(?:y|ies)\b", normalized)
        or ("salary" in normalized and re.search(r"\btop\b|\bhighest\b", normalized))
    )
    has_top_n = re.search(r"\b(?:top|first)\s+\d+\b", normalized)

    if not (has_department_group and (has_salary_rank or has_top_n)):
        return None

    limit_match = re.search(r"(?:top|first)\s+(\d+)", normalized)
    limit = int(limit_match.group(1)) if limit_match else 1
    ranking_type = "TOP_N_WITHIN_GROUP" if has_top_n else "HIGHEST_WITHIN_GROUP"

    return {
        "type": ranking_type,
        "entity": "employees",
        "group_table": "departments",
        "partition_by": "department_id",
        "order_by": "salary DESC",
        "rank_column": "salary_rank",
        "limit": limit,
    }


def detect_department_employee_count(text: str) -> bool:
    """Detect prompts asking for employee counts grouped by department."""
    normalized = normalize_text(text)
    return bool(
        re.search(r"\bcount\b", normalized)
        and re.search(r"\bemployees?\b", normalized)
        and re.search(
            r"\beach\s+departments?\b|\bper\s+departments?\b|\bin\s+each\s+departments?\b",
            normalized,
        )
    )


def detect_name_contains(text: str) -> Optional[dict[str, Any]]:
    """Detect case-insensitive employees.first_name substring searches."""
    normalized = normalize_text(text)
    match = re.search(
        r"\bemployees?\b.*\b(?:first\s+name|name)\s+contains\s+([a-z][\w-]*)\b"
        r"|\b(?:first\s+name|name)\s+contains\s+([a-z][\w-]*)\b.*\bemployees?\b",
        normalized,
    )
    if not match:
        return None
    term = next(group for group in match.groups() if group)
    return {"type": "NAME_CONTAINS", "column": "first_name", "value": term}


def detect_employees_hired_today(text: str) -> bool:
    """Detect prompts asking for employees hired today."""
    normalized = normalize_text(text)
    return bool(
        re.search(r"\bemployees?\b", normalized)
        and re.search(r"\bhired\s+today\b|\bhire(?:d)?\s+date\s+today\b", normalized)
    )


def detect_random_rows(text: str) -> Optional[dict[str, Any]]:
    """Detect random employees row selection such as 'Show 3 random employees'."""
    normalized = normalize_text(text)
    match = re.search(r"\b(?:show|find|get|list|display)?\s*(\d+)\s+random\s+employees?\b", normalized)
    if not match:
        match = re.search(r"\brandom\s+(\d+)\s+employees?\b", normalized)
    if not match:
        return None
    return {"type": "RANDOM_ROWS", "table": "employees", "limit": int(match.group(1))}


def detect_insert_employee_return_id(text: str) -> Optional[dict[str, Any]]:
    """Extract 'Add employee Rahul with salary 60000 ... and return id' prompts."""
    normalized = normalize_text(text)
    if not re.search(r"\b(?:add|insert|create)\s+employee\b", normalized):
        return None
    if not re.search(r"\breturn\s+(?:id|employee\s*id|employeeid)\b", normalized):
        return None

    name_match = re.search(r"\bemployee\s+([a-z][\w-]*)\b", text, re.IGNORECASE)
    salary_match = re.search(r"\bsalary\s+(\d+(?:\.\d+)?)\b", normalized)
    department_match = re.search(r"\bdepartment\s+(\d+)\b", normalized)
    designation_match = re.search(
        r"\bdesignation\s+([a-z][\w -]*?)(?:\s+and\s+return\b|\s+return\b|$)",
        text,
        re.IGNORECASE,
    )

    if not (name_match and salary_match and department_match and designation_match):
        return None

    name = name_match.group(1).strip().title()
    designation = designation_match.group(1).strip()
    designation = " ".join(designation.split()).title()

    return {
        "type": "INSERT_EMPLOYEE_RETURN_ID",
        "name": name,
        "salary": salary_match.group(1),
        "department_id": department_match.group(1),
        "designation": designation,
    }


def extract_set_values(text: str) -> list[dict[str, str]]:
    """Extract SET clause values for UPDATE statements."""
    normalized = normalize_text(text)
    sets: list[dict[str, str]] = []

    pct_val = re.search(r"by\s+(\d+)\s*(?:%|percent)", normalized)
    if pct_val:
        col = "salary"
        col_match = re.search(r"(?:increase|raise|decrease|update)\s+(\w+)", normalized)
        if col_match:
            col = col_match.group(1)
        sets.append({
            "column": col,
            "value": f"{pct_val.group(1)}%",
            "type": "percentage",
        })
        return sets

    set_match = re.search(
        r"(?:set\s+)?(\w+)\s+(?:to|=)\s+(\d+(?:\.\d+)?)",
        normalized,
    )
    if set_match:
        sets.append({"column": set_match.group(1), "value": set_match.group(2)})

    return sets


def extract_transfer_details(text: str) -> dict[str, Any]:
    """Extract transfer amount and account IDs."""
    normalized = normalize_text(text)
    details: dict[str, Any] = {}

    amount_match = re.search(
        r"(?:transfer|send|move)\s+(?:rs\.?|₹|\$)?\s*(\d+(?:\.\d+)?)", normalized
    )
    if amount_match:
        details["amount"] = amount_match.group(1)

    from_match = re.search(r"from\s+(?:account\s+)?(\d+|\w+)", normalized)
    to_match = re.search(r"to\s+(?:account\s+)?(\d+|\w+)", normalized)
    if from_match:
        details["from_account"] = from_match.group(1)
    if to_match:
        details["to_account"] = to_match.group(1)

    return details


def process_prompt(
    text: str,
    known_tables: Optional[list[str]] = None,
    schema: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convert natural language into a structured intent object."""
    cleaned_text = normalize_prompt(text)
    normalized = normalize_text(text)

    if is_invalid_prompt(text):
        return {
            "original_text": text,
            "normalized_text": normalized,
            "action": "INVALID_PROMPT",
            "query_type": "INVALID_PROMPT",
            "tables": [],
            "columns": [],
            "aggregates": [],
            "conditions": [],
            "set_values": [],
            "transfer": {},
            "order_by": None,
            "limit": None,
            "join_type": None,
            "invalid_prompt": True,
        }

    if is_unsafe_request(text):
        return {
            "original_text": text,
            "normalized_text": normalized,
            "action": "UNSAFE_REQUEST",
            "query_type": "UNSAFE_REQUEST",
            "tables": [],
            "columns": [],
            "aggregates": [],
            "conditions": [],
            "set_values": [],
            "transfer": {},
            "order_by": None,
            "limit": None,
            "join_type": None,
            "unsafe_request": True,
        }

    if detect_multiple_prompts(text):
        return {
            "original_text": text,
            "normalized_text": normalized,
            "action": "MULTIPLE_PROMPTS_DETECTED",
            "query_type": "MULTIPLE_PROMPTS_DETECTED",
            "tables": [],
            "columns": [],
            "aggregates": [],
            "conditions": [],
            "set_values": [],
            "transfer": {},
            "order_by": None,
            "limit": None,
            "join_type": None,
            "multiple_prompts_detected": True,
        }

    if needs_unsupported_schema(cleaned_text):
        return {
            "original_text": text,
            "normalized_text": normalized,
            "action": "UNSUPPORTED_SCHEMA",
            "query_type": "UNSUPPORTED_SCHEMA",
            "tables": [],
            "columns": [],
            "aggregates": [],
            "conditions": [],
            "set_values": [],
            "transfer": {},
            "order_by": None,
            "limit": None,
            "join_type": None,
            "unsupported_schema": True,
        }

    all_columns: list[str] = []
    if schema:
        for info in schema.get("tables", {}).values():
            all_columns.extend(info.get("columns", []))

    tables = detect_tables(cleaned_text, known_tables)
    columns = detect_columns(cleaned_text, all_columns)
    conditions = extract_conditions(cleaned_text)
    action = detect_action(cleaned_text)

    intent: dict[str, Any] = {
        "original_text": text,
        "normalized_text": normalized,
        "action": action,
        "query_type": action,
        "tables": tables,
        "columns": columns,
        "aggregates": detect_aggregates(text),
        "conditions": conditions,
        "set_values": extract_set_values(cleaned_text) if action == "UPDATE" else [],
        "transfer": extract_transfer_details(cleaned_text) if action == "TRANSACTION" else {},
        "order_by": None,
        "limit": None,
        "join_type": None,
        "grouped_ranking": None,
        "dialect_feature": None,
        "multi_query_type": None,
    }

    grouped_ranking = detect_grouped_ranking(cleaned_text)
    if grouped_ranking:
        intent["grouped_ranking"] = grouped_ranking
        intent["tables"] = ["employees", "departments"]
        intent["columns"] = ["employee_id", "first_name", "last_name", "salary", "department_id", "department_name"]
        intent["aggregates"] = []
        intent["conditions"] = []
        intent["order_by"] = grouped_ranking["order_by"]
        intent["limit"] = grouped_ranking["limit"]
        return intent

    if detect_department_employee_count(cleaned_text):
        intent["multi_query_type"] = "COUNT_EMPLOYEES_BY_DEPARTMENT"
        intent["tables"] = ["departments", "employees"]
        intent["columns"] = ["department_name", "department_id", "employee_id"]
        intent["aggregates"] = ["COUNT"]
        return intent

    name_contains = detect_name_contains(cleaned_text)
    if name_contains:
        intent["dialect_feature"] = name_contains
        intent["tables"] = ["employees"]
        intent["columns"] = ["first_name"]
        intent["conditions"] = [{
            "column": "first_name",
            "operator": "contains",
            "value": name_contains["value"],
        }]
        return intent

    if detect_employees_hired_today(cleaned_text):
        intent["dialect_feature"] = {"type": "EMPLOYEES_HIRED_TODAY"}
        intent["tables"] = ["employees"]
        intent["columns"] = ["hire_date"]
        return intent

    random_rows = detect_random_rows(cleaned_text)
    if random_rows:
        intent["dialect_feature"] = random_rows
        intent["tables"] = ["employees"]
        intent["columns"] = []
        intent["limit"] = random_rows["limit"]
        return intent

    if _wants_left_join_text(normalized):
        intent["join_type"] = "LEFT"

    if re.search(r"\bhighest(?:\s|-)?paid\b", normalized) or re.search(r"\bhighest\s+salar(?:y|ies)\b", normalized):
        intent["order_by"] = "salary desc"
    else:
        order_match = re.search(
            r"(?:order(?:ed)?|sort(?:ed)?)\s+(?:by\s+)?(\w+)(?:\s+(asc|desc))?",
            normalized,
        )
        if order_match:
            intent["order_by"] = f"{normalize_column(order_match.group(1))} {order_match.group(2) or 'asc'}"

    limit_match = re.search(r"(?:top|first|limit)\s+(\d+)", normalized)
    if limit_match:
        intent["limit"] = int(limit_match.group(1))

    return intent
