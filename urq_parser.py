# -*- coding: utf-8 -*-
# urq_parser.py
# URQ Parser - извлекает структуру из URQ файлов
import re
import os
from collections import deque

# Регулярки для парсинга URQ
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.M)
END_PATTERN = re.compile(r'^\s*\bend\b', re.M | re.I)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.M | re.I)
PROC_PATTERN = re.compile(r'^\s*\bproc\b', re.M | re.I)
PLN_PATTERN = re.compile(r'^\s*pln\s*(.*)$', re.M)
P_PATTERN = re.compile(r'^\s*p\s*(.*)$', re.M)
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),([^\r\n]*?)(?=\r?\n|$)', re.M | re.I)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.M | re.I)
PROC_CMD_PATTERN = re.compile(r'^\s*\bproc\s+(.+)', re.M | re.I)
INLINE_BTN_PATTERN = re.compile(r'\[\[([^\]|]*?)(?:\|([^\]]*?))?\]\]')
PLN_TEXT_EXTRACTOR = re.compile(r"^(?:pln|p)\s(.*)$")
TEXT_EXTRACTION = re.compile(r"^(pln|p)\s(.*)$", re.M)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.M | re.DOTALL)
COLON_PATTERN = re.compile(r':([^\n]*)')

VAR_PATTERN = re.compile(r'^\s*([^=\n]+?)\s*=', re.M)
INV_PATTERN = re.compile(r'^\s*inv\+\s*(.+)', re.M | re.I)

# Константы
ENCODING_BUFFER_SIZE = 1024

