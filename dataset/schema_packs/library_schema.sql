CREATE TABLE authors (
  author_id INT AUTO_INCREMENT PRIMARY KEY,
  author_name VARCHAR(150) NOT NULL
);

CREATE TABLE book_categories (
  category_id INT AUTO_INCREMENT PRIMARY KEY,
  category_name VARCHAR(100) NOT NULL
);

CREATE TABLE books (
  book_id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(180) NOT NULL,
  author_id INT NOT NULL,
  category_id INT NOT NULL,
  published_year INT,
  FOREIGN KEY (author_id) REFERENCES authors(author_id),
  FOREIGN KEY (category_id) REFERENCES book_categories(category_id)
);

CREATE TABLE members (
  member_id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(80) NOT NULL,
  last_name VARCHAR(80) NOT NULL,
  email VARCHAR(150) NOT NULL
);

CREATE TABLE borrow_records (
  borrow_id INT AUTO_INCREMENT PRIMARY KEY,
  book_id INT NOT NULL,
  member_id INT NOT NULL,
  borrow_date DATE NOT NULL,
  due_date DATE NOT NULL,
  return_date DATE,
  FOREIGN KEY (book_id) REFERENCES books(book_id),
  FOREIGN KEY (member_id) REFERENCES members(member_id)
);

INSERT INTO authors VALUES (1,'C. J. Date'),(2,'Jane Austen');
INSERT INTO book_categories VALUES (1,'Database'),(2,'Novel');
INSERT INTO books VALUES (1,'SQL and Relational Theory',1,1,2015),(2,'Pride and Prejudice',2,2,1813);
INSERT INTO members VALUES (1,'Bina','Tamang','bina@example.com'),(2,'Rohit','KC','rohit@example.com');
INSERT INTO borrow_records VALUES (1,1,1,'2025-01-01','2025-01-15','2025-01-10'),(2,2,2,'2025-02-01','2025-02-15',NULL);
