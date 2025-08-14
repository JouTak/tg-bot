CREATE DATABASE IF NOT EXISTS itmocraft_tg_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE itmocraft_tg_bot;

CREATE TABLE IF NOT EXISTS users (
  tg_id     BIGINT        NOT NULL PRIMARY KEY,
  nc_login  VARCHAR(100)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
  card_id     INT             NOT NULL PRIMARY KEY,
  title       VARCHAR(255)    NOT NULL,
  description TEXT            NOT NULL,
  board_id    INT             NOT NULL,
  board_title VARCHAR(100)    NOT NULL,
  stack_id    INT             NOT NULL,
  stack_title VARCHAR(100)    NOT NULL,
  duedate     DATETIME        NULL,
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS task_assignees (
  card_id INT NOT NULL,
  nc_login VARCHAR(100) NOT NULL,
  PRIMARY KEY(card_id, nc_login)
)ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS task_stats (
  card_id BIGINT PRIMARY KEY,
  comments_count INT NOT NULL DEFAULT 0,
  attachments_count INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS board_log_topics (
  board_id         INT NOT NULL PRIMARY KEY,
  message_thread_id BIGINT NOT NULL,
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
