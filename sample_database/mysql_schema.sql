-- =============================================================================
-- MySQL Sample Schema — University Database
-- Used by the Natural Language to SQL Generator for demo and viva walkthroughs
-- =============================================================================

CREATE DATABASE IF NOT EXISTS university_db;
USE university_db;

-- Departments
CREATE TABLE IF NOT EXISTS departments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    location    VARCHAR(100),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Students
CREATE TABLE IF NOT EXISTS students (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    age             INT,
    department_id   INT,
    enrollment_date DATE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
        ON DELETE SET NULL
);

-- Courses
CREATE TABLE IF NOT EXISTS courses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    title           VARCHAR(150) NOT NULL,
    code            VARCHAR(20) NOT NULL UNIQUE,
    credits         INT DEFAULT 3,
    department_id   INT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id)
        ON DELETE SET NULL
);

-- Enrollments (many-to-many: students ↔ courses)
CREATE TABLE IF NOT EXISTS enrollments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    student_id  INT NOT NULL,
    course_id   INT NOT NULL,
    grade       CHAR(2),
    enrolled_at DATE,
    FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id)
        ON DELETE CASCADE,
    UNIQUE KEY unique_enrollment (student_id, course_id)
);

-- Indexes for common query patterns
CREATE INDEX idx_students_department ON students(department_id);
CREATE INDEX idx_students_age ON students(age);
CREATE INDEX idx_courses_department ON courses(department_id);
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
