-- =============================================================================
-- Sample Data — University Database (compatible with MySQL and PostgreSQL)
-- Load after running the appropriate schema file.
-- =============================================================================

-- Departments
INSERT INTO departments (name, location) VALUES
    ('Computer Science', 'Building A'),
    ('Mathematics',      'Building B'),
    ('Physics',          'Building C');

-- Students
INSERT INTO students (name, email, age, department_id, enrollment_date) VALUES
    ('Alice Johnson',  'alice@university.edu',  20, 1, '2023-09-01'),
    ('Bob Smith',      'bob@university.edu',    22, 1, '2022-09-01'),
    ('Carol Williams', 'carol@university.edu',  19, 2, '2024-01-15'),
    ('David Brown',    'david@university.edu',  21, 3, '2023-09-01'),
    ('Eva Martinez',   'eva@university.edu',    23, 1, '2021-09-01');

-- Courses
INSERT INTO courses (title, code, credits, department_id) VALUES
    ('Database Systems',    'CS301', 4, 1),
    ('Calculus I',          'MATH101', 3, 2),
    ('Linear Algebra',      'MATH201', 3, 2),
    ('Quantum Mechanics',   'PHY401', 4, 3),
    ('Web Development',     'CS201', 3, 1);

-- Enrollments
INSERT INTO enrollments (student_id, course_id, grade, enrolled_at) VALUES
    (1, 1, 'A',  '2024-01-10'),
    (1, 5, 'B+', '2024-01-10'),
    (2, 1, 'A-', '2024-01-10'),
    (2, 5, 'A',  '2024-01-10'),
    (3, 2, 'B',  '2024-01-15'),
    (3, 3, 'A',  '2024-01-15'),
    (4, 4, 'B+', '2024-01-20'),
    (5, 1, 'A',  '2023-09-05'),
    (5, 5, 'A+', '2023-09-05');
