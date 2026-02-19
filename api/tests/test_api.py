import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_check(client):
    rv = client.get('/health')
    assert rv.status_code == 200

def test_feedback_submission(client):
    data = {
        'customer_id': 'test123',
        'feedback_text': 'Great service!',
        'timestamp': '2026-02-19T14:30:00Z'
    }
    rv = client.post('/feedback', json=data)
    assert rv.status_code == 202
    json_data = rv.get_json()
    assert 'message_id' in json_data