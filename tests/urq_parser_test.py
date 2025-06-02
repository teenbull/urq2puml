Отличная постановка проблемы и предложенное решение! Ваше тестовое решение test_line_numbers.py демонстрирует правильный подход к получению реальных номеров строк.

Оценка проблемы и текущего решения:

Вы абсолютно правы, текущий метод _parse_locations вычисляет номера строк на основе предварительно обработанного (очищенного) контента, что приводит к неверным номерам из-за удаления комментариев и других элементов. Это ключевая ошибка.

Оценка вашего тестового кода и стратегии:

Ваша стратегия:

Получить оригинальный контент.

Получить очищенный контент.

Найти все совпадения локаций (:loc) в обоих контентах.

Итерировать по очищенным совпадениям, но для каждого совпадения использовать его индекс для получения соответствующего совпадения в оригинальном контенте, чтобы вычислить реальный номер строки.

Использовать очищенный контент для извлечения содержимого локаций (описания, ссылок и т.д.).

Плюсы:

Точность: Этот подход гарантирует получение реальных номеров строк из оригинального файла.

Логическое разделение: Четко отделены два этапа: определение номера строки (по оригиналу) и парсинг содержимого (по очищенному).

Использование индексов: Допущение, что порядок локаций сохраняется при очистке, является корректным, так как _prep_content не изменяет сами метки локаций, только их содержимое или комментарии.

Моменты для оптимизации и улучшения (с учетом ваших предпочтений к коду):

Эффективность подсчета строк: В вашем текущем коде _parse_locations в urq_parser.py уже реализован очень эффективный способ подсчета строк с помощью cum_nl и last_nl_pos. В тестовом скрипте для fallback (content[:m.start()].count('\n')) используется менее эффективный метод, который пересчитывает с начала строки каждый раз. Мы должны сохранить cum_nl подход для подсчета строк в оригинальном контенте.

Интеграция в UrqParser: Вместо создания двух отдельных этапов и, возможно, двух списков локаций, можно интегрировать этот двухэтапный подход (анализ оригинала для строк, анализ очищенного для контента) в один проход внутри _parse_locations.

Обработка расхождений: Хорошо, что вы добавили предупреждение о расхождении в количестве локаций. Это важный сигнал. Если такое происходит, это говорит о более фундаментальной проблеме с LOC_PATTERN или _prep_content, которую следует исследовать. В идеале, количество :loc меток должно быть одинаковым в обеих версиях контента.

Предлагаемое изменение для urq_parser.py:

Чтобы реализовать это наиболее элегантно и эффективно, мы слегка изменим parse_file, чтобы она передавала оригинальный контент в _parse_locations. А уже _parse_locations будет выполнять _prep_content и работать с обеими версиями контента.

# urq_parser.py
# URQ Parser - извлекает структуру из URQ файлов
import re
import os

# (Регулярки остаются без изменений)
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
END_PATTERN = re.compile(r'^\s*\bend\b', re.MULTILINE | re.IGNORECASE)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.MULTILINE | re.IGNORECASE)
PROC_PATTERN = re.compile(r'^\s*\bproc\b', re.MULTILINE | re.IGNORECASE)
PLN_PATTERN = re.compile(r'^\s*pln\s*(.*)$', re.MULTILINE)
P_PATTERN = re.compile(r'^\s*p\s*(.*)$', re.MULTILINE)
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),([^\r\n]*?)(?=\r?\n|$)', re.MULTILINE | re.IGNORECASE)
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
        self.id = id
        self.name = name
        self.desc = desc
        self.line = line
        self.dup = False
        self.cycle = False
        self.end = False
        self.non_end = False
        self.tech = self._is_tech_loc(name)
        self.orphan = False
        self.links = []
        self.vars = set()
        self.invs = set()

    def _is_tech_loc(self, name):
        """Проверяет является ли локация технической"""
        if not name:
            return False
        name_lower = name.lower()
        return (name_lower == 'common' or
                name_lower.startswith('common_') or
                name_lower.startswith('use_') or
                name_lower.startswith('inv_') or
            self.id == '0')

