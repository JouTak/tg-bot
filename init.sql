CREATE DATABASE IF NOT EXISTS joutakbot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE joutakbot;

CREATE TABLE IF NOT EXISTS users (
  tg_id     BIGINT        NOT NULL PRIMARY KEY,
  nc_login  VARCHAR(100)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
  id          INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tg_id       BIGINT          NOT NULL,
  card_id     INT             NOT NULL,
  title       VARCHAR(255)    NOT NULL,
  description TEXT            NOT NULL,
  board_id    INT             NOT NULL,
  board_title VARCHAR(100)    NOT NULL,
  stack_id    INT             NOT NULL,
  stack_title VARCHAR(100)    NOT NULL,
  duedate     DATETIME        NULL,
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_tasks_tg_card (tg_id, card_id),
  CONSTRAINT fk_tasks_users
    FOREIGN KEY (tg_id) REFERENCES users (tg_id)
      ON DELETE CASCADE
      ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;