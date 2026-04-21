-- Smart Office Life Agent: 스키마 분리 초기화
-- docker-entrypoint-initdb.d 에 의해 최초 1회만 실행됨.

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS agent_state;
CREATE SCHEMA IF NOT EXISTS workflow;

-- 권한 부여 (POSTGRES_USER 기준)
DO $$
DECLARE
    db_user text := current_user;
BEGIN
    EXECUTE format('GRANT ALL ON SCHEMA auth TO %I', db_user);
    EXECUTE format('GRANT ALL ON SCHEMA agent_state TO %I', db_user);
    EXECUTE format('GRANT ALL ON SCHEMA workflow TO %I', db_user);
END $$;

COMMENT ON SCHEMA auth IS '사용자 인증/프로필 (users, credentials 등)';
COMMENT ON SCHEMA agent_state IS '에이전트 & 펫 상태 (pet_profile, activity_logs, adk_*)';
COMMENT ON SCHEMA workflow IS 'ADK Graph Workflow 실행 히스토리/체크포인트';

-- 펫 챗봇 MemoryService 의 텍스트 검색(ILIKE) 가속용
CREATE EXTENSION IF NOT EXISTS pg_trgm;
