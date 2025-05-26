import re
from typing import Optional
import html

def clean_text(text: str, max_length: Optional[int] = None) -> str:
    """
    Очистка текста от лишних символов и форматирования
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина текста (если нужно обрезать)
    
    Returns:
        Очищенный текст
    """
    # Удаление HTML тегов
    text = re.sub(r'<[^>]+>', '', text)
    
    # Замена HTML entities
    text = html.unescape(text)
    
    # Удаление лишних переносов строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Удаление лишних пробелов
    text = re.sub(r'[^\S\n]+', ' ', text).strip()
    
    # Обрезка до максимальной длины если нужно
    if max_length and len(text) > max_length:
        text = text[:max_length-3] + '...'
    
    return text

def split_long_text(text: str, max_chunk_size: int = 4000) -> list[str]:
    """
    Разделение длинного текста на части по максимальному размеру
    
    Args:
        text: Исходный текст
        max_chunk_size: Максимальный размер части текста
    
    Returns:
        Список частей текста
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    # Попробуем разделить по абзацам
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
        
        if current_chunk:
            current_chunk += "\n\n"
        current_chunk += paragraph
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def format_script_for_subtitles(script: str) -> str:
    """
    Форматирование сценария для субтитров
    
    Args:
        script: Исходный сценарий
    
    Returns:
        Текст, оптимизированный для отображения в субтитрах
    """
    # Удаление маркеров сцен (если есть)
    script = re.sub(r'\[.*?\]', '', script)
    
    # Разделение на реплики
    lines = script.split('\n')
    processed_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Укорачивание слишком длинных строк
        if len(line) > 50:
            words = line.split()
            new_line = ""
            for word in words:
                if len(new_line) + len(word) + 1 > 50:
                    processed_lines.append(new_line)
                    new_line = word
                else:
                    if new_line:
                        new_line += " "
                    new_line += word
            if new_line:
                processed_lines.append(new_line)
        else:
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)

def count_approximate_video_duration(text: str) -> int:
    """
    Подсчет примерной длительности видео в секундах на основе текста
    
    Args:
        text: Текст сценария
    
    Returns:
        Примерная длительность в секундах
    """
    # Средняя скорость речи ~150 слов в минуту (2.5 слова/сек)
    word_count = len(text.split())
    duration = word_count / 2.5  # в секундах
    
    # Минимальная и максимальная длительность
    duration = max(15, min(90, duration))
    
    return int(duration)