CREATE TABLE hotels (
  hotel_id INT AUTO_INCREMENT PRIMARY KEY,
  hotel_name VARCHAR(150) NOT NULL,
  city VARCHAR(100) NOT NULL
);

CREATE TABLE rooms (
  room_id INT AUTO_INCREMENT PRIMARY KEY,
  hotel_id INT NOT NULL,
  room_number VARCHAR(20) NOT NULL,
  room_type VARCHAR(80),
  status VARCHAR(40) NOT NULL,
  price_per_night DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (hotel_id) REFERENCES hotels(hotel_id)
);

CREATE TABLE guests (
  guest_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL
);

CREATE TABLE bookings (
  booking_id INT AUTO_INCREMENT PRIMARY KEY,
  room_id INT NOT NULL,
  guest_id INT NOT NULL,
  check_in_date DATE NOT NULL,
  check_out_date DATE NOT NULL,
  status VARCHAR(40),
  FOREIGN KEY (room_id) REFERENCES rooms(room_id),
  FOREIGN KEY (guest_id) REFERENCES guests(guest_id)
);

CREATE TABLE payments (
  payment_id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  payment_date DATE NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
);

INSERT INTO hotels VALUES (1,'En2SQL Grand','Kathmandu'),(2,'Lake View Inn','Pokhara');
INSERT INTO rooms VALUES (1,1,'101','Deluxe','Available',6500),(2,1,'102','Suite','Booked',12000),(3,2,'201','Standard','Available',4500);
INSERT INTO guests VALUES (1,'Mina','Gurung','mina@example.com'),(2,'Arjun','Khadka','arjun@example.com');
INSERT INTO bookings VALUES (1,2,1,'2025-04-01','2025-04-03','Confirmed');
INSERT INTO payments VALUES (1,1,'2025-04-01',24000);
