-- =============================================================================
-- PostgreSQL Sample Schema — University Database
-- Used by the Natural Language to SQL Generator for demo and viva walkthroughs
-- =============================================================================

-- Create database (run as superuser if needed):
-- CREATE DATABASE university_db;

-- Departments
CREATE TABLE IF NOT EXISTS departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    location    VARCHAR(100),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Students
CREATE TABLE IF NOT EXISTS students (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    age             INT,
    department_id   INT REFERENCES departments(id) ON DELETE SET NULL,
    enrollment_date DATE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Courses
CREATE TABLE IF NOT EXISTS courses (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(150) NOT NULL,
    code            VARCHAR(20) NOT NULL UNIQUE,
    credits         INT DEFAULT 3,
    department_id   INT REFERENCES departments(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enrollments (many-to-many: students ↔ courses)
CREATE TABLE IF NOT EXISTS enrollments (
    id          SERIAL PRIMARY KEY,
    student_id  INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id   INT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    grade       CHAR(2),
    enrolled_at DATE,
    UNIQUE (student_id, course_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_students_department ON students(department_id);
CREATE INDEX IF NOT EXISTS idx_students_age ON students(age);
CREATE INDEX IF NOT EXISTS idx_courses_department ON courses(department_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
