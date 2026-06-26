CREATE TABLE regions (
  region_id INT AUTO_INCREMENT PRIMARY KEY,
  region_name VARCHAR(100) NOT NULL
);

CREATE TABLE countries (
  country_id CHAR(2) PRIMARY KEY,
  country_name VARCHAR(100) NOT NULL,
  region_id INT,
  FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE locations (
  location_id INT AUTO_INCREMENT PRIMARY KEY,
  street_address VARCHAR(150),
  postal_code VARCHAR(30),
  city VARCHAR(100) NOT NULL,
  state_province VARCHAR(100),
  country_id CHAR(2),
  FOREIGN KEY (country_id) REFERENCES countries(country_id)
);

CREATE TABLE jobs (
  job_id INT AUTO_INCREMENT PRIMARY KEY,
  job_title VARCHAR(100) NOT NULL,
  min_salary DECIMAL(10,2),
  max_salary DECIMAL(10,2)
);

CREATE TABLE departments (
  department_id INT AUTO_INCREMENT PRIMARY KEY,
  department_name VARCHAR(100) NOT NULL,
  location_id INT,
  FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

CREATE TABLE employees (
  employee_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80),
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL,
  phone_number VARCHAR(40),
  hire_date DATE NOT NULL,
  job_id INT,
  salary DECIMAL(10,2),
  manager_id INT,
  department_id INT,
  FOREIGN KEY (job_id) REFERENCES jobs(job_id),
  FOREIGN KEY (manager_id) REFERENCES employees(employee_id),
  FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE dependents (
  dependent_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  relationship VARCHAR(50),
  employee_id INT NOT NULL,
  FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

INSERT INTO regions VALUES (1,'Americas'),(2,'Europe'),(3,'Asia');
INSERT INTO countries VALUES ('US','United States',1),('NP','Nepal',3);
INSERT INTO locations VALUES (1,'Main Street','10001','New York','NY','US'),(2,'Durbar Marg','44600','Kathmandu','Bagmati','NP');
INSERT INTO jobs VALUES (1,'Developer',40000,120000),(2,'Manager',60000,160000),(3,'Sales Representative',30000,100000);
INSERT INTO departments VALUES (1,'IT',2),(2,'Sales',1),(3,'Finance',1);
INSERT INTO employees VALUES
  (1,'Anjali','Adhikari','anjali@example.com','555-1000','2020-01-01',1,90000,NULL,1),
  (2,'Rahul','Sharma','rahul@example.com','555-1001','2021-02-01',2,120000,1,1),
  (3,'Maya','Rai','maya@example.com','555-1002','2022-03-01',3,70000,2,2);
INSERT INTO dependents VALUES (1,'Asha','Adhikari','Child',1);
