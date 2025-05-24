# -*- coding: utf-8 -*-
# URQ Parser - извлекает структуру из URQ файлов
import re
import os

# Регулярки для парсинга URQ
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
END_PATTERN = re.compile(r'^\s*\bend\b', re.MULTILINE | re.IGNORECASE)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.MULTILINE | re.IGNORECASE)
PROC_PATTERN = re.compile(r'^\s*\bproc\b', re.MULTILINE | re.IGNORECASE)
PLN_PATTERN = re.compile(r'^\s*pln\s*(.*)$', re.MULTILINE)
P_PATTERN = re.compile(r'^\s*p\s*(.*)$', re.MULTILINE)
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', re.MULTILINE | re.IGNORECASE)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.MULTILINE | re.IGNORECASE)
PROC_CMD_PATTERN = re.compile(r'^\s*\bproc\s+(.+)', re.MULTILINE | re.IGNORECASE)
INLINE_BTN_PATTERN = re.compile(r'\[\[([^\]|]*?)(?:\|([^\]]*?))?\]\]')
PLN_TEXT_EXTRACTOR = re.compile(r"^(?:pln|p)\s(.*)$")

TEXT_EXTRACTION = re.compile(r"^(pln|p)\s(.*)$", re.MULTILINE)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.MULTILINE)

class Loc:
    def __init__(self, id, name, desc, line):
        self.id = id
        self.name = name
        self.desc = desc
        self.line = line
        self.dup = False
        self.cycle = False
        self.end = False
        self.links = []  # [(target, type, label, is_phantom)]

