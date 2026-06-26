CREATE TABLE departments (
  department_id INT AUTO_INCREMENT PRIMARY KEY,
  department_name VARCHAR(100) NOT NULL
);

CREATE TABLE instructors (
  instructor_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL
);

CREATE TABLE students (
  student_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL,
  department_id INT,
  FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE courses (
  course_id INT AUTO_INCREMENT PRIMARY KEY,
  course_name VARCHAR(120) NOT NULL,
  department_id INT,
  instructor_id INT,
  FOREIGN KEY (department_id) REFERENCES departments(department_id),
  FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id)
);

CREATE TABLE enrollments (
  enrollment_id INT AUTO_INCREMENT PRIMARY KEY,
  student_id INT NOT NULL,
  course_id INT NOT NULL,
  enrolled_at DATE NOT NULL,
  FOREIGN KEY (student_id) REFERENCES students(student_id),
  FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE TABLE grades (
  grade_id INT AUTO_INCREMENT PRIMARY KEY,
  enrollment_id INT NOT NULL,
  marks DECIMAL(5,2) NOT NULL,
  grade VARCHAR(5),
  FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id)
);

INSERT INTO departments VALUES (1,'Computer Science'),(2,'Management');
INSERT INTO instructors VALUES (1,'Priya','Karki','priya@example.com'),(2,'Suman','Rana','suman@example.com');
INSERT INTO students VALUES (1,'Nisha','Thapa','nisha@example.com',1),(2,'Amit','Gurung','amit@example.com',1);
INSERT INTO courses VALUES (1,'Database Systems',1,1),(2,'Business Analytics',2,2);
INSERT INTO enrollments VALUES (1,1,1,'2025-01-01'),(2,2,1,'2025-01-02'),(3,1,2,'2025-01-03');
INSERT INTO grades VALUES (1,1,92,'A'),(2,2,85,'B'),(3,3,88,'B+');
