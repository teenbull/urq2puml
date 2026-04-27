# -*- coding: utf-8 -*-
# urq_fixer.py
# URQ Fixer - перемещает локации-сиротки в конец файла

import os
import re

# Комментировать строки сироток
COMMENT_ORPHANS = True
COMMENT_DUPLICATES = True
MOVE_DUPLICATES = False

# Относительные импорты для Sublime Text
try:
    from .urq_parser import UrqParser, LOC_PATTERN, remove_urq_comments
except ImportError:
    from urq_parser import UrqParser, LOC_PATTERN, remove_urq_comments

class UrqFixer:
    def __init__(self):
        self.warnings = [ ]
    
    def fix(self, content, encoding='cp1251'):
        """Основная функция - исправляет все проблемы"""
        if not content or not content.strip():
            self._add_warning("Пустой контент для исправления")
            return content, None
            
        parser = UrqParser()
        # Используем parse_string напрямую без создания временных файлов на диске.
        # Это избавляет от проблем с парсингом %include, из-за которых могли сдвигаться
        # номера строк в оригинальном коде, а также значительно ускоряет работу.
        locs = parser.parse_string(content)
        self.warnings.extend(parser.get_warnings())
        
        if not locs:
            self._add_warning("Не найдено локаций для обработки")
            return content, None
            
        return self._move_problem_locs(content, locs)

    def _move_problem_locs(self, content, locs):
        """Перемещает проблемные локации в конец"""
        orphans =[l for l in locs if l.orphan]
        duplicates =[l for l in locs if l.dup]
        
        if not orphans and not duplicates:
            return content, None
        
        # Сплитим по \n, чтобы индексы строк массива точно совпали с loc.line
        orig_lines = content.split('\n')
        
        # Создаем очищенную от комментариев версию кода. 
        # Она нужна только как трафарет, чтобы понимать, где реально заканчивается код локации.
        clean_content = remove_urq_comments(content)
        clean_lines = clean_content.split('\n')
        
        ranges_to_remove = [ ]
        orphan_content = ""
        duplicate_content = ""
        
        # Обязательно сортируем по номерам строк, чтобы идти по файлу сверху вниз
        sorted_locs = sorted(locs, key=lambda x: x.line)
        
        for i, loc in enumerate(sorted_locs):
            if not (loc.orphan or (loc.dup and MOVE_DUPLICATES)):
                continue
                
            start_line = loc.line - 1
            # Граница для поиска - начало следующей локации (или конец файла)
            next_line = sorted_locs[i + 1].line - 1 if i + 1 < len(sorted_locs) else len(orig_lines)
            
            # Идем снизу вверх от следующей метки и ищем последнюю значащую строку.
            # Благодаря clean_lines мы проигнорируем комментарии и вырежем ровно до 'end' (или похожего),
            # оставляя блочные комментарии лежать на своем старом месте.
            end_line = next_line
            while end_line > start_line:
                if end_line - 1 < len(clean_lines) and clean_lines[end_line - 1].strip():
                    break
                end_line -= 1
                
            # Защита от пустых/полностью закомментированных локаций - забираем хотя бы саму метку
            if end_line == start_line:
                end_line = start_line + 1
                
            loc_lines = orig_lines[start_line:end_line]
            loc_content = '\n'.join(loc_lines)
            
            if loc_content.strip():
                ranges_to_remove.append((start_line, end_line))
                if loc.orphan: orphan_content += loc_content + '\n'
                if loc.dup and MOVE_DUPLICATES: duplicate_content += loc_content + '\n'
        
        # Обработка дубликатов без перемещения (только комментирование in-place)
        if duplicates and not MOVE_DUPLICATES:
            for loc in duplicates:
                start_line = loc.line - 1
                if start_line < len(orig_lines) and not orig_lines[start_line].strip().startswith(';'):
                    orig_lines[start_line] = f";{orig_lines[start_line]}"
            self._add_warning(f"Закомментировано {len(duplicates)} дубликатов")
        
        if not ranges_to_remove and not (duplicates and not MOVE_DUPLICATES):
            return content, None
        
        # Удаляем проблемные блоки из оригинального списка строк.
        # Обязательно с конца (reverse=True), чтобы при удалении нижних строк 
        # индексы верхних не смещались!
        ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
        for start_line, end_line in ranges_to_remove:
            del orig_lines[start_line:end_line]
        
        new_content = '\n'.join(orig_lines).rstrip()
        scroll_line = len(orig_lines) + 1
        final_block = ""
        
        # Добавляем вырезанные проблемные локации в самый конец файла
        if orphan_content:
            sep = "\n\n; " + "-" * 50 + "\n; Потерянные локации:\n; " + "-" * 50 + "\n\n"
            final_block += sep + self._comment_content(orphan_content.rstrip(), COMMENT_ORPHANS)
            self._add_warning(f"Перемещено {len(orphans)} локаций-сироток")
        
        if duplicate_content:
            sep = "\n\n; " + "-" * 50 + "\n; Дубликаты:\n; " + "-" * 50 + "\n\n"
            final_block += sep + self._comment_content(duplicate_content.rstrip(), COMMENT_DUPLICATES)
            self._add_warning(f"Перемещено {len([d for d in duplicates if MOVE_DUPLICATES])} дубликатов")
        
        return new_content + final_block, scroll_line

           
    def fix_orphans(self, content, encoding='cp1251'):
        """Исправляет только сиротки"""
        locs = self._parse_content(content, encoding)
        if not locs:
            return content, None
        
        orphans =[l for l in locs if l.orphan]
        # Передаем полный список locs, чтобы функция знала общую структуру файла 
        # и могла правильно высчитать, где начинается следующая локация.
        return self._process_locations(content, orphans, locs, "Потерянные локации:", COMMENT_ORPHANS)
    
    def fix_duplicates(self, content, encoding='cp1251'):
        """Исправляет только дубликаты"""
        locs = self._parse_content(content, encoding)
        if not locs:
            return content, None
        
        duplicates =[l for l in locs if l.dup]
        return self._process_locations(content, duplicates, locs, "Дубликаты:", COMMENT_DUPLICATES)
    
    def _parse_content(self, content, encoding='cp1251'):
        """Парсит контент и возвращает локации"""
        parser = UrqParser()
        # Читаем текст прямо из памяти, без создания временных файлов
        locs = parser.parse_string(content)
        self.warnings.extend(parser.get_warnings())
        return locs
    
    def _process_locations(self, content, problem_locs, all_locs, title, should_comment):
        """Обрабатывает конкретный тип проблемных локаций с учетом реальных номеров строк"""
        if not problem_locs:
            return content, None
        
        orig_lines = content.split('\n')
        clean_content = remove_urq_comments(content)
        clean_lines = clean_content.split('\n')
        
        ranges_to_remove = [ ]
        loc_content_list =[ ]
        
        sorted_locs = sorted(all_locs, key=lambda x: x.line)
        
        for loc in problem_locs:
            try:
                idx = sorted_locs.index(loc)
            except ValueError:
                continue
                
            start_line = loc.line - 1
            next_line = sorted_locs[idx + 1].line - 1 if idx + 1 < len(sorted_locs) else len(orig_lines)
            
            # Ищем истинный конец локации, игнорируя хвосты с комментариями
            end_line = next_line
            while end_line > start_line:
                if end_line - 1 < len(clean_lines) and clean_lines[end_line - 1].strip():
                    break
                end_line -= 1
                
            if end_line == start_line:
                end_line = start_line + 1
                
            loc_lines = orig_lines[start_line:end_line]
            current_loc_content = '\n'.join(loc_lines)
            
            if current_loc_content.strip():
                loc_content_list.append(current_loc_content)
                ranges_to_remove.append((start_line, end_line))
        
        # Удаляем локации снизу вверх, чтобы не сбить индексы строк списка orig_lines
        ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
        for start_line, end_line in ranges_to_remove:
            del orig_lines[start_line:end_line]
        
        new_content = '\n'.join(orig_lines).rstrip()
        sep = f"\n\n; " + "-" * 50 + f"\n; {title}\n; " + "-" * 50 + "\n\n"
        
        combined_loc_content = '\n\n'.join(loc_content_list)
        processed_content = self._comment_content(combined_loc_content.rstrip(), should_comment)
        
        scroll_line = len(orig_lines) + 1
        self._add_warning(f"Перемещено {len(problem_locs)} локаций: {title.lower()}")
        
        # Добавляем собранные проблемные локации в самый конец файла
        return new_content + sep + processed_content, scroll_line
    
    def _comment_content(self, content, should_comment):
        """Комментирует контент если нужно"""
        if not should_comment or not content:
            return content
        
        lines = content.split('\n')
        commented_lines = [ ]
        for line in lines:
            if line.strip() and not line.strip().startswith(';'):
                commented_lines.append(f";{line}")
            else:
                commented_lines.append(line)
        return '\n'.join(commented_lines)
    
    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Fixer Warning: {message}")
    
    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings