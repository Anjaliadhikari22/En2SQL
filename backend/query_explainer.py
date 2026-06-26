"""Simple, point-wise explanations for generated SQL queries."""

import re
from typing import Any, Union


def _bullets(*items: str) -> list[str]:
    return list(items)


def _db_name(db_type: str) -> str:
    return "PostgreSQL" if (db_type or "").lower() in ("postgres", "postgresql") else "MySQL"


def _limit_from_intent(intent: dict[str, Any], default: int = 1) -> int:
    return (
        (intent.get("grouped_ranking") or {}).get("limit")
        or intent.get("limit")
        or default
    )


def _limit_from_sql(sql: str, default: int = 1) -> int:
    match = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.IGNORECASE)
    return int(match.group(1)) if match else default


def _salary_threshold(sql: str, intent: dict[str, Any]) -> str:
    for cond in intent.get("conditions", []):
        if cond.get("column") == "salary" and cond.get("operator") == ">":
            return str(cond.get("value"))
    match = re.search(r"\bsalary\s*>\s*([0-9]+(?:\.[0-9]+)?)", sql, re.IGNORECASE)
    return match.group(1) if match else "the given amount"


def _explain_grouped_ranking(intent: dict[str, Any]) -> list[str]:
    limit = _limit_from_intent(intent)
    ranking_type = (intent.get("grouped_ranking") or {}).get("type")

    if ranking_type == "HIGHEST_WITHIN_GROUP":
        return _bullets(
            "Option 1 uses DENSE_RANK(), so employees with the same salary get the same rank.",
            "Option 1 is useful when salary ties should be shown fairly.",
            "Option 2 uses a maximum-salary subquery to find the highest-paid employees in each department.",
        )

    return _bullets(
        "Option 1 uses ROW_NUMBER() to rank employees separately inside each department.",
        f"It returns exactly the top {limit} highest-paid employees from every department.",
        "Option 2 uses DENSE_RANK(), so employees with the same salary get the same rank.",
        f"DENSE_RANK() may return more than {limit} employees if salary ties exist.",
        "Option 3 uses a correlated subquery as an alternative method.",
        "For most cases, Option 1 is the recommended query.",
    )


def _explain_dialect_feature(intent: dict[str, Any], sql: str, db_type: str) -> list[str]:
    feature = intent.get("dialect_feature") or {}
    feature_type = feature.get("type")
    database = _db_name(db_type)

    if feature_type == "NAME_CONTAINS":
        term = feature.get("value", "the requested text")
        syntax_note = (
            "PostgreSQL uses ILIKE for this case-insensitive search."
            if database == "PostgreSQL"
            else "MySQL uses LOWER() to make the search case-insensitive."
        )
        return _bullets(
            f"Shows employees whose first name contains “{term}”.",
            "Uses the employees table.",
            syntax_note,
        )

    if feature_type == "EMPLOYEES_HIRED_TODAY":
        return _bullets(
            "Shows employees hired today.",
            "Uses the employees table.",
            f"Uses {database} date syntax.",
        )

    if feature_type == "RANDOM_ROWS":
        limit = feature.get("limit") or _limit_from_sql(sql)
        return _bullets(
            f"Shows {limit} randomly selected employees.",
            "Uses the employees table.",
            "This is a read-only query, so it does not change any data.",
        )

    return []


