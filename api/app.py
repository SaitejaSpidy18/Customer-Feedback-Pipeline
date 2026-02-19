from flask import Flask, request, jsonify
from kafka import KafkaProducer
import uuid
import json
import os
import pymysql
from datetime import datetime
from dotenv import load_dotenv
import logging
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)
# Kafka configuration
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'kafka:9092')
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
    retries=3
)
# MySQL configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'mysql'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'root_password'),
    'database': os.getenv('MYSQL_DATABASE', 'feedback_db'),
    'charset': 'utf8mb4'
}
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200
@app.route('/feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        required_fields = ['customer_id', 'feedback_text', 'timestamp']
        if not all(k in data for k in required_fields):
            return jsonify({'error': f'Missing required fields: {required_fields}'}), 400
        # Validate timestamp format
        try:
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format. Use ISO 8601'}), 400
        # Validate non-empty strings
        if not data['customer_id'].strip() or not data['feedback_text'].strip():
            return jsonify({'error': 'customer_id and feedback_text cannot be empty'}), 400
        message_id = str(uuid.uuid4())
        feedback_event = {
            'message_id': message_id,
            'customer_id': data['customer_id'],
            'feedback_text': data['feedback_text'],
            'feedback_timestamp': data['timestamp']
        }
        # Publish to Kafka asynchronously
        future = producer.send('customer_feedback_events', feedback_event)
        producer.flush()  # Ensure message is sent
        logger.info(f'Feedback submitted: {message_id} for customer {data["customer_id"]}')
        return jsonify({
            'message': 'Feedback received for processing',
            'message_id': message_id
        }), 202
    except Exception as e:
        logger.error(f'Error processing feedback: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500
@app.route('/feedback/<message_id>', methods=['GET'])
def get_feedback(message_id):
    try:
        connection = pymysql.connect(**MYSQL_CONFIG)
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM feedback_analysis WHERE message_id = %s",
                (message_id,)
            )
            result = cursor.fetchone()
        if result:
            return jsonify(result), 200
        return jsonify({'error': 'Feedback not found'}), 404
    except Exception as e:
        logger.error(f'Database error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        if 'connection' in locals():
            connection.close()
@app.route('/feedback', methods=['GET'])
def get_feedback_by_sentiment():
    try:
        sentiment = request.args.get('sentiment')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit
        if sentiment not in ['positive', 'negative', 'neutral']:
            return jsonify({'error': 'sentiment must be positive, negative, or neutral'}), 400
        connection = pymysql.connect(**MYSQL_CONFIG)
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM feedback_analysis WHERE sentiment_score = %s LIMIT %s OFFSET %s",
                (sentiment, limit, offset)
            )
            results = cursor.fetchall()
        return jsonify({
            'feedback': results,
            'page': page,
            'limit': limit,
            'sentiment': sentiment
        }), 200
    except Exception as e:
        logger.error(f'Database error: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        if 'connection' in locals():
            connection.close()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
