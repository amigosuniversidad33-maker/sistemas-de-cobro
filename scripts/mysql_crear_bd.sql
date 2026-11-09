-- Ejecutar UNA vez como root en MySQL 8 (MySQL Workbench o: mysql -u root -p < scripts\mysql_crear_bd.sql)
-- ANTES de ejecutar, reemplace las dos contraseñas de ejemplo por contraseñas largas y únicas.
-- No guarde este archivo con las contraseñas reales en el repositorio.

CREATE DATABASE IF NOT EXISTS cobros_ia CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- Usuario de la APLICACIÓN: solo datos (sin DDL). Solo puede conectarse desde este equipo.
CREATE USER IF NOT EXISTS 'cobros_app'@'localhost' IDENTIFIED BY 'CAMBIE_ESTA_CLAVE_APP';
GRANT SELECT, INSERT, UPDATE, DELETE ON cobros_ia.* TO 'cobros_app'@'localhost';

-- Usuario de MIGRACIONES y RESPALDOS: puede crear/alterar tablas. Úselo en DATABASE_URL_MIGRACIONES.
CREATE USER IF NOT EXISTS 'cobros_migra'@'localhost' IDENTIFIED BY 'CAMBIE_ESTA_CLAVE_MIGRA';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES, LOCK TABLES, SHOW VIEW, TRIGGER
  ON cobros_ia.* TO 'cobros_migra'@'localhost';

FLUSH PRIVILEGES;
