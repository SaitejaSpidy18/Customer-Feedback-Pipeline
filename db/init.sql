CREATE DATABASE IF NOT EXISTS feedback_db;
USE feedback_db;
CREATE TABLE IF NOT EXISTS feedback_analysis (
    message_id VARCHAR(36) PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    feedback_text TEXT NOT NULL,
    sentiment_score VARCHAR(20) NOT NULL,
    feedback_timestamp DATETIME NOT NULL,
    analysis_timestamp DATETIME NOT NULL,
    INDEX idx_customer_id (customer_id),
    INDEX idx_sentiment_score (sentiment_score),
    INDEX idx_feedback_timestamp (feedback_timestamp)
);
