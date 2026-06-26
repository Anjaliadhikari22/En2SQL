CREATE TABLE categories (
  category_id INT AUTO_INCREMENT PRIMARY KEY,
  category_name VARCHAR(100) NOT NULL
);

CREATE TABLE products (
  product_id INT AUTO_INCREMENT PRIMARY KEY,
  product_name VARCHAR(150) NOT NULL,
  category_id INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  stock_quantity INT DEFAULT 0,
  FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE customers (
  customer_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL,
  created_at DATE NOT NULL
);

CREATE TABLE orders (
  order_id INT AUTO_INCREMENT PRIMARY KEY,
  customer_id INT NOT NULL,
  order_date DATE NOT NULL,
  status VARCHAR(40) NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
  order_item_id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE payments (
  payment_id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  payment_date DATE NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  payment_method VARCHAR(50),
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

INSERT INTO categories VALUES (1,'Electronics'),(2,'Books'),(3,'Clothing');
INSERT INTO products VALUES (1,'Laptop',1,75000,10),(2,'Headphones',1,2500,50),(3,'SQL Guide',2,899,25),(4,'Jacket',3,3200,20);
INSERT INTO customers VALUES (1,'Anjali','Adhikari','anjali@example.com','2025-01-10'),(2,'Rahul','Sharma','rahul@example.com','2025-02-11'),(3,'Maya','Rai','maya@example.com','2025-03-12');
INSERT INTO orders VALUES (1,1,'2025-01-15','Paid'),(2,2,'2025-02-20','Paid');
INSERT INTO order_items VALUES (1,1,1,1,75000),(2,1,2,2,2500),(3,2,3,5,899);
INSERT INTO payments VALUES (1,1,'2025-01-15',80000,'Card'),(2,2,'2025-02-20',4495,'UPI');
