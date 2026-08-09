-- 적용 대상: project_node_projection.content
-- 변경 사유: API는 content를 최대 65,535자로 허용하므로 utf8mb4에서 TEXT의
--           65,535바이트 한도를 초과할 수 있다.
-- 적용 전 타입: TEXT NOT NULL
-- 적용 후 타입: MEDIUMTEXT NOT NULL

ALTER TABLE project_node_projection
    MODIFY COLUMN content MEDIUMTEXT NOT NULL;

-- 롤백 SQL:
-- ALTER TABLE project_node_projection
--     MODIFY COLUMN content TEXT NOT NULL;
--
-- 주의: TEXT 바이트 한도를 초과하는 데이터가 존재하면 데이터 손실 없이 롤백할 수 없다.
