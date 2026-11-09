-- Ejecutar en phpMyAdmin (http://localhost/phpmyadmin) sobre la base "cobros"
CREATE DATABASE IF NOT EXISTS cobros CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cobros;

CREATE TABLE IF NOT EXISTS telefonos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  telefono VARCHAR(20) NOT NULL,          -- formato +502XXXXXXXX
  monto DECIMAL(10,2) NOT NULL DEFAULT 0, -- saldo pendiente a mencionar en la llamada
  creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llamadas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  telefono_id INT NOT NULL,
  call_sid VARCHAR(64),
  estado VARCHAR(30),
  duracion INT DEFAULT NULL,
  error TEXT,
  creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (telefono_id) REFERENCES telefonos(id) ON DELETE CASCADE
);
