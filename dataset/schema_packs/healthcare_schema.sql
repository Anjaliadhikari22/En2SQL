CREATE TABLE doctors (
  doctor_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  specialization VARCHAR(100)
);

CREATE TABLE patients (
  patient_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  date_of_birth DATE
);

CREATE TABLE appointments (
  appointment_id INT AUTO_INCREMENT PRIMARY KEY,
  doctor_id INT NOT NULL,
  patient_id INT NOT NULL,
  appointment_date DATE NOT NULL,
  status VARCHAR(40),
  FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
  FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE TABLE medicines (
  medicine_id INT AUTO_INCREMENT PRIMARY KEY,
  medicine_name VARCHAR(120) NOT NULL,
  manufacturer VARCHAR(120)
);

CREATE TABLE prescriptions (
  prescription_id INT AUTO_INCREMENT PRIMARY KEY,
  appointment_id INT NOT NULL,
  medicine_id INT NOT NULL,
  dosage VARCHAR(80),
  FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id),
  FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
);

INSERT INTO doctors VALUES (1,'Rita','Shrestha','Cardiology'),(2,'Om','Bista','Dermatology');
INSERT INTO patients VALUES (1,'Kiran','Rai','1995-04-12'),(2,'Sita','Maharjan','1988-09-08');
INSERT INTO appointments VALUES (1,1,1,'2025-03-10','Completed'),(2,2,2,'2025-03-11','Scheduled');
INSERT INTO medicines VALUES (1,'Atorvastatin','MediCo'),(2,'Cetirizine','HealthLabs');
INSERT INTO prescriptions VALUES (1,1,1,'10mg daily');
