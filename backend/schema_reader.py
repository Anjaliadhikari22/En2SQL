"""Schema introspection and local schema-pack registry for En2SQL."""

from typing import Any, Optional
import re

from sqlalchemy import inspect

from database import get_engine, is_db_connected


HR_RELATIONSHIPS: list[dict[str, str]] = [
    {"from": "countries.region_id", "to": "regions.region_id"},
    {"from": "locations.country_id", "to": "countries.country_id"},
    {"from": "departments.location_id", "to": "locations.location_id"},
    {"from": "employees.job_id", "to": "jobs.job_id"},
    {"from": "employees.department_id", "to": "departments.department_id"},
    {"from": "employees.manager_id", "to": "employees.employee_id"},
    {"from": "dependents.employee_id", "to": "employees.employee_id"},
]


HR_SCHEMA: dict[str, Any] = {
    "schema_pack": "hr",
    "display_name": "HR",
    "source": "hr",
    "relationships": HR_RELATIONSHIPS,
    "tables": {
        "regions": {
            "description": "Geographic regions",
            "columns": ["region_id", "region_name"],
            "primary_key": ["region_id"],
        },
        "countries": {
            "description": "Countries mapped to regions",
            "columns": ["country_id", "country_name", "region_id"],
            "primary_key": ["country_id"],
        },
        "locations": {
            "description": "Office locations mapped to countries",
            "columns": ["location_id", "street_address", "postal_code", "city", "state_province", "country_id"],
            "primary_key": ["location_id"],
        },
        "jobs": {
            "description": "Job titles and salary bands",
            "columns": ["job_id", "job_title", "min_salary", "max_salary"],
            "primary_key": ["job_id"],
        },
        "departments": {
            "description": "Departments mapped to locations",
            "columns": ["department_id", "department_name", "location_id"],
            "primary_key": ["department_id"],
        },
        "employees": {
            "description": "Employee records with job, manager, department, hire date, and salary",
            "columns": [
                "employee_id", "first_name", "last_name", "email", "phone_number",
                "hire_date", "job_id", "salary", "manager_id", "department_id",
            ],
            "primary_key": ["employee_id"],
        },
        "dependents": {
            "description": "Employee dependents",
            "columns": ["dependent_id", "first_name", "last_name", "relationship", "employee_id"],
            "primary_key": ["dependent_id"],
        },
    },
}