class UrqParser:
    def __init__(self):
        self.warnings = []
    
    def parse_file(self, file_path):
        """Парсит URQ файл и возвращает структуру"""
        encoding = self._detect_encoding(file_path)
        if not encoding:
            return [], {}
            
        content = self._read_file_with_encoding(file_path, encoding)
        if not content:
            return [], {}

        content = self._prep_content(content)
        matches = list(LOC_PATTERN.finditer(content))
        
        if not matches:
            self._add_warning(f"В файле {os.path.basename(file_path)} не найдено ни одной метки")
            return [], {}

        return self._parse_locations(content, matches)

    def _parse_locations(self, content, matches):
        """Парсит все локации и связи"""
        locs = []
        name_to_id = {}
        name_counts = {}
        
        # Создаем локации
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            line_num = content[:match.start()].count('\n') + 1
            loc_content = content[start_pos:end_pos].lstrip()
            desc = self._extract_description(loc_content)
            
            loc = Loc(str(i), name, desc, line_num)
            
            # Проверяем дубликаты
            if name in name_counts:
                loc.dup = True
                name_counts[name] += 1
                self._add_warning(f"Найден дубликат метки: '{name}' на строке {line_num}")
            else:
                name_counts[name] = 0
                name_to_id[name] = loc.id
            
            locs.append(loc)
        
        # Извлекаем связи и флаги
        for i, loc in enumerate(locs):
            start_pos = matches[i].end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            loc_content = content[start_pos:end_pos].lstrip()
            
            self._extract_links_and_flags(loc, loc_content, locs, i, name_to_id)
        
        # Помечаем концевые локации
        source_ids = {loc.id for loc in locs if loc.links}
        for loc in locs:
            if loc.id not in source_ids and not loc.dup:
                loc.end = True
        
        return locs, name_to_id

    def _prep_content(self, content):
        """Предобработка контента"""
        # Комменты и переносы
        content = COMMENTS_REMOVAL.sub('', content)        
        # content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # content = re.sub(r';[^\n]*', '', content)
        content = re.sub(r'\n\s*_', '', content)
        
        # Разбиваем if/then/else
        lines = []
        for line in content.split('\n'):
            if re.match(r'^\s*if\b', line, re.IGNORECASE):
                parts = re.split(r'\b(then|else)\b', line, flags=re.IGNORECASE)
                for part in parts:
                    part = part.strip()
                    if part and part.lower() not in ('then', 'else'):
                        lines.append(part)
            else:
                lines.append(line)
        
        # Разбиваем по &
        parts = '\n'.join(lines).split('&')
        return '\n'.join(part.strip() for part in parts if part.strip())

    def _detect_encoding(self, file_path):
        """Определяет кодировку файла"""
        if not os.path.exists(file_path):
            self._add_warning(f"Файл не найден: {file_path}")
            return None
        
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(1024)
            
            # UTF-8 сначала
            for enc in ['utf-8', 'cp1251']:
                try:
                    sample.decode(enc)
                    return enc
                except UnicodeDecodeError:
                    continue
            
            self._add_warning(f"Не удалось определить кодировку файла {os.path.basename(file_path)}")
            return None
            
        except IOError as e:
            self._add_warning(f"Ошибка чтения файла {os.path.basename(file_path)}: {e}")
            return None

    def _read_file_with_encoding(self, file_path, encoding):
        """Читает файл с кодировкой"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except IOError as e:
            self._add_warning(f"Ошибка чтения файла {os.path.basename(file_path)}: {e}")
            return None

    def _extract_description(self, content):
        """Извлекает описание из контента"""
        parts = [self._process_text_with_buttons(match.group(2).strip()).strip() 
                for match in TEXT_EXTRACTION.finditer(content)]
        
        return self._clean_final_text(' '.join(parts)) if parts else "Нет описания"       
    
    def _process_text_with_buttons(self, text):
        """Обрабатывает текст с инлайн кнопками"""
        return INLINE_BTN_PATTERN.sub(lambda m: m.group(1) if m.group(1) is not None else "", text)

    def _clean_final_text(self, text):
        """Финальная очистка текста"""
        return text.replace('"', "''") if text else "Нет описания"

    def _extract_links_and_flags(self, loc, content, locs, loc_idx, name_to_id):
        """Извлекает связи и устанавливает флаги"""
        has_end = END_PATTERN.search(content)
        has_goto = GOTO_PATTERN.search(content)
        
        # Автосвязь - ищем следующую локацию в физическом порядке
        if not has_end and not has_goto:
            next_idx = loc_idx + 1
            if next_idx < len(locs):
                loc.links.append((locs[next_idx].id, "auto", "", False))

        # Собираем уникальные тексты для инлайн кнопок
        processed_texts = set()
        
        # Обрабатываем все pln/p тексты за один проход
        pln_found = False
        for match in TEXT_EXTRACTION.finditer(content):
            text_type = match.group(1)  # 'pln' или 'p'
            text = match.group(2).strip()
            
            if text_type == 'pln':
                pln_found = True
            
            # Обрабатываем pln всегда, p только если нет pln
            if (text_type == 'pln' or not pln_found) and text and text not in processed_texts:
                processed_texts.add(text)
                self._extract_inline_buttons(text, loc, name_to_id)

        # btn команды
        for match in BTN_PATTERN.finditer(content):
            target = match.group(1).strip()
            label = match.group(2)
            if target:
                self._add_link_with_cycle_check(loc, target, "btn", label, name_to_id)
            else:
                self._add_warning(f"Пустая цель btn из '{loc.name}', кнопка '{label}'")

        # goto команды
        for match in GOTO_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                self._add_link_with_cycle_check(loc, target, "goto", "", name_to_id)
            else:
                self._add_warning(f"Пустая цель goto из '{loc.name}'")

        # proc команды
        for match in PROC_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                self._add_link_with_cycle_check(loc, target, "proc", "", name_to_id)
            else:
                self._add_warning(f"Пустая цель proc из '{loc.name}'")
            
    def _extract_inline_buttons(self, text, loc, name_to_id):
        """Извлекает инлайн кнопки из текста"""
        for match in INLINE_BTN_PATTERN.finditer(text):
            desc = match.group(1) if match.group(1) is not None else ""
            target = match.group(2) if match.group(2) is not None else desc
                
            desc_stripped = desc.strip() if desc else ""
            target_stripped = target.strip() if target else ""
            
            # Если цель не указана явно, используем описание
            if match.group(2) is None:
                target_stripped = desc_stripped
            
            self._add_link_with_cycle_check(loc, target_stripped, "btn", desc_stripped, name_to_id)
            
    def _add_link_with_cycle_check(self, loc, target, link_type, label, name_to_id):
        """Добавляет связь с проверкой на цикл"""
        # Проверяем самоссылку
        if target == loc.name:
            loc.cycle = True
        
        # Очищаем лейбл для btn
        if link_type == "btn":
            if label == "":
                clean_label = ""
            elif label.strip() == "":
                clean_label = " "
            else:
                clean_label = self._clean_button_text(label.strip())
        else:
            clean_label = ""
        
        # Проверяем существование цели и помечаем как phantom
        target_exists = target in name_to_id or target == loc.name
        is_phantom = not target_exists
        
        loc.links.append((target, link_type, clean_label, is_phantom))
            
    def _clean_button_text(self, text):
        """Очищает текст кнопки"""
        if not text:
            return ""
        
        # Удаляем инлайн кнопки и заменяем кавычки
        return self._process_text_with_buttons(text).replace('"', "''").strip()

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Parser Warning: {message}")

    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings