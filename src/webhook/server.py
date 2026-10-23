from flask import Flask, request
from src.webhook.handler import handle_event
from src.logger import log_info, log_error, log_warning
from src.config import BITRIX_PORTAL_DOMAIN, BITRIX_APPLICATION_TOKEN

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Healthcheck — сервис жив?"""
    return {"status": "ok", "service": "isur-bitrix-integration"}, 200


@app.route('/status', methods=['GET'])
def status():
    """Возвращает статус сервиса."""
    from src.state import get_last_sync, get_uptime
    from src.utils.db_utils import load_links, get_missed_webhooks

    try:
        links_count = len(load_links())
        missed_count = len(get_missed_webhooks(limit=1000))
    except Exception as e:
        links_count = -1
        missed_count = -1
        log_error(f"Ошибка получения статуса: {e}")

    return {
        "status": "ok",
        "service": "isur-bitrix-integration",
        "uptime_seconds": get_uptime(),
        "last_sync": get_last_sync(),
        "links_count": links_count,
        "missed_webhooks_count": missed_count
    }, 200


def _verify_webhook(data):
    """Проверяет подлинность вебхука от Битрикс24."""
    # Битрикс передает данные в form-data плоскими ключами с квадратными скобками
    domain = data.get('auth[domain]')
    token = data.get('auth[application_token]')
    
    # Фолбэк для JSON
    if not domain:
        auth = data.get("auth") or {}
        domain = auth.get("domain")
        token = auth.get("application_token")

    if BITRIX_PORTAL_DOMAIN:
        if domain != BITRIX_PORTAL_DOMAIN:
            log_warning(f"Domain mismatch: ожидался {BITRIX_PORTAL_DOMAIN}, получен {domain}")
            return False

    if BITRIX_APPLICATION_TOKEN:
        if token != BITRIX_APPLICATION_TOKEN:
            log_warning(f"Application token mismatch: получен {token}")
            return False

    return True


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Битрикс отправляет данные как form-data
        data = request.json if request.is_json else request.form.to_dict()

        # Проверка подлинности
        if not _verify_webhook(data):
            log_warning("Вебхук отклонён: не прошёл проверку подлинности")
            return {"error": "Unauthorized"}, 403

        event = data.get('event')
        
        # Достаем ID задачи из плоских ключей form-data
        task_id = data.get('data[FIELDS_AFTER][ID]') or data.get('data[FIELDS_BEFORE][ID]')
        
        # Фолбэк для JSON
        if not task_id and isinstance(data.get('data'), dict):
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
    """Запускает production WSGI-сервер (waitress) для приёма вебхуков."""
    from waitress import serve
    log_info("🌐 Запуск webhook-сервера на 0.0.0.0:5000 (waitress)")
    serve(app, host="0.0.0.0", port=5000, threads=4)