ECOMMERCE_SCHEMA: dict[str, Any] = {
    "schema_pack": "ecommerce",
    "display_name": "E-Commerce",
    "source": "schema_pack",
    "relationships": [
        {"from": "products.category_id", "to": "categories.category_id"},
        {"from": "orders.customer_id", "to": "customers.customer_id"},
        {"from": "order_items.order_id", "to": "orders.order_id"},
        {"from": "order_items.product_id", "to": "products.product_id"},
        {"from": "payments.order_id", "to": "orders.order_id"},
    ],
    "tables": {
        "categories": {"description": "Product categories", "columns": ["category_id", "category_name"], "primary_key": ["category_id"]},
        "products": {"description": "Products available for sale", "columns": ["product_id", "product_name", "category_id", "price", "stock_quantity"], "primary_key": ["product_id"]},
        "customers": {"description": "Customer records", "columns": ["customer_id", "first_name", "last_name", "email", "created_at"], "primary_key": ["customer_id"]},
        "orders": {"description": "Customer orders", "columns": ["order_id", "customer_id", "order_date", "status"], "primary_key": ["order_id"]},
        "order_items": {"description": "Line items in each order", "columns": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"], "primary_key": ["order_item_id"]},
        "payments": {"description": "Order payments", "columns": ["payment_id", "order_id", "payment_date", "amount", "payment_method"], "primary_key": ["payment_id"]},
    },
}


UNIVERSITY_SCHEMA: dict[str, Any] = {
    "schema_pack": "university",
    "display_name": "University",
    "source": "schema_pack",
    "relationships": [
        {"from": "students.department_id", "to": "departments.department_id"},
        {"from": "courses.department_id", "to": "departments.department_id"},
        {"from": "courses.instructor_id", "to": "instructors.instructor_id"},
        {"from": "enrollments.student_id", "to": "students.student_id"},
        {"from": "enrollments.course_id", "to": "courses.course_id"},
        {"from": "grades.enrollment_id", "to": "enrollments.enrollment_id"},
    ],
    "tables": {
        "students": {"description": "Student records", "columns": ["student_id", "first_name", "last_name", "email", "department_id"], "primary_key": ["student_id"]},
        "courses": {"description": "Courses offered by departments", "columns": ["course_id", "course_name", "department_id", "instructor_id"], "primary_key": ["course_id"]},
        "instructors": {"description": "Instructor records", "columns": ["instructor_id", "first_name", "last_name", "email"], "primary_key": ["instructor_id"]},
        "departments": {"description": "Academic departments", "columns": ["department_id", "department_name"], "primary_key": ["department_id"]},
        "enrollments": {"description": "Student course enrollments", "columns": ["enrollment_id", "student_id", "course_id", "enrolled_at"], "primary_key": ["enrollment_id"]},
        "grades": {"description": "Marks and grades for enrollments", "columns": ["grade_id", "enrollment_id", "marks", "grade"], "primary_key": ["grade_id"]},
    },
}


HEALTHCARE_SCHEMA: dict[str, Any] = {
    "schema_pack": "healthcare",
    "display_name": "Healthcare",
    "source": "schema_pack",
    "relationships": [
        {"from": "appointments.doctor_id", "to": "doctors.doctor_id"},
        {"from": "appointments.patient_id", "to": "patients.patient_id"},
        {"from": "prescriptions.appointment_id", "to": "appointments.appointment_id"},
        {"from": "prescriptions.medicine_id", "to": "medicines.medicine_id"},
    ],
    "tables": {
        "doctors": {"description": "Doctor records", "columns": ["doctor_id", "first_name", "last_name", "specialization"], "primary_key": ["doctor_id"]},
        "patients": {"description": "Patient records", "columns": ["patient_id", "first_name", "last_name", "date_of_birth"], "primary_key": ["patient_id"]},
        "appointments": {"description": "Doctor-patient appointments", "columns": ["appointment_id", "doctor_id", "patient_id", "appointment_date", "status"], "primary_key": ["appointment_id"]},
        "prescriptions": {"description": "Medicines prescribed during appointments", "columns": ["prescription_id", "appointment_id", "medicine_id", "dosage"], "primary_key": ["prescription_id"]},
        "medicines": {"description": "Medicine catalog", "columns": ["medicine_id", "medicine_name", "manufacturer"], "primary_key": ["medicine_id"]},
    },
}


LIBRARY_SCHEMA: dict[str, Any] = {
    "schema_pack": "library",
    "display_name": "Library",
    "source": "schema_pack",
    "relationships": [
        {"from": "books.author_id", "to": "authors.author_id"},
        {"from": "books.category_id", "to": "book_categories.category_id"},
        {"from": "borrow_records.book_id", "to": "books.book_id"},
        {"from": "borrow_records.member_id", "to": "members.member_id"},
    ],
    "tables": {
        "books": {"description": "Library books", "columns": ["book_id", "title", "author_id", "category_id", "published_year"], "primary_key": ["book_id"]},
        "authors": {"description": "Book authors", "columns": ["author_id", "author_name"], "primary_key": ["author_id"]},
        "members": {"description": "Library members", "columns": ["member_id", "first_name", "last_name", "email"], "primary_key": ["member_id"]},
        "borrow_records": {"description": "Book borrowing records", "columns": ["borrow_id", "book_id", "member_id", "borrow_date", "due_date", "return_date"], "primary_key": ["borrow_id"]},
        "book_categories": {"description": "Book categories", "columns": ["category_id", "category_name"], "primary_key": ["category_id"]},
    },
}


BANKING_SCHEMA: dict[str, Any] = {
    "schema_pack": "banking",
    "display_name": "Banking",
    "source": "schema_pack",
    "relationships": [
        {"from": "accounts.customer_id", "to": "customers.customer_id"},
        {"from": "accounts.branch_id", "to": "branches.branch_id"},
        {"from": "transactions.account_id", "to": "accounts.account_id"},
    ],
    "tables": {
        "customers": {"description": "Bank customers", "columns": ["customer_id", "first_name", "last_name", "email"], "primary_key": ["customer_id"]},
        "accounts": {"description": "Customer bank accounts", "columns": ["account_id", "customer_id", "branch_id", "account_type", "balance"], "primary_key": ["account_id"]},
        "transactions": {"description": "Account transactions", "columns": ["transaction_id", "account_id", "transaction_date", "transaction_type", "amount"], "primary_key": ["transaction_id"]},
        "branches": {"description": "Bank branches", "columns": ["branch_id", "branch_name", "city"], "primary_key": ["branch_id"]},
    },
}


BOOKING_SCHEMA: dict[str, Any] = {
    "schema_pack": "booking",
    "display_name": "Hotel/Booking",
    "source": "schema_pack",
    "relationships": [
        {"from": "rooms.hotel_id", "to": "hotels.hotel_id"},
        {"from": "bookings.room_id", "to": "rooms.room_id"},
        {"from": "bookings.guest_id", "to": "guests.guest_id"},
        {"from": "payments.booking_id", "to": "bookings.booking_id"},
    ],
    "tables": {
        "hotels": {"description": "Hotels", "columns": ["hotel_id", "hotel_name", "city"], "primary_key": ["hotel_id"]},
        "rooms": {"description": "Hotel rooms", "columns": ["room_id", "hotel_id", "room_number", "room_type", "status", "price_per_night"], "primary_key": ["room_id"]},
        "guests": {"description": "Hotel guests", "columns": ["guest_id", "first_name", "last_name", "email"], "primary_key": ["guest_id"]},
        "bookings": {"description": "Room bookings", "columns": ["booking_id", "room_id", "guest_id", "check_in_date", "check_out_date", "status"], "primary_key": ["booking_id"]},
        "payments": {"description": "Booking payments", "columns": ["payment_id", "booking_id", "payment_date", "amount"], "primary_key": ["payment_id"]},
    },
}


SCHEMA_PACKS: dict[str, dict[str, Any]] = {
    "hr": HR_SCHEMA,
    "ecommerce": ECOMMERCE_SCHEMA,
    "university": UNIVERSITY_SCHEMA,
    "healthcare": HEALTHCARE_SCHEMA,
    "library": LIBRARY_SCHEMA,
    "banking": BANKING_SCHEMA,
    "booking": BOOKING_SCHEMA,
}


SCHEMA_PACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hr": ("employee", "employees", "salary", "department", "departments", "job", "jobs", "manager", "dependent"),
    "university": ("student", "students", "course", "courses", "instructor", "teacher", "enrollment", "enrollments", "grade", "grades", "marks", "university"),
    "healthcare": ("doctor", "doctors", "patient", "patients", "appointment", "appointments", "hospital", "medicine", "medicines", "prescription", "prescriptions"),
    "library": ("book", "books", "author", "authors", "member", "members", "borrower", "issue", "issued", "return", "returned", "library"),
    "ecommerce": ("product", "products", "customer", "customers", "order", "orders", "revenue", "sales", "category", "categories", "payment", "payments", "cart"),
    "banking": ("account", "accounts", "transaction", "transactions", "bank", "balance", "deposit", "withdraw", "loan", "loans", "branch"),
    "booking": ("booking", "bookings", "hotel", "hotels", "room", "rooms", "guest", "guests", "reservation", "reservations", "checkin", "checkout", "check-in", "check-out", "check in", "check out"),
}


