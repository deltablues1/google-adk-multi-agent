-- Migration: Create sessions table for PostgreSQL
-- Version: 001
-- Date: 2024-01-15

CREATE TABLE IF NOT EXISTS adk_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    metadata JSONB DEFAULT '{}',
    history JSONB DEFAULT '[]',
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON adk_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON adk_sessions(updated_at);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to call the function
CREATE TRIGGER update_adk_sessions_updated_at 
    BEFORE UPDATE ON adk_sessions 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