# Link tuple indices
LINK_TARGET_ID = 0
LINK_TARGET_NAME = 1
LINK_TYPE = 2
LINK_LABEL = 3
LINK_IS_PHANTOM = 4
LINK_IS_MENU = 5
LINK_IS_LOCAL = 6

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
        self.tech = False       # техническая локация
        self.orphan = False     # локация-сиротка (недостижима от старта, не может быть технической)
        self.links = []         # [(target_id, target_name, type, label, is_phantom, is_menu, is_local)]
        self.vars = set()       # переменные
        self.invs = set()       # предметы инвентаря

    def __repr__(self):
        return f"Loc(id={self.id}, name='{self.name}', line={self.line}, links={len(self.links)}, flags={self._get_flags()})"    

    def _get_flags(self):
        flags = []
        if self.dup: flags.append('dup')
        if self.cycle: flags.append('cycle')
        if self.end: flags.append('end')
        if self.tech: flags.append('tech')
        if self.orphan: flags.append('orphan')
        return ','.join(flags) if flags else 'none'

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
        
        # Освобождаем память от больших строк
        del orig_content
        
        if not locs:
            self._add_warning(f"В файле {os.path.basename(file_path)} не найдено ни одной метки")
            return []
        
        # Анализируем содержимое локаций
        self._analyze_locations(locs, clean_content)
        
        # Освобождаем память от больших строк
        del clean_content

        # DEBUG: показываем структуру локаций
        # print("=== LOC STRUCTURE DEBUG ===")
        # for loc in locs:
        #     print(f"{loc}")
        #     for link in loc.links:
        #         print(f"  -> {link}")
        # print("=== END DEBUG ===\n")
        
        return locs
        
    def parse_string(self, qst_content_string, encoding='utf-8'):
        """Парсит URQ строку и возвращает структуру"""
        if not qst_content_string:
            self._add_warning("Входная строка QST пуста.")
            return []

        # _prep_content ожидает строку, поэтому передаем напрямую
        clean_content = self._prep_content(qst_content_string)
        
        # _get_locations ожидает оригинальный и очищенный контент
        # Для parse_string оригинальный контент это сама входная строка
        locs = self._get_locations(qst_content_string, clean_content)
        
        if not locs:
            self._add_warning("В предоставленной строке QST не найдено ни одной метки.")
            return []
        
        # Анализируем содержимое локаций
        self._analyze_locations(locs, clean_content)
        
        return locs

    def _get_locations(self, orig_content, clean_content):
        """Извлекает локации с правильными номерами строк через двухэтапное сопоставление"""
        # Этап 1: Находим все локации в очищенном контенте (для логики)
        clean_matches = list(LOC_PATTERN.finditer(clean_content))
        if not clean_matches:
            return []
        
        # Этап 2: Собираем потенциальные :метки из оригинала (для точных номеров строк)
        orig_pots = []  # raw=имя_после_двоеточия, line=номер_строки
        orig_lines = orig_content.split('\n')
        
        for line_num, line in enumerate(orig_lines, 1):
            # Ищем все :метка в каждой строке (не используем LOC_PATTERN - он для начала строки)
            for m in COLON_PATTERN.finditer(line):
                # raw_name = то что после :, убираем блочные /* */ комменты  
                raw_name = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.DOTALL).strip()
                # Добавляем даже если raw_name пустой, но есть что-то после очистки строчных ;
                if raw_name or self._strip_line_comments(m.group(1).strip()):
                    orig_pots.append({
                        "raw": raw_name,        # имя метки (блочные комменты убраны)
                        "line": line_num        # реальный номер строки
                    })
        
        # Этап 3: Сопоставляем clean_matches с orig_pots последовательно
        locs = []
        name_idx = {}       # для поиска дубликатов
        orig_idx = 0        # текущий индекс в orig_pots
        
        for i, clean_m in enumerate(clean_matches):
            clean_name = clean_m.group(1).strip()  # имя из очищенного контента
            real_line = -1
            
            # Ищем соответствующую метку в оригинале (последовательно)
            while orig_idx < len(orig_pots):
                pot = orig_pots[orig_idx]
                # Полностью очищаем имя из оригинала (блочные и строчные комменты)
                orig_clean = self._strip_line_comments(pot["raw"])
                
                if orig_clean:  # пропускаем пустые после очистки
                    # Правила сопоставления:
                    # A) Точное совпадение: clean_name == orig_clean
                    # B) Префикс: clean_name начинается с orig_clean (для склеенных &)
                    if clean_name == orig_clean or clean_name.startswith(orig_clean):
                        real_line = pot["line"]
                        orig_idx += 1  # переходим к следующей потенциальной метке
                        break
                
                orig_idx += 1
                # Защита от выхода за границы
                if orig_idx >= len(orig_pots):
                    break
            
            # Фоллбэк: если не нашли в оригинале, считаем по clean_content
            if real_line == -1:
                real_line = clean_content[:clean_m.start()].count('\n') + 1
            
            # Извлекаем описание локации
            s_pos = clean_m.end()
            e_pos = clean_matches[i + 1].start() if i + 1 < len(clean_matches) else len(clean_content)
            desc = self._extract_description(clean_content[s_pos:e_pos].lstrip())
            
            # Создаем объект локации
            loc = Loc(str(i), clean_name, desc, real_line)
            loc.tech = self._is_tech_loc(clean_name) or (i == 0)  # первая всегда техническая
            
            # Проверяем дубликаты
            if clean_name in name_idx:
                loc.dup = True
                self._add_warning(f"Найден дубликат метки: '{clean_name}' на строке {real_line}")
            else:
                if clean_name:
                    name_idx[clean_name] = i
            
            locs.append(loc)
        
        return locs

    def _strip_line_comments(self, text):
        """Убирает комментарии ; из текста"""
        semi_pos = text.find(';')
        return text[:semi_pos].strip() if semi_pos != -1 else text.strip()

    def _analyze_locations(self, locs, clean_content):
        """Анализирует содержимое локаций и извлекает связи"""
        clean_matches = list(LOC_PATTERN.finditer(clean_content))
        
        # Извлекаем связи и флаги для каждой локации
        for i, loc in enumerate(locs):
            if i < len(clean_matches):
                s_pos = clean_matches[i].end()
                e_pos = clean_matches[i + 1].start() if i + 1 < len(clean_matches) else len(clean_content)
                l_cont = clean_content[s_pos:e_pos].lstrip()
                
                self._extract_links_and_flags(loc, l_cont, locs)
        
        # Резолвим цели и помечаем концовки
        self._resolve_target_ids(locs)
        
        # Помечаем концовки - локации у которых нет исходящих ссылок, кроме меню и локальных
        for loc in locs:
            has_outgoing = any(not link[LINK_IS_MENU] and not link[LINK_IS_LOCAL] for link in loc.links)
            if not has_outgoing and not loc.non_end and not loc.tech:
                loc.end = True

    def _is_tech_loc(self, name):
        """Проверяет является ли локация технической"""
        if not name:
            return False
        name_lower = name.lower()
        return (name_lower == 'common' or 
                name_lower.startswith('common_') or 
                name_lower.startswith('use_') or 
                name_lower.startswith('inv_'))

    def _extract_links_and_flags(self, loc, l_cont, locs):
        """Извлекает связи и устанавливает флаги"""
        has_end = END_PATTERN.search(l_cont)
        has_goto = GOTO_PATTERN.search(l_cont)
        
        # Автолинк - просто на следующую локацию по ID
        if not has_end and not has_goto:
            next_id = str(int(loc.id) + 1)
            if int(next_id) < len(locs):
                next_loc = locs[int(next_id)]
                self._add_link(loc, next_id, next_loc.name, "auto", "", False, False, False)

        # Оптимизация: делаем поиск по тексту только один раз
        text_matches = list(TEXT_EXTRACTION.finditer(l_cont))
        pln_found = any(m.group(1) == 'pln' for m in text_matches)
        
        for m in text_matches:
            t_type = m.group(1)
            text = m.group(2).strip()
            if (t_type == 'pln' or not pln_found) and text:
                self._extract_inline_buttons(text, loc)

        for m in BTN_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            raw_label = m.group(2)
            label = raw_label.split('\n')[0].strip() if raw_label else ""
            
            if target: 
                self._add_link_with_prefixes(loc, target, "btn", label)
            else: 
                self._add_warning(f"Пустая цель btn из '{loc.name}', кнопка '{label}'")

        for m in GOTO_CMD_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            if target: 
                self._add_link_with_prefixes(loc, target, "goto", "")
            else: 
                self._add_warning(f"Пустая цель goto из '{loc.name}'")

        for m in PROC_CMD_PATTERN.finditer(l_cont):
            target = m.group(1).strip()
            if target: 
                self._add_link_with_prefixes(loc, target, "proc", "")
            else: 
                self._add_warning(f"Пустая цель proc из '{loc.name}'")

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
       n_map = {l.name.lower(): l.id for l in locs if not l.dup and l.name}
       
       # Маппинг имен дубликатов на ID их *первого* вхождения
       d_map = {}
       found_dup_names = set() 
       for l_obj in locs:
           if l_obj.dup and l_obj.name:
               name_lower = l_obj.name.lower()
               if name_lower not in found_dup_names:
                   d_map[name_lower] = l_obj.id
                   found_dup_names.add(name_lower)
       
       # Создаем маппинг ID -> loc для быстрого поиска
       id_to_loc = {l.id: l for l in locs}
       
       for loc in locs:
           res_links = []
           for link in loc.links:
               t_id = link[LINK_TARGET_ID]
               t_name = link[LINK_TARGET_NAME] 
               l_type = link[LINK_TYPE]
               label = link[LINK_LABEL]
               is_phantom = link[LINK_IS_PHANTOM]
               is_local = link[LINK_IS_LOCAL]
               is_menu = link[LINK_IS_MENU]
               
               # Если target_id уже установлен (автолинки), оставляем как есть
               if t_id is not None:
                   res_links.append(link)
                   # Устанавливаем non_end флаг
                   if l_type == 'proc' or is_local or is_menu:
                       target_loc = id_to_loc.get(t_id)
                       if target_loc:
                           target_loc.non_end = True
                   continue
               
               # Резолвим по имени
               new_id = None
               t_name_lower = t_name.lower()
               
               if t_name_lower == loc.name.lower():  # Самоссылка
                   new_id = loc.id
                   loc.cycle = True
               elif t_name_lower in n_map:  # Основная локация
                   new_id = n_map[t_name_lower]
               elif t_name_lower in d_map:  # Дубликат
                   new_id = d_map[t_name_lower]
               
               # Обновляем is_phantom
               new_phantom = new_id is None
               res_links.append((new_id, t_name, l_type, label, new_phantom, is_menu, is_local))
               
               # Устанавливаем non_end флаг
               if new_id and (l_type == 'proc' or is_local or is_menu):
                   target_loc = id_to_loc.get(new_id)
                   if target_loc:
                       target_loc.non_end = True
           
           loc.links = res_links
       
       # Находим сиротки
       self._mark_orphans(locs)
    def _mark_orphans(self, locs):
        """Помечает локации-сиротки"""
        if not locs:
            return
        
        # Строим граф связей по ID (более надежно)
        graph = {}  # id -> [target_ids]
        
        for loc in locs:
            graph[loc.id] = []
            for link in loc.links:
                t_id = link[LINK_TARGET_ID]  # target_id
                if t_id:
                    graph[loc.id].append(t_id)
        
        # Стартовые точки: все техлокации
        start_ids = {l.id for l in locs if l.tech}
        
        if not start_ids and locs:
            start_ids.add(locs[0].id)  # Первая локация как запасной старт
        
        if not start_ids:
            # Если совсем нет стартовых точек, все - сиротки
            for loc in locs:
                if not loc.tech:
                    loc.orphan = True
                    self._add_warning(f"Сиротка '{loc.name}' на строке {loc.line}")
            return
        
        # BFS от всех стартовых точек с оптимизированной очередью
        reachable = set(start_ids)
        queue = deque(start_ids)
        
        while queue:
            current = queue.popleft()
            for target_id in graph.get(current, []):
                if target_id not in reachable:
                    reachable.add(target_id)
                    queue.append(target_id)
        
        # Помечаем недостижимые нетехнические локации как сиротки
        for loc in locs:
            if not loc.tech and loc.id not in reachable:
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
            if re.match(r'^\s*if\b', line_text, re.I):
                parts = re.split(r'\b(then|else)\b', line_text, flags=re.I)
                lines.extend(p.lstrip() for p in parts if p.lstrip() and p.lstrip().lower() not in ('then', 'else'))
            else:
                lines.append(line_text)
        # Разбиваем по & и очищаем
        return '\n'.join(p.strip() for p in '\n'.join(lines).split('&') if p.strip())

    def _detect_encoding(self, f_path):
        """Определяет кодировку файла"""
        if not os.path.exists(f_path):
            self._add_warning(f"Файл не найден: {f_path}")
            return None
        try:
            with open(f_path, 'rb') as f:
                sample = f.read(ENCODING_BUFFER_SIZE)
            for enc in ['cp1251', 'utf-8']:  # cp1251 сначала
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

    def _read_file(self, f_path):
        """Читает файл"""
        enc = self._detect_encoding(f_path)
        if not enc:
            self._add_warning(f"Не удалось прочитать файл {os.path.basename(f_path)} - неизвестная кодировка")
            return None
        try:
            with open(f_path, 'r', encoding=enc) as f:
                return f.read()
        except IOError as e:
            self._add_warning(f"Ошибка чтения файла {os.path.basename(f_path)}: {e}")
            return None

    def _extract_description(self, l_cont):
        """Извлекает описание из контента"""
        parts = [self._process_text_with_buttons(m.group(2).strip()).strip() 
                 for m in TEXT_EXTRACTION.finditer(l_cont)]
        return self._clean_final_text(' '.join(parts)) if parts else "Нет описания"       
    
    def _process_text_with_buttons(self, text):
        """Обрабатывает текст с инлайн кнопками"""
        return INLINE_BTN_PATTERN.sub(lambda m: m.group(1) if m.group(1) is not None else "", text)

    def _clean_final_text(self, text):
        """Финальная очистка текста"""
        return text.replace('"', "''") if text else "Нет описания"
            
    def _extract_inline_buttons(self, text, loc):
        """Извлекает инлайн кнопки из текста"""
        for m in INLINE_BTN_PATTERN.finditer(text):
            desc_text = m.group(1) if m.group(1) is not None else ""
            target_text = m.group(2) if m.group(2) is not None else desc_text
            self._add_link_with_prefixes(loc, target_text.strip(), "btn", desc_text.strip())
            
    def _add_link_with_prefixes(self, loc, target, l_type, label):
        """Добавляет связь с обработкой префиксов % и !"""
        target = target.strip()
        is_menu = is_local = False
        
        if target and target[0] in '%!':
            is_menu = (target[0] == '%')
            is_local = (target[0] == '!')
            target = target[1:]  # Убираем префикс
        
        cl_label = self._clean_button_text(label.strip()) if l_type == "btn" and label.strip() else label
        
        # Все ссылки пока добавляем с target_id=None, резолвим позже
        self._add_link(loc, None, target, l_type, cl_label, True, is_menu, is_local)
                 
    def _add_link(self, loc, t_id, t_name, l_type, label, is_ph, is_menu, is_local):
        """Единый метод добавления связи в правильном формате"""
        loc.links.append((t_id, t_name, l_type, label, is_ph, is_menu, is_local))
        
    def _clean_button_text(self, text):
        """Очищает текст кнопки"""
        if not text: 
            return ""
        return self._process_text_with_buttons(text).replace('"', "''")

    def _add_warning(self, msg):
        """Добавляет предупреждение"""
        self.warnings.append(f"URQ Parser Warning: {msg}")

    def get_warnings(self):
        """Возвращает список предупреждений"""
        return self.warnings