def normalize_schema_pack(value: Optional[str]) -> str:
    """Return canonical schema-pack id or 'auto'."""
    raw = (value or "auto").strip().lower().replace("_", "-")
    aliases = {
        "auto-detect": "auto",
        "autodetect": "auto",
        "e-commerce": "ecommerce",
        "ecommerce": "ecommerce",
        "hotel": "booking",
        "hotel-booking": "booking",
        "hotel/booking": "booking",
        "booking": "booking",
        "hr": "hr",
        "human-resources": "hr",
    }
    return aliases.get(raw, raw)


def detect_schema_pack(prompt: str, requested: Optional[str] = "auto") -> dict[str, Any]:
    """
    Resolve selected schema pack.

    Returns a small decision dict so routes can distinguish unsupported domains
    from known schema packs without calling any external service.
    """
    requested_pack = normalize_schema_pack(requested)
    if requested_pack != "auto":
        if requested_pack in SCHEMA_PACKS:
            return {"schema_pack": requested_pack, "detected_domain": requested_pack, "unsupported": False}
        return {"schema_pack": "", "detected_domain": "", "unsupported": True}

    text = (prompt or "").lower()
    scores: dict[str, int] = {}
    for pack, keywords in SCHEMA_PACK_KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text))
        if score:
            scores[pack] = score

    if not scores:
        return {"schema_pack": "", "detected_domain": "", "unsupported": True}

    pack = max(scores, key=scores.get)
    return {"schema_pack": pack, "detected_domain": pack, "unsupported": False}


