class ISURAuthError(Exception):
    """Ошибка авторизации в ИСУР."""
    pass

class ISURAPIError(Exception):
    """Ошибка при запросе к ИСУР."""
    pass

class BitrixAPIError(Exception):
    """Ошибка при запросе к Битрикс24."""
    pass

class TaskCreationError(Exception):
    """Ошибка создания задачи."""
    pass