def generate_explanation(
    intent: dict[str, Any],
    sql: str,
    db_type: str,
) -> Union[str, list[str]]:
    """Return concise bullet points focused on what the query does."""
    normalized = intent.get("normalized_text", "")
    upper = sql.upper()

    if intent.get("unsupported_schema"):
        return "This request needs tables that are not available in the current database, so no SQL query was generated."

    pack = (intent.get("schema_pack") or "").lower()
    if pack and pack != "hr":
        if pack == "ecommerce" and "SUM(" in upper and "QUANTITY *" in upper:
            return _bullets(
                "Calculates revenue using order quantity multiplied by unit price.",
                "Groups or sorts the result based on the requested business view.",
                "This is a read-only query, so it does not change any data.",
            )
        if pack == "university":
            return _bullets(
                "Uses the local University schema pack.",
                "Joins the relevant student, course, enrollment, instructor, or grade tables.",
                "This is a read-only query, so it does not change any data.",
            )
        if pack == "healthcare":
            return _bullets(
                "Uses the local Healthcare schema pack.",
                "Joins the relevant doctor, patient, appointment, prescription, or medicine tables.",
                "This is a read-only query, so it does not change any data.",
            )
        if pack == "library":
            return _bullets(
                "Uses the local Library schema pack.",
                "Joins the relevant book, author, member, or borrow record tables.",
                "This is a read-only query, so it does not change any data.",
            )
        if pack == "banking":
            return _bullets(
                "Uses the local Banking schema pack.",
                "Joins the relevant customer, account, transaction, or branch tables.",
                "This is a read-only query, so it does not change any data.",
            )
        if pack == "booking":
            return _bullets(
                "Uses the local Hotel/Booking schema pack.",
                "Joins the relevant hotel, room, guest, booking, or payment tables.",
                "This is a read-only query, so it does not change any data.",
            )

    if intent.get("grouped_ranking"):
        return _explain_grouped_ranking(intent)

    if intent.get("multi_query_type") == "COUNT_EMPLOYEES_BY_DEPARTMENT":
        return _bullets(
            "Option 1 shows department names with employee counts.",
            "Option 2 gives a simpler count grouped by department_id.",
            "Both options are read-only and do not change any data.",
        )

    dialect_text = _explain_dialect_feature(intent, sql, db_type)
    if dialect_text:
        return dialect_text

    if "FROM EMPLOYEES" in upper and re.search(r"\bSALARY\s*>\s*", upper):
        if "AVG(SALARY)" in upper:
            return _bullets(
                "Shows employees whose salary is above the average salary.",
                "Uses a subquery to calculate the average salary from the employees table.",
                "This is a read-only query, so it does not change any data.",
            )
        amount = _salary_threshold(sql, intent)
        return _bullets(
            f"Shows employees whose salary is greater than {amount}.",
            "Uses the employees table.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM EMPLOYEES" in upper and re.search(r"\bSALARY\s*<\s*\(", upper) and "AVG(SALARY)" in upper:
        return _bullets(
            "Shows employees whose salary is below the average salary.",
            "Uses a subquery to calculate the average salary from the employees table.",
            "This is a read-only query, so it does not change any data.",
        )

    if "SECOND_HIGHEST_SALARY" in upper or ("SELECT DISTINCT SALARY" in upper and "OFFSET" in upper):
        return _bullets(
            "Finds the second-highest distinct salary.",
            "Avoids hardcoding any salary value.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM EMPLOYEES" in upper and "ORDER BY SALARY DESC" in upper and "LIMIT" in upper:
        limit = _limit_from_sql(sql, _limit_from_intent(intent, 5))
        return _bullets(
            f"Shows the top {limit} highest-paid employees.",
            "Sorts employees by salary from highest to lowest.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM EMPLOYEES E" in upper and "JOIN DEPARTMENTS D" in upper:
        if "COUNT(" in upper and "GROUP BY" in upper:
            return _bullets(
                "Counts how many employees are present in each department.",
                "Shows departments with the highest employee count first.",
                "Uses a join between employees and departments.",
            )
        return _bullets(
            "Shows each employee’s first name and last name.",
            "Also displays the department name for each employee.",
            "Uses a join between employees and departments.",
        )

    if "FROM DEPARTMENTS D" in upper and "LEFT JOIN EMPLOYEES E" in upper and "IS NULL" in upper:
        return _bullets(
            "Shows departments that do not have any employees.",
            "Uses a LEFT JOIN and keeps only rows where no employee matched.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM DEPARTMENTS D" in upper and "LEFT JOIN EMPLOYEES E" in upper and "COUNT(" in upper:
        return _bullets(
            "Counts how many employees are present in each department.",
            "Shows departments with the highest employee count first.",
            "Includes departments even if they have no employees.",
        )

    if "FROM EMPLOYEES" in upper and "DEPARTMENT_ID IS NULL" in upper:
        return _bullets(
            "Shows employees who are not assigned to any department.",
            "Checks for NULL in the department_id column.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM EMPLOYEES" in upper and "GROUP BY EMAIL" in upper and "HAVING COUNT(*) > 1" in upper:
        return _bullets(
            "Finds duplicate email addresses.",
            "Groups employees by email and shows only repeated emails.",
            "This is a read-only query, so it does not change any data.",
        )

    if "FROM EMPLOYEES" in upper and "GROUP BY FIRST_NAME, LAST_NAME, EMAIL" in upper:
        return _bullets(
            "Finds possible duplicate employee records.",
            "Groups by first name, last name, and email.",
            "Shows only groups that appear more than once.",
        )


    if "FROM EMPLOYEES E" in upper and "JOIN JOBS J" in upper:
        return _bullets(
            "Shows employees along with their job titles.",
            "Also displays each employee’s salary.",
            "Uses a join between employees and jobs.",
        )

    if "FROM DEPARTMENTS D" in upper and "JOIN LOCATIONS L" in upper:
        return _bullets(
            "Shows each department with its city.",
            "Uses a join between departments and locations.",
        )

    if "FROM EMPLOYEES" in upper and "HIRE_DATE >" in upper:
        match = re.search(r"hire_date\s*>\s*'([^']+)'", sql, re.IGNORECASE)
        date_text = match.group(1) if match else "the selected date"
        return _bullets(
            f"Shows employees hired after {date_text}.",
            "Uses the employees table.",
            "This is a read-only query, so it does not change any data.",
        )

    if re.search(r"ORDER BY\s+(RAND|RANDOM)\s*\(\s*\)", upper):
        limit = _limit_from_sql(sql, _limit_from_intent(intent, 1))
        return _bullets(
            f"Shows {limit} randomly selected employees.",
            "Uses the employees table.",
            "This is a read-only query, so it does not change any data.",
        )

    if normalized:
        return "Returns the information requested in your prompt."

    return "Returns matching records from the database."