def get_demo_schema() -> dict[str, Any]:
    """Return the built-in HR schema used when live DB introspection is unavailable."""
    return get_schema_pack("hr")


def get_schema_pack(schema_pack: str = "hr") -> dict[str, Any]:
    """Return local schema-pack metadata."""
    pack = normalize_schema_pack(schema_pack)
    schema = SCHEMA_PACKS.get(pack, HR_SCHEMA)
    return {
        **schema,
        "tables": {name: dict(info) for name, info in schema.get("tables", {}).items()},
        "relationships": [dict(rel) for rel in schema.get("relationships", [])],
    }


def read_schema_from_db(db_type: str, schema_pack: str = "hr") -> dict[str, Any]:
    """Introspect the live database and return a schema dictionary."""
    pack = normalize_schema_pack(schema_pack)
    fallback = get_schema_pack(pack)
    engine = get_engine(db_type, pack)
    inspector = inspect(engine)
    schema: dict[str, Any] = {
        "schema_pack": pack,
        "display_name": fallback.get("display_name", pack.title()),
        "source": "database",
        "relationships": fallback.get("relationships", []),
        "tables": {},
    }

    for table_name in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        pk = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        schema["tables"][table_name] = {
            "description": fallback.get("tables", {}).get(table_name, {}).get("description", ""),
            "columns": columns,
            "primary_key": pk,
        }

    return schema


def load_schema(db_type: str, schema_pack: str = "hr") -> dict[str, Any]:
    """Load schema from the selected internal DB, falling back to local metadata."""
    pack = normalize_schema_pack(schema_pack)
    if is_db_connected(db_type, pack):
        try:
            live_schema = read_schema_from_db(db_type, pack)
            if live_schema.get("tables"):
                return live_schema
        except Exception:
            pass
    return get_schema_pack(pack)


def get_schema_details(schema_pack: str = "hr", db_type: str = "mysql") -> dict[str, Any]:
    """Return schema details for GET /api/schema."""
    pack = normalize_schema_pack(schema_pack)
    schema = load_schema(db_type, pack)
    tables_detail = []
    for name, info in schema["tables"].items():
        tables_detail.append({
            "name": name,
            "description": info.get("description", ""),
            "columns": info["columns"],
            "primary_key": info.get("primary_key", []),
        })

    return {
        "schema_pack": schema.get("schema_pack", pack),
        "display_name": schema.get("display_name", pack.title()),
        "mode": "live" if is_db_connected(db_type, pack) else "demo",
        "tables": tables_detail,
        "relationships": schema.get("relationships", HR_RELATIONSHIPS),
        "table_count": len(tables_detail),
    }


def get_table_names(schema: dict[str, Any]) -> list[str]:
    """Return sorted list of table names."""
    return sorted(schema.get("tables", {}).keys())


def get_columns_for_table(schema: dict[str, Any], table_name: str) -> list[str]:
    """Return column names for a given table."""
    for key, info in schema.get("tables", {}).items():
        if key.lower() == table_name.lower():
            return info.get("columns", [])
    return []
