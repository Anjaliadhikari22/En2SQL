CREATE TABLE branches (
  branch_id INT AUTO_INCREMENT PRIMARY KEY,
  branch_name VARCHAR(120) NOT NULL,
  city VARCHAR(100) NOT NULL
);

CREATE TABLE customers (
  customer_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL
);

CREATE TABLE accounts (
  account_id INT AUTO_INCREMENT PRIMARY KEY,
  customer_id INT NOT NULL,
  branch_id INT NOT NULL,
  account_type VARCHAR(50),
  balance DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  FOREIGN KEY (branch_id) REFERENCES branches(branch_id)
);

CREATE TABLE transactions (
  transaction_id INT AUTO_INCREMENT PRIMARY KEY,
  account_id INT NOT NULL,
  transaction_date DATE NOT NULL,
  transaction_type VARCHAR(40) NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

INSERT INTO branches VALUES (1,'Central Branch','Kathmandu'),(2,'Lakeside Branch','Pokhara');
INSERT INTO customers VALUES (1,'Puja','Basnet','puja@example.com'),(2,'Nabin','Rai','nabin@example.com');
INSERT INTO accounts VALUES (1,1,1,'Savings',120000),(2,2,2,'Current',85000);
INSERT INTO transactions VALUES (1,1,'2025-01-01','Deposit',20000),(2,1,'2025-01-05','Withdraw',5000),(3,2,'2025-01-07','Deposit',15000);
