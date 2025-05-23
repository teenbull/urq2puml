# -*- coding: utf-8 -*-
# URQ Parser - извлекает структуру из URQ файлов
import re
import os
print("Package name:", os.path.basename(os.path.dirname(__file__)))
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

# Регулярка для инлайн кнопок в pln/p тексте
INLINE_BTN_PATTERN = re.compile(r'\[\[([^\]|]*?)(?:\|([^\]]*?))?\]\]')
# И для текста в pln/p
PLN_TEXT_EXTRACTOR = re.compile(r"^(?:pln|p)\s(.*)$")

class UrqParser:
    def __init__(self):
        self.warnings = []
    
    def parse_file(self, file_path):
        """Парсит URQ файл и возвращает структуру"""
        encoding = self._detect_encoding(file_path)
        if not encoding:
            return None
            
        content = self._read_file_with_encoding(file_path, encoding)
        if not content:
            return None

        content = self._prep_content(content)
        matches = list(LOC_PATTERN.finditer(content))
        
        if not matches:
            self._add_warning("В файле {} не найдено ни одной метки".format(os.path.basename(file_path)))
            return None

        return self._parse_locations(content, matches)

    def _parse_locations(self, content, matches):
        """Парсит все локации и связи"""
        locs = {}  # {name: [desc, id]}
        all_locs = {}  # {id: [name, desc, line_num, is_duplicate]}
        btn_links = []
        auto_links = []
        goto_links = []
        proc_links = []
        cycle_ids = set()
        loc_counter = 0
        name_counts = {}
        
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            line_number = content[:match.start()].count('\n') + 1
            loc_content = content[start_pos:end_pos].lstrip()
            desc = self._extract_description(loc_content)
            
            loc_id = str(loc_counter)
            is_duplicate = name in name_counts
            
            if not is_duplicate:
                locs[name] = [desc, loc_id]
                name_counts[name] = 0
            else:
                name_counts[name] += 1
                self._add_warning("Найден дубликат метки: '{}' на строке {}".format(name, line_number))
            
            all_locs[loc_id] = [name, desc, line_number, is_duplicate]
            
            next_loc_id = str(loc_counter + 1) if i + 1 < len(matches) else None
            self._extract_links(name, loc_content, btn_links, auto_links, goto_links, proc_links, loc_id, next_loc_id, cycle_ids)
            loc_counter += 1

        return locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids

    def _prep_content(self, content):
        """Предобработка контента"""
        # Удаляем комментарии
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r';[^\n]*', '', content)
        
        # Объединяем строки
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
        
        content = '\n'.join(lines)
        
        # Разбиваем по &
        parts = content.split('&')
        content = '\n'.join(part.strip() for part in parts if part.strip())
        
        return content

    def _detect_encoding(self, file_path):
        """Определяет кодировку файла"""
        if not os.path.exists(file_path):
            self._add_warning("Файл не найден: {}".format(file_path))
            return None
        
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(1024)
            
            # UTF-8 сначала
            try:
                sample.decode('utf-8')
                return 'utf-8'
            except UnicodeDecodeError:
                pass
            
            # Потом CP1251
            try:
                sample.decode('cp1251')
                return 'cp1251'
            except UnicodeDecodeError:
                pass
            
            self._add_warning("Не удалось определить кодировку файла {}".format(os.path.basename(file_path)))
            return None
            
        except IOError as e:
            self._add_warning("Ошибка чтения файла {}: {}".format(os.path.basename(file_path), e))
            return None

    def _read_file_with_encoding(self, file_path, encoding):
        """Читает файл с кодировкой"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except IOError as e:
            self._add_warning("Ошибка чтения файла {}: {}".format(os.path.basename(file_path), e))
            return None

    def _extract_description(self, content: str) -> str:
        parts = []
        for raw_line in content.splitlines():
           line = raw_line.strip() 
           
           match = PLN_TEXT_EXTRACTOR.match(line)
           if match:
               # group(1) contains the text after "pln " or "p "
               extracted_text = match.group(1).strip()
               
               processed_text = self._process_text_with_buttons(extracted_text).strip()
               if processed_text: # If not empty after all processing
                   parts.append(processed_text)
           # If no match, the line is not a pln/p line we care about, so it's skipped.
           
        if not parts:
           return "Нет описания"
           
        return self._clean_final_text(' '.join(parts))
       
    def _process_text_with_buttons(self, text):
        """Обрабатывает текст с инлайн кнопками, заменяя их на описания"""
        def replace_button(match):
            desc = match.group(1) if match.group(1) is not None else ""
            return desc  # Возвращаем описание кнопки как есть
        
        return INLINE_BTN_PATTERN.sub(replace_button, text)

    def _clean_final_text(self, text):
        """Финальная очистка текста"""
        if not text:
            return "Нет описания"
        
        # Удаляем лишние пробелы и переносы
        # text = re.sub(r'\s+', ' ', text).strip()
        
        # Заменяем кавычки для PlantUML
        text = text.replace('"', "''")
        
        return text

    def _extract_links(self, loc_name, content, btn_links, auto_links, goto_links, proc_links, loc_id, next_loc_id, cycle_ids):
        """Извлекает связи из локации"""
        has_end = END_PATTERN.search(content)
        has_goto = GOTO_PATTERN.search(content)
        has_proc = PROC_PATTERN.search(content)
        
        # Автосвязь (нет end, нет goto, но есть следующая локация)
        if not has_end and not has_goto and next_loc_id is not None:
            auto_links.append((loc_id, next_loc_id, "auto"))

        # Собираем все текстовые строки для обработки инлайн кнопок (БЕЗ дублирования)
        processed_texts = set()
        
        # Сначала pln строки
        for pln_match in PLN_PATTERN.finditer(content):
            text = pln_match.group(1).strip()
            if text and text not in processed_texts:
                processed_texts.add(text)
                self._extract_inline_buttons(text, loc_name, loc_id, btn_links, cycle_ids)

        # Если нет pln строк, обрабатываем p строки
        if not any(PLN_PATTERN.finditer(content)):
            for p_match in P_PATTERN.finditer(content):
                text = p_match.group(1).strip()
                if text and text not in processed_texts:
                    processed_texts.add(text)
                    self._extract_inline_buttons(text, loc_name, loc_id, btn_links, cycle_ids)

        # btn
        for match in BTN_PATTERN.finditer(content):
            target = match.group(1).strip()  
            label = match.group(2)  # Don't strip to preserve distinction
            if target:
                if target == loc_name:
                    cycle_ids.add(loc_id)
                # Only truly empty (no characters) should be blue
                if label == "":
                    clean_label = ""  # Blue arrow
                elif label.strip() == "":
                    clean_label = " "  # Normal arrow with space caption  
                else:
                    clean_label = self._clean_button_text(label.strip())
                btn_links.append((loc_id, target, clean_label))
            else:
                self._add_warning("Пустая цель btn из '{}', кнопка '{}'".format(loc_name, label))

        # goto
        for match in GOTO_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                if target == loc_name:
                    cycle_ids.add(loc_id)
                goto_links.append((loc_id, target, "goto"))
            else:
                self._add_warning("Пустая цель goto из '{}'".format(loc_name))

        # proc
        for match in PROC_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                if target == loc_name:
                    cycle_ids.add(loc_id)
                proc_links.append((loc_id, target, "proc"))
            else:
                self._add_warning("Пустая цель proc из '{}'".format(loc_name))

    def _extract_inline_buttons(self, text, loc_name, loc_id, btn_links, cycle_ids):
        """Извлекает инлайн кнопки из текста pln/p"""
        for match in INLINE_BTN_PATTERN.finditer(text):
            desc = match.group(1) if match.group(1) is not None else ""
            target = match.group(2) if match.group(2) is not None else desc
                
            # Strip desc for empty button detection
            desc_stripped = desc.strip() if desc else ""
            
            # Preserve empty desc as empty string for blue arrow
            if desc_stripped == "":
                safe_desc = ""
            else:
                safe_desc = self._clean_button_text(desc_stripped)
            
            # Strip target for processing, but keep original logic
            target_stripped = target.strip() if target else ""
            
            # If no explicit target was provided, use desc as target
            if match.group(2) is None:
                target_stripped = desc_stripped
                
            # Check for self-reference only if target is not empty
            if target_stripped and target_stripped == loc_name:
                cycle_ids.add(loc_id)
            
            btn_links.append((loc_id, target_stripped, safe_desc))
            
    def _clean_button_text(self, text):
        """Очищает текст кнопки"""
        if not text:
            return ""
        
        # Удаляем инлайн кнопки из текста кнопки (рекурсивно)
        text = self._process_text_with_buttons(text)
        
        # Заменяем кавычки
        text = text.replace('"', "''").strip()
        
        return text

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append("URQ Parser Warning: {}".format(message))

    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings