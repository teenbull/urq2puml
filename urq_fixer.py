# -*- coding: utf-8 -*-
# urq_fixer.py
# URQ Fixer - перемещает локации-сиротки в конец файла

import os
import re

# Комментировать строки сироток
COMMENT_ORPHANS = True
COMMENT_DUPLICATES = True

# Относительные импорты для Sublime Text
try:
    from .urq_parser import UrqParser, LOC_PATTERN
except ImportError:
    from urq_parser import UrqParser, LOC_PATTERN

class UrqFixer:
    def __init__(self):
        self.warnings = []
    
    def fix(self, content, encoding='cp1251'):
        """Основная функция - исправляет все проблемы"""
        if not content or not content.strip():
            self._add_warning("Пустой контент для исправления")
            return content, None
            
        # Парсим файл через UrqParser
        parser = UrqParser()
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qst', delete=False, encoding=encoding) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            locs = parser.parse_file(tmp_path)
            self.warnings.extend(parser.get_warnings())
            
            if not locs:
                self._add_warning("Не найдено локаций для обработки")
                return content, None
                
            return self._move_problem_locs(content, locs)
            
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

    def _move_problem_locs(self, content, locs):
        """Перемещает проблемные локации в конец"""
        orphans = [l for l in locs if l.orphan]
        duplicates = [l for l in locs if l.dup]
        
        if not orphans and not duplicates:
            return content, None
        
        # Разбиваем контент на строки для работы по номерам строк
        lines = content.split('\n')
        
        # Собираем диапазоны строк для удаления
        ranges_to_remove = []
        orphan_content = ""
        duplicate_content = ""
        
        # Сортируем все локации по номеру строки для правильного определения границ
        sorted_locs = sorted(locs, key=lambda x: x.line)
        
        for i, loc in enumerate(sorted_locs):
            if not (loc.orphan or loc.dup):
                continue
                
            start_line = loc.line - 1  # Переводим в 0-based индексацию
            
            # Находим конец локации: начало следующей локации или конец файла
            if i + 1 < len(sorted_locs):
                end_line = sorted_locs[i + 1].line - 1
            else:
                end_line = len(lines)
            
            # Извлекаем содержимое локации
            loc_lines = lines[start_line:end_line]
            loc_content = '\n'.join(loc_lines)
            
            if loc_content.strip():  # Только если есть контент
                ranges_to_remove.append((start_line, end_line))
                
                if loc.orphan:
                    orphan_content += loc_content + '\n'
                if loc.dup:
                    duplicate_content += loc_content + '\n'
        
        if not ranges_to_remove:
            return content, None
        
        # Удаляем проблемные локации (в обратном порядке по номерам строк)
        ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
        for start_line, end_line in ranges_to_remove:
            del lines[start_line:end_line]
        
        # Формируем новый контент
        new_content = '\n'.join(lines).rstrip()
        scroll_line = len(lines) + 1  # Строка где начнутся комментарии
        final_block = ""
        
        if orphan_content:
            sep = "\n\n; " + "-" * 50 + "\n; Потерянные локации:\n; " + "-" * 50 + "\n\n"
            processed_content = self._comment_content(orphan_content.rstrip(), COMMENT_ORPHANS)
            final_block += sep + processed_content
            self._add_warning(f"Перемещено {len(orphans)} локаций-сироток")
        
        if duplicate_content:
            sep = "\n\n; " + "-" * 50 + "\n; Дубликаты:\n; " + "-" * 50 + "\n\n"
            processed_content = self._comment_content(duplicate_content.rstrip(), COMMENT_DUPLICATES)
            final_block += sep + processed_content
            self._add_warning(f"Перемещено {len(duplicates)} дубликатов")
        
        return new_content + final_block, scroll_line

           
    def fix_orphans(self, content, encoding='cp1251'):
        """Исправляет только сиротки"""
        locs = self._parse_content(content, encoding)
        if not locs:
            return content, []
        
        orphans = [l for l in locs if l.orphan]
        return self._process_locations(content, orphans, "Потерянные локации:", COMMENT_ORPHANS)
    
    def fix_duplicates(self, content, encoding='cp1251'):
        """Исправляет только дубликаты"""
        locs = self._parse_content(content, encoding)
        if not locs:
            return content, []
        
        duplicates = [l for l in locs if l.dup]
        return self._process_locations(content, duplicates, "Дубликаты:", COMMENT_DUPLICATES)
    
    def _parse_content(self, content, encoding):
        """Парсит контент и возвращает локации"""
        parser = UrqParser()
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.qst', delete=False, encoding=encoding) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            locs = parser.parse_file(tmp_path)
            self.warnings.extend(parser.get_warnings())
            return locs
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    def _process_locations(self, content, problem_locs, title, should_comment):
        """Обрабатывает конкретный тип проблемных локаций"""
        if not problem_locs:
            return content, []
        
        matches = list(LOC_PATTERN.finditer(content))
        ranges_to_remove = []
        loc_content = ""
        
        for loc in problem_locs:
            loc_idx = int(loc.id)
            if loc_idx >= len(matches):
                continue
                
            start_pos = matches[loc_idx].start()
            end_pos = matches[loc_idx + 1].start() if loc_idx + 1 < len(matches) else len(content)
            
            loc_content += content[start_pos:end_pos]
            ranges_to_remove.append((start_pos, end_pos))
        
        # Удаляем локации
        ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
        new_content = content
        for start_pos, end_pos in ranges_to_remove:
            new_content = new_content[:start_pos] + new_content[end_pos:]
        
        # Добавляем в конец
        new_content = new_content.rstrip()
        sep = f"\n\n; " + "-" * 50 + f"\n; {title}\n; " + "-" * 50 + "\n\n"
        processed_content = self._comment_content(loc_content, should_comment)
        
        scroll_markers = [(f"; {title}", 1)]
        self._add_warning(f"Перемещено {len(problem_locs)} локаций: {title.lower()}")
        
        return new_content + sep + processed_content, scroll_markers
    
    def _comment_content(self, content, should_comment):
        """Комментирует контент если нужно"""
        if not should_comment or not content:
            return content
        
        lines = content.split('\n')
        commented_lines = []
        for line in lines:
            if line.strip() and not line.strip().startswith(';'):
                commented_lines.append(f"; {line}")
            else:
                commented_lines.append(line)
        return '\n'.join(commented_lines)
    
    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Fixer Warning: {message}")
    
    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings