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
# BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', re.MULTILINE | re.IGNORECASE)
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),([^\r\n]*?)(?=\r?\n|$)', re.MULTILINE | re.IGNORECASE)
# BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),([^\n]*?)(?=\n|$)', re.MULTILINE | re.IGNORECASE)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.MULTILINE | re.IGNORECASE)
PROC_CMD_PATTERN = re.compile(r'^\s*\bproc\s+(.+)', re.MULTILINE | re.IGNORECASE)
INLINE_BTN_PATTERN = re.compile(r'\[\[([^\]|]*?)(?:\|([^\]]*?))?\]\]')
PLN_TEXT_EXTRACTOR = re.compile(r"^(?:pln|p)\s(.*)$")
TEXT_EXTRACTION = re.compile(r"^(pln|p)\s(.*)$", re.MULTILINE)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.MULTILINE | re.DOTALL)

class Loc: 
    def __init__(self, id, name, desc, line):
        self.id = id
        self.name = name
        self.desc = desc
        self.line = line
        self.dup = False
        self.cycle = False
        self.end = False
        self.non_end = False # не может быть концовкой если на нее ссылается proc, local или menu
        # используется для установки флага end, чтобы не пересматривать перед этим все ссылки заново
        self.links = []  # [(target_id, target_name, type, label, is_phantom, is_manu, is_local)]