class UrqParser:
    def __init__(self):
        self.warnings = []

    def parse_file(self, file_path):
        """Парсит URQ файл и возвращает структуру"""
        orig_content = self._read_file(file_path) # Читаем ОРИГИНАЛЬНЫЙ контент
        if not orig_content:
            return []
        # Теперь _parse_locations получает оригинальный контент и сам его преобразует
        locs = self._parse_locations(orig_content)
        if not locs:
            self._add_warning(f"В файле {os.path.basename(file_path)} не найдено ни одной метки")
        return locs

    def _parse_locations(self, orig_c): # orig_c - original_content
        """
        Парсит все локации и связи, получая реальные номера строк из оригинального контента,
        а содержимое из очищенного.
        """
        clean_c = self._prep_content(orig_c) # clean_c - cleaned_content

        orig_ms = list(LOC_PATTERN.finditer(orig_c)) # orig_ms - original_matches
        clean_ms = list(LOC_PATTERN.finditer(clean_c)) # clean_ms - cleaned_matches

        if not clean_ms:
            return []

        if len(orig_ms) != len(clean_ms):
            # Если количество меток различается, это серьезная проблема,
            # и номера строк могут быть неточными.
            self._add_warning(
                f"Обнаружено несоответствие количества меток. Оригинал: {len(orig_ms)}, "
                f"Очищенный: {len(clean_ms)}. Номера строк могут быть неточными. "
                "Проверьте LOC_PATTERN и COMMENTS_REMOVAL."
            )
            # При таком расхождении, мы не можем гарантировать соответствие по индексу.
            # Для надежности в данном случае, продолжим парсить по очищенному,
            # но предупреждение обязательно.

        locs = []
        name_first_idx = {}

        # Эффективный подсчет строк для оригинального контента
        orig_cum_nl = 0
        orig_last_nl_pos = 0

        # Эффективный подсчет строк для очищенного контента (на случай fallback)
        clean_cum_nl = 0
        clean_last_nl_pos = 0

        for i, clean_m in enumerate(clean_ms): # clean_m - cleaned_match
            name = clean_m.group(1).strip()
            real_line = -1 # Инициализируем на случай ошибки

            # Пытаемся получить реальный номер строки из оригинального контента
            if i < len(orig_ms):
                orig_m = orig_ms[i] # orig_m - original_match
                # Эффективный подсчет номера строки из оригинального контента
                seg_nl = orig_c.count('\n', orig_last_nl_pos, orig_m.start())
                orig_cum_nl += seg_nl
                real_line = orig_cum_nl + 1
                orig_last_nl_pos = orig_m.start()
            else:
                # Если нет соответствующей метки в оригинале (например, orig_ms короче),
                # используем номер строки из очищенного контента и добавляем предупреждение.
                self._add_warning(
                    f"Не найдена соответствующая метка '{name}' в оригинальном контенте "
                    f"по индексу {i}. Используется номер строки из очищенного контента."
                )
                seg_nl = clean_c.count('\n', clean_last_nl_pos, clean_m.start())
                clean_cum_nl += seg_nl
                real_line = clean_cum_nl + 1
                clean_last_nl_pos = clean_m.start()

            # Извлекаем контент локации из ОЧИЩЕННОГО контента
            s_pos = clean_m.end() # start_pos
            e_pos = clean_ms[i + 1].start() if i + 1 < len(clean_ms) else len(clean_c) # end_pos
            l_cont = clean_c[s_pos:e_pos].lstrip() # loc_content

            desc = self._extract_description(l_cont)
            loc = Loc(str(i), name, desc, real_line) # Используем РЕАЛЬНЫЙ номер строки

            # Проверяем дубликаты
            if name in name_first_idx:
                loc.dup = True
                self._add_warning(f"Найден дубликат метки: '{name}' на строке {real_line}")
            else:
                if name: name_first_idx[name] = i

            locs.append(loc)

            # Извлекаем связи и флаги, используя контент из ОЧИЩЕННОГО файла
            # Передаем `clean_ms` для корректной проверки границ авто-связей
            self._extract_links_and_flags(loc, l_cont, clean_ms, i)

        self._resolve_target_ids(locs)
        # Помечаем концевые локации (концовки)
        s_ids = {l_obj.id for l_obj in locs if any(not link[6] for link in l_obj.links)} # link[6] is is_local
        for l_obj in locs:
            if (l_obj.id not in s_ids and
                    not l_obj.non_end and
                    not l_obj.tech):
                l_obj.end = True

        self._mark_orphans(locs) # Находим сиротки

        return locs

    # (Остальные методы класса UrqParser остаются без изменений)
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

        for m in BTN_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            raw_label = m.group(2)
            label = raw_label.split('\n')[0].strip() if raw_label else ""
            
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
        for line_text in content.split('\n'):
            if re.match(r'^\s*if\b', line_text, re.IGNORECASE):
                parts = re.split(r'\b(then|else)\b', line_text, flags=re.IGNORECASE)
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

            self._add_link_with_cycle_check(loc, target_text.strip(), "btn", desc_text.strip())
            
    def _add_link_with_cycle_check(self, loc, target, l_type, label): # l_type - link_type
        """Добавляет связь с проверкой на цикл"""
        target = target.strip()
        is_menu = is_local = False
        
        if target:
            prefix = target[0]
            if prefix in '%!':
                target = target[1:] # Убираем префикс из имени цели
                is_menu = (prefix == '%')
                is_local = (prefix == '!')

        if target.lower() == loc.name.lower(): 
            loc.cycle = True
        
        cl_label = "" # clean_label
        if l_type == "btn":
            stripped = label.strip()
            cl_label = self._clean_button_text(stripped) if stripped else label
        
        loc.links.append((target, l_type, cl_label, is_menu, is_local))
                 
    def _clean_button_text(self, text):
        """Очищает текст кнопки"""
        if not text: return ""
        return self._process_text_with_buttons(text).replace('"', "''")

    def _add_warning(self, msg): # msg - message
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Parser Warning: {msg}")

    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings
