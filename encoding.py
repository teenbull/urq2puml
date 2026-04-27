# encoding_utils.py
# Утилиты для работы с кодировками URQ файлов

import os

ENCODING_BUFFER_SIZE = 1024

def detect_encoding(f_path, warnings_callback=None):
    """
    Определяет кодировку файла с поддержкой UTF-8 BOM
    
    Args:
        f_path: путь к файлу
        warnings_callback: функция для добавления предупреждений (опционально)
    
    Returns:
        str: название кодировки или None при ошибке
    """
    if not os.path.exists(f_path):
        if warnings_callback:
            warnings_callback(f"Файл не найден: {f_path}")
        return None
        
    try:
        with open(f_path, 'rb') as f:
            # sample = f.read(ENCODING_BUFFER_SIZE)
            sample = f.read() # читаем файл целиком, не жалеем
            
        if warnings_callback:
            warnings_callback(f"Обнаружен файл {os.path.basename(f_path)}")
            
        # Проверяем UTF-8 с BOM
        if sample.startswith(b'\xef\xbb\xbf'):
            if warnings_callback:
                warnings_callback(f"Найден UTF-8 BOM в файле {os.path.basename(f_path)}")
            return 'utf-8-sig'
            
        # Проверяем остальные кодировки
        for enc in ['utf-8','cp1251']:
            try:
                decoded = sample.decode(enc)
                if warnings_callback:
                    warnings_callback(f"Успешно декодирован файл {os.path.basename(f_path)} как {enc}")
                return enc
            except UnicodeDecodeError as e:
                if warnings_callback:
                    warnings_callback(f"Не удалось декодировать файл {os.path.basename(f_path)} как {enc}: {e}")
                continue
                
        if warnings_callback:
            warnings_callback(f"Не удалось определить кодировку файла {os.path.basename(f_path)} - попробованы: cp1251, utf-8")
            # Показываем первые несколько байт для диагностики
            hex_sample = ' '.join(f'{b:02x}' for b in sample[:16])
            warnings_callback(f"Первые 16 байт файла: {hex_sample}")
        return None
        
    except IOError as e:
        if warnings_callback:
            warnings_callback(f"Ошибка чтения файла {os.path.basename(f_path)}: {e}")
        return None