# -*- coding: utf-8 -*-
# urq_parser.py
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

VAR_PATTERN = re.compile(r'^\s*([^=\n]+?)\s*=', re.MULTILINE)
INV_PATTERN = re.compile(r'^\s*inv\+\s*(.+)', re.MULTILINE | re.IGNORECASE)

class Loc: 
    def __init__(self, id, name, desc, line):
        self.id = id            # номер локации (для puml)
        self.name = name        # имя локации
        self.desc = desc        # содержание локации
        self.line = line        # строка, на которой локация найдена
        self.dup = False        # локация является дубликатом?
        self.cycle = False      # на локацию есть самоссылка?
        self.end = False        # локация является концовкой?
        self.non_end = False    # не может быть концовкой если на нее ссылается proc, local или menu
                                # используется для установки флага end, чтобы не пересматривать перед этим все ссылки заново
        self.tech = False       # техническая локация
        self.orphan = False     # локация-сиротка (недостижима от старта, не может быть технической)
        self.links = []         # [(target_id, target_name, type, label, is_phantom, is_manu, is_local)]
        self.vars = set()       # переменные
        self.invs = set()       # предметы инвентаря

class UrqParser:
    def __init__(self):
        self.warnings = []
    
    def parse_file(self, file_path):
        """Парсит URQ файл и возвращает структуру"""        
        orig_content = self._read_file(file_path)
        if not orig_content:
            return []
        
        clean_content = self._prep_content(orig_content)
        
        # Получаем локации с правильными номерами строк
        locs = self._get_locations(orig_content, clean_content)
        if not locs:
            self._add_warning(f"В файле {os.path.basename(file_path)} не найдено ни одной метки")
            return []
        
        # Анализируем содержимое локаций
        self._analyze_locations(locs, clean_content)
        return locs

    def _get_locations(self, orig_content, clean_content):
        """Извлекает локации с правильными номерами строк"""
        orig_matches = list(LOC_PATTERN.finditer(orig_content))
        clean_matches = list(LOC_PATTERN.finditer(clean_content))
        
        locs = []
        name_first_idx = {}  # Для отслеживания дубликатов
        
        if len(orig_matches) != len(clean_matches):
            self._add_warning("Количество меток в оригинале и очищенном контенте не совпадает")
        
        for i, clean_m in enumerate(clean_matches):
            name = clean_m.group(1).strip()
            
            # Вычисляем правильный номер строки
            real_line = self._calc_real_line(orig_content, orig_matches, i, clean_content, clean_m)
            
            # Извлекаем описание из чистого контента
            s_pos = clean_m.end()
            e_pos = clean_matches[i + 1].start() if i + 1 < len(clean_matches) else len(clean_content)
            l_cont = clean_content[s_pos:e_pos].lstrip()
            
            desc = self._extract_description(l_cont)
            loc = Loc(str(i), name, desc, real_line)
            loc.tech = self._is_tech_loc(name) or (i == 0)  # первая локация всегда техническая
            
            # Проверяем дубликаты
            if name in name_first_idx:
                loc.dup = True
                self._add_warning(f"Найден дубликат метки: '{name}' на строке {real_line}")
            else:
                if name: 
                    name_first_idx[name] = i
            
            locs.append(loc)
        
        return locs

    def _calc_real_line(self, orig_content, orig_matches, i, clean_content, clean_m):
        """Вычисляет реальный номер строки для локации"""
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            pos_colon = orig_m.group(0).find(':')
            if pos_colon != -1:
                abs_pos = orig_m.start() + pos_colon
                return orig_content[:abs_pos].count('\n') + 1
            else:
                line_num = orig_content[:orig_m.start()].count('\n') + 1
                if (orig_m.start() > 0 and orig_content[orig_m.start()] == '\n' and
                    orig_content[orig_m.start():].split('\n', 1)[0].strip().startswith(':')):
                    line_num += 1
                return line_num
        else:
            line_num = clean_content[:clean_m.start()].count('\n') + 1
            if (clean_m.start() > 0 and clean_content[clean_m.start()] == '\n' and
                clean_content[clean_m.start():].split('\n', 1)[0].strip().startswith(':')):
                line_num += 1
            return line_num

    def _analyze_locations(self, locs, clean_content):
        """Анализирует содержимое локаций и извлекает связи"""
        clean_matches = list(LOC_PATTERN.finditer(clean_content))
        
        # Извлекаем связи и флаги для каждой локации
        for i, loc in enumerate(locs):
            if i < len(clean_matches):
                s_pos = clean_matches[i].end()
                e_pos = clean_matches[i + 1].start() if i + 1 < len(clean_matches) else len(clean_content)
                l_cont = clean_content[s_pos:e_pos].lstrip()
                
                self._extract_links_and_flags(loc, l_cont, clean_matches, i)
        
        # Резолвим цели и помечаем концовки
        self._resolve_target_ids(locs)
        
        # Помечаем концевые локации
        s_ids = {l.id for l in locs if any(not link[6] for link in l.links)}
        for l in locs:
            if (l.id not in s_ids and not l.non_end and not l.tech):
                l.end = True

    def _is_tech_loc(self, name):
        """Проверяет является ли локация технической"""
        if not name:
            return False
        name_lower = name.lower()
        return (name_lower == 'common' or 
                name_lower.startswith('common_') or 
                name_lower.startswith('use_') or 
                name_lower.startswith('inv_'))

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
        # print(f"DEBUG: Parsing loc '{loc.name}', content: {repr(l_cont)}")
        
        for m in BTN_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            raw_label = m.group(2)
            # DEBUG: показываем что захватили
            # print(f"DEBUG: BTN match - target: {repr(target)}, raw_label: {repr(raw_label)}")
            
            label = raw_label.split('\n')[0].strip() if raw_label else ""
            # print(f"DEBUG: Final label after processing: {repr(label)}")
            
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

        # Парсим переменные
        for m in VAR_PATTERN.finditer(l_cont):
            var_name = m.group(1).strip()
            if var_name:
                loc.vars.add(var_name.lower())

        # Парсим инвентарь
        for m in INV_PATTERN.finditer(l_cont):
            inv_name = m.group(1).strip()
            if inv_name:
                loc.invs.add(inv_name.lower())

    def _resolve_target_ids(self, locs):
        """Резолвим имена целей в ID и помечаем цели спец. связей"""
        # Маппинг имен не-дубликатов на их ID (case insensitive)
        n_map = {l.name.lower(): l.id for l in locs if not l.dup and l.name} # name_to_id
        
        # Предварительно создаем маппинг имен дубликатов на ID их *первого* вхождения
        # Это избегает многократного сканирования `locs` для каждого такого линка
        d_map = {} # name_to_first_dup_id
        # Отслеживаем имена, для которых уже нашли первый дубликат, чтобы не перезаписывать
        found_dup_names = set() 
        for l_obj in locs: # l_obj - loc object
            if l_obj.dup and l_obj.name:
                name_lower = l_obj.name.lower()
                if name_lower not in found_dup_names:
                    d_map[name_lower] = l_obj.id
                    found_dup_names.add(name_lower)
        
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
                
                # Case insensitive сравнение
                t_name_lower = t_name.lower()
                l_name_lower = l.name.lower()
                
                if t_name_lower == l_name_lower:  # Самоссылка
                    t_id, is_ph = l.id, False
                elif t_name_lower in n_map:  # Основная локация (не дубликат)
                    t_id, is_ph = n_map[t_name_lower], False
                elif t_name_lower in d_map:  # Ссылка на дубликат (берем ID первого)
                    t_id, is_ph = d_map[t_name_lower], False
                # Если t_id все еще None, то это фантомная ссылка
                
                res_links.append((t_id, t_name, l_type, label, is_ph, is_menu, is_local))
                
                # Устанавливаем non_end флаг для целевой локации (если она существует)
                if t_id is not None and (l_type == 'proc' or is_local or is_menu):
                    target_loc = id_to_loc.get(t_id)
                    if target_loc:
                        target_loc.non_end = True
            
            l.links = res_links
        
        # Находим сиротки - нетехнические локации недостижимые от старта или техлокаций
        self._mark_orphans(locs)

    def _mark_orphans(self, locs):
        """Помечает локации-сиротки"""
        if not locs:
            return
        
        # Строим граф всех связей (включая техлокации для прохождения)
        graph = {}
        tech_names = set()
        
        for loc in locs:
            if not loc.name:
                continue
                
            # Собираем техлокации
            if loc.tech:
                tech_names.add(loc.name)
            
            graph[loc.name] = []
            for link in loc.links:
                target_name = link[1]  # target_name из кортежа
                # Убираем проверку на phantom - нам важны все связи для достижимости
                if target_name:
                    graph[loc.name].append(target_name)
        
        # Стартовые точки: начальная локация + все техлокации
        start_name = locs[0].name if locs else None
        start_points = ({start_name} | tech_names) if start_name else tech_names
        
        if not start_points:
            # Если нет стартовых точек, все нетехнические - сиротки
            for loc in locs:
                if not loc.tech:
                    loc.orphan = True
                    self._add_warning(f"Сиротка '{loc.name}' на строке {loc.line}")
            return
        
        # BFS от всех стартовых точек
        reachable = set(start_points)
        queue = list(start_points)
        
        while queue:
            current = queue.pop(0)
            for target in graph.get(current, []):
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        
        # Помечаем недостижимые нетехнические локации как сиротки
        for loc in locs:
            if loc.name and not loc.tech and loc.name not in reachable:
                loc.orphan = True
                self._add_warning(f"Сиротка '{loc.name}' на строке {loc.line}")

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

        # Case insensitive сравнение для проверки цикла
        if target.lower() == loc.name.lower(): 
            loc.cycle = True
        
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