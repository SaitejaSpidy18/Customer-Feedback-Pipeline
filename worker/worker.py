import json
import os
import logging
import pymysql
import time
from datetime import datetime
from kafka import KafkaConsumer
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from dotenv import load_dotenv
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()
# Initialize NLTK
analyzer = SentimentIntensityAnalyzer()
# MySQL configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'mysql'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'root_password'),
    'database': os.getenv('MYSQL_DATABASE', 'feedback_db'),
    'charset': 'utf8mb4',
    'autocommit': True
}
def get_mysql_connection():
    return pymysql.connect(**MYSQL_CONFIG)
def analyze_sentiment(text):
    """Perform sentiment analysis using VADER"""
    scores = analyzer.polarity_scores(text)
    compound = scores['compound']
    if compound >= 0.05:
        return 'positive'
    elif compound <= -0.05:
        return 'negative'
    else:
        return 'neutral'
def store_feedback_analysis(message_id, customer_id, feedback_text, sentiment_score, feedback_timestamp):
    """Idempotent storage of feedback analysis"""
    try:
        connection = get_mysql_connection()
        with connection.cursor() as cursor:
            # Try INSERT first, ignore if exists (idempotent)
            cursor.execute("""
                INSERT IGNORE INTO feedback_analysis 
                (message_id, customer_id, feedback_text, sentiment_score, feedback_timestamp, analysis_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                message_id, customer_id, feedback_text, sentiment_score,
                feedback_timestamp, datetime.now()
            ))
            if cursor.rowcount == 0:
                logger.warning(f"Message {message_id} already processed (idempotent skip)")
                return False
            logger.info(f"Stored analysis for message {message_id}: {sentiment_score}")
            return True
    except Exception as e:
        logger.error(f"Database error for {message_id}: {str(e)}")
        return False
    finally:
        if 'connection' in locals():
            connection.close()
def main():
    kafka_broker = os.getenv('KAFKA_BROKER', 'kafka:9092')
    consumer = KafkaConsumer(
        'customer_feedback_events',
        bootstrap_servers=[kafka_broker],
        auto_offset_reset='earliest',
        enable_auto_commit=False,  # Manual commit for reliability
        group_id='sentiment_analyzer_group_v1',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )
    logger.info("Worker started, consuming from customer_feedback_events topic")
    for message in consumer:
        try:
            feedback = message.value
            logger.info(f"Processing message {feedback.get('message_id')}")
            # Extract required fields with validation
            required_fields = ['message_id', 'customer_id', 'feedback_text', 'feedback_timestamp']
            if not all(field in feedback for field in required_fields):
                logger.error(f"Missing required fields in message: {feedback}")
                consumer.commit()
                continue
            message_id = feedback['message_id']
            customer_id = feedback['customer_id']
            feedback_text = feedback['feedback_text']
            feedback_timestamp = feedback['feedback_timestamp']
            # Perform sentiment analysis
            sentiment_score = analyze_sentiment(feedback_text)
            # Store with idempotency
            if store_feedback_analysis(
                message_id, customer_id, feedback_text, 
                sentiment_score, feedback_timestamp
            ):
                logger.info(f"Successfully processed {message_id}: {sentiment_score}")
            else:
                logger.warning(f"Failed to store or already processed {message_id}")
            # Manual commit after successful processing
            consumer.commit()
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            consumer.commit()
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            # Don't commit on error to allow retry
            time.sleep(5)  # Brief pause before retry
if __name__ == '__main__':
    main()
