from flask import Flask, request
from src.webhook.handler import handle_event
from src.logger import log_info, log_error

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        event = data.get('event')
        task_id = data.get('data', {}).get('FIELDS', {}).get('ID')
        
        log_info(f"Получен вебхук: {event} для задачи {task_id}")
        
        if event and task_id:
            handle_event(event, task_id)
            return {"status": "ok"}, 200
        
        return {"error": "Invalid request"}, 400
    except Exception as e:
        log_error(f"Ошибка вебхука: {e}")
        return {"error": str(e)}, 500

def start_webhook_server():
    """Запускает Flask-сервер для приёма вебхуков."""
    app.run(host="0.0.0.0", port=5000)