class UrqParser:
    def __init__(self):
        self.warnings = []
    
    def parse_file(self, file_path): # Без изменений в логике этого метода
        """Парсит URQ файл и возвращает структуру"""        
        content = self._read_file(file_path)
        if not content:
            return []
        content = self._prep_content(content) # Препроцессинг
        locs = self._parse_locations(content) # Добываем метки
        if not locs:
            self._add_warning(f"В файле {os.path.basename(file_path)} не найдено ни одной метки")
        return locs

    def _parse_locations(self, content):
        """Парсит все локации и связи"""
        matches = list(LOC_PATTERN.finditer(content))
        if not matches:
            return []

        locs = []
        # Для отслеживания дубликатов и имен, встреченных первыми
        # name_first_idx хранит индекс первого вхождения имени
        name_first_idx = {} 
        
        # Для эффективного подсчета строк
        cum_nl = 0 # cumulative_newlines
        last_nl_pos = 0 # last_scanned_pos_for_newlines

        for i, m in enumerate(matches): # m - match object
            # Эффективный подсчет номера строки
            seg_nl = content.count('\n', last_nl_pos, m.start())
            cum_nl += seg_nl
            line_num = cum_nl + 1 
            last_nl_pos = m.start()

            name = m.group(1).strip()
            
            # Извлекаем контент локации ОДИН раз
            s_pos = m.end() # start_pos
            e_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content) # end_pos
            l_cont = content[s_pos:e_pos].lstrip() # loc_content
            
            desc = self._extract_description(l_cont)
            loc = Loc(str(i), name, desc, line_num)
            
            # Проверяем дубликаты
            if name in name_first_idx:
                loc.dup = True
                self._add_warning(f"Найден дубликат метки: '{name}' на строке {line_num}")
            else:
                # Запоминаем индекс первого вхождения имени (если имя непустое)
                if name: name_first_idx[name] = i 
            
            locs.append(loc)
            
            # Извлекаем связи и флаги в ЭТОМ ЖЕ цикле
            # Передаем `matches` для корректной проверки границ авто-связей
            self._extract_links_and_flags(loc, l_cont, matches, i) 
        
        self._resolve_target_ids(locs) # Резолвим имена целей в ID

        # Помечаем концевые локации (концовки)
        # s_ids: локации с исходящими НЕ-локальными связями (т.е. являются продолжением, а не концовкой)
        s_ids = {l_obj.id for l_obj in locs if any(not link[6] for link in l_obj.links)} # link[6] is is_local

        for l_obj in locs:
            # Концовка = (нет исходящих НЕ-локальных связей) И 
            #             (не является целью спец. связи типа proc, local, или menu)
            if (l_obj.id not in s_ids and
                    # not l_obj.dup and # не является дубликатом?
                    not l_obj.non_end): # проверка на флаг - не концовка (ставится для целей proc, is_local, is_menu)
                l_obj.end = True


        return locs

    def _extract_links_and_flags(self, loc, l_cont, all_matches, loc_idx):
        """Извлекает связи и устанавливает флаги (адаптировано для all_matches)"""
        # l_cont - loc_content, all_matches - полный список regex matches для проверки границ
        has_end = END_PATTERN.search(l_cont)
        has_goto = GOTO_PATTERN.search(l_cont)
        
        if not has_end and not has_goto:
            next_idx = loc_idx + 1
            if next_idx < len(all_matches):
                loc.links.append((next_idx, "auto", ""))

        pln_found = False
        for m in TEXT_EXTRACTION.finditer(l_cont):
            t_type = m.group(1)
            text = m.group(2).strip()
            if t_type == 'pln':
                pln_found = True
            if (t_type == 'pln' or not pln_found) and text:
                self._extract_inline_buttons(text, loc)

        # DEBUG: показываем что парсим
        print(f"DEBUG: Parsing loc '{loc.name}', content: {repr(l_cont)}")
        
        for m in BTN_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            raw_label = m.group(2)
            # DEBUG: показываем что захватили
            print(f"DEBUG: BTN match - target: {repr(target)}, raw_label: {repr(raw_label)}")
            
            label = raw_label.split('\n')[0].strip() if raw_label else ""
            print(f"DEBUG: Final label after processing: {repr(label)}")
            
            if target: 
                self._add_link_with_cycle_check(loc, target, "btn", label)
            else: 
                self._add_warning(f"Пустая цель btn из '{loc.name}', кнопка '{label}'")

        for m in GOTO_CMD_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            if target: self._add_link_with_cycle_check(loc, target, "goto", "")
            else: self._add_warning(f"Пустая цель goto из '{loc.name}'")

        for m in PROC_CMD_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            if target: self._add_link_with_cycle_check(loc, target, "proc", "")
            else: self._add_warning(f"Пустая цель proc из '{loc.name}'")

    def _resolve_target_ids(self, locs):
        """Резолвим имена целей в ID и помечаем цели спец. связей"""
        # Маппинг имен не-дубликатов на их ID
        n_map = {l.name: l.id for l in locs if not l.dup and l.name} # name_to_id
        
        # Предварительно создаем маппинг имен дубликатов на ID их *первого* вхождения
        # Это избегает многократного сканирования `locs` для каждого такого линка
        d_map = {} # name_to_first_dup_id
        # Отслеживаем имена, для которых уже нашли первый дубликат, чтобы не перезаписывать
        found_dup_names = set() 
        for l_obj in locs: # l_obj - loc object
            if l_obj.dup and l_obj.name and l_obj.name not in found_dup_names:
                d_map[l_obj.name] = l_obj.id
                found_dup_names.add(l_obj.name)
        
        # Создаем маппинг ID -> loc для быстрого поиска
        id_to_loc = {l.id: l for l in locs}
        
        for l in locs: # l - loc object
            res_links = [] # resolved_links
            for link_data in l.links: # link_data - (target, type, label, is_menu, is_local) or (idx, type, label, is_menu, is_local)
                if isinstance(link_data[0], int):  # Автосвязь по индексу
                    idx, l_type, label = link_data[:3] # auto_idx, link_type
                    is_menu = link_data[3] if len(link_data) > 3 else False
                    is_local = link_data[4] if len(link_data) > 4 else False
                    if idx < len(locs):
                        t_loc = locs[idx] # target_loc
                        res_links.append((t_loc.id, t_loc.name, l_type, label, False, is_menu, is_local))
                        
                        # Устанавливаем non_end флаг для целевой локации
                        if l_type == 'proc' or is_local or is_menu:
                            t_loc.non_end = True
                    # else: можно добавить warning для некорректного индекса автосвязи
                    continue
                
                t_name, l_type, label = link_data[:3] # target_name, link_type
                is_menu = link_data[3] if len(link_data) > 3 else False
                is_local = link_data[4] if len(link_data) > 4 else False
                t_id, is_ph = None, True # target_id, is_phantom
                
                if t_name == l.name:  # Самоссылка
                    t_id, is_ph = l.id, False
                elif t_name in n_map:  # Основная локация (не дубликат)
                    t_id, is_ph = n_map[t_name], False
                elif t_name in d_map:  # Ссылка на дубликат (берем ID первого)
                    t_id, is_ph = d_map[t_name], False
                # Если t_id все еще None, то это фантомная ссылка
                
                res_links.append((t_id, t_name, l_type, label, is_ph, is_menu, is_local))
                
                # Устанавливаем non_end флаг для целевой локации (если она существует)
                if t_id is not None and (l_type == 'proc' or is_local or is_menu):
                    target_loc = id_to_loc.get(t_id)
                    if target_loc:
                        target_loc.non_end = True
            
            l.links = res_links
                
    def _prep_content(self, content):
        """Предобработка контента"""
        content = COMMENTS_REMOVAL.sub('', content)        
        content = re.sub(r'\n\s*_', '', content)

        # меняем кавычки "" на '' - исключительно для puml!
        content = re.sub(r'"', '\'', content)
        
        lines = []
        for line_text in content.split('\n'): # line_text - для ясности
            if re.match(r'^\s*if\b', line_text, re.IGNORECASE):
                parts = re.split(r'\b(then|else)\b', line_text, flags=re.IGNORECASE)
                # Используем list comprehension для краткости и эффективности
                # lines.extend(p.strip() for p in parts if p.strip() and p.strip().lower() not in ('then', 'else'))
                lines.extend(p.lstrip() for p in parts if p.lstrip() and p.lstrip().lower() not in ('then', 'else'))
            else:
                lines.append(line_text)
        # Разбиваем по & и очищаем
        return '\n'.join(p.strip() for p in '\n'.join(lines).split('&') if p.strip())

    def _detect_encoding(self, f_path): # f_path - file_path
        """Определяет кодировку файла"""
        if not os.path.exists(f_path):
            self._add_warning(f"Файл не найден: {f_path}")
            return None
        try:
            with open(f_path, 'rb') as f:
                sample = f.read(1024)
            for enc in ['cp1251', 'utf-8']: # cp1251 сначала
                try:
                    sample.decode(enc)
                    return enc
                except UnicodeDecodeError:
                    continue
            self._add_warning(f"Не удалось определить кодировку файла {os.path.basename(f_path)}")
            return None
        except IOError as e:
            self._add_warning(f"Ошибка чтения файла {os.path.basename(f_path)}: {e}")
            return None

    def _read_file(self, f_path): # f_path - file_path
        """Читает файл"""
        enc = self._detect_encoding(f_path) # encoding
        if not enc: return None
        try:
            with open(f_path, 'r', encoding=enc) as f:
                return f.read()
        except IOError as e:
            self._add_warning(f"Ошибка чтения файла {os.path.basename(f_path)}: {e}")
            return None

    def _extract_description(self, l_cont): # l_cont - loc_content
        """Извлекает описание из контента"""
        parts = [self._process_text_with_buttons(m.group(2).strip()).strip() 
                 for m in TEXT_EXTRACTION.finditer(l_cont)] # m - match object
        return self._clean_final_text(' '.join(parts)) if parts else "Нет описания"       
    
    def _process_text_with_buttons(self, text):
        """Обрабатывает текст с инлайн кнопками"""
        return INLINE_BTN_PATTERN.sub(lambda m: m.group(1) if m.group(1) is not None else "", text)

    def _clean_final_text(self, text):
        """Финальная очистка текста"""
        return text.replace('"', "''") if text else "Нет описания"
            
    def _extract_inline_buttons(self, text, loc):
        """Извлекает инлайн кнопки из текста"""
        for m in INLINE_BTN_PATTERN.finditer(text): # m - match object
            desc_text = m.group(1) if m.group(1) is not None else "" # desc_text
            target_text = m.group(2) if m.group(2) is not None else desc_text # target_text

            # Если цель не указана явно (формат [[desc]]), используем desc как target
            # Уже обработано в target_text = m.group(2) if m.group(2) is not None else desc_text
            # desc_stripped = desc_text.strip()
            # target_stripped = target_text.strip() if target_text else desc_stripped
            
            # Упрощено, так как desc_text и target_text уже содержат нужные значения
            self._add_link_with_cycle_check(loc, target_text.strip(), "btn", desc_text.strip())
            
    def _add_link_with_cycle_check(self, loc, target, l_type, label): # l_type - link_type
        """Добавляет связь с проверкой на цикл"""
        # Стрипаем % или ! с начала ссылки и устанавливаем флаги
        # % - меню в кнопке, ! - немедленные действия
        target = target.strip()
        is_menu = is_local = False
        
        if target:
            prefix = target[0]
            if prefix in '%!':
                target = target[1:] # Убираем префикс из имени цели
                is_menu = (prefix == '%')
                is_local = (prefix == '!')

        if target == loc.name: loc.cycle = True
        
        cl_label = "" # clean_label
        if l_type == "btn":
            # Стрипаем только если есть не-пробельные символы
            stripped = label.strip()
            cl_label = self._clean_button_text(stripped) if stripped else label
        
        # (target_name, link_type, label, is_menu, is_local)
        # is_phantom вычисляется позже в _resolve_target_ids
        loc.links.append((target, l_type, cl_label, is_menu, is_local))
                 
    def _clean_button_text(self, text):
        """Очищает текст кнопки"""
        if not text: return ""
        return self._process_text_with_buttons(text).replace('"', "''")#.strip()

    def _add_warning(self, msg): # msg - message
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Parser Warning: {msg}")

    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings