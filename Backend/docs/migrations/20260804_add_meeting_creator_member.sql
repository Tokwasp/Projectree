-- 기존 Meeting을 보존하기 위해 최초 배포에서는 nullable로 추가한다.
ALTER TABLE meeting
    ADD COLUMN creator_member_id INT NULL AFTER project_id;

-- 생성자는 현재 ProjectMember 생명주기와 독립된 과거 기록이므로 FK를 두지 않는다.
CREATE INDEX idx_meeting_project_creator
    ON meeting(project_id, creator_member_id);

-- 코드 배포 후 Redis에서 신뢰 가능한 creator/room을 다시 읽은 Meeting만 보충한다.
-- Redis에 근거가 없는 기존 Meeting의 생성자를 임의로 추정하지 않는다.
SELECT COUNT(*) AS meeting_creator_not_registered
FROM meeting
WHERE creator_member_id IS NULL;

-- NULL이 0건이고 별도 운영 승인을 받은 뒤에만 후속 배포에서 실행한다.
-- ALTER TABLE meeting
--     MODIFY COLUMN creator_member_id INT NOT NULL;
