# Конвертер из URQ в граф PlantUML
# Плагин для Sublime Text, поддерживает только Python 3.3 (без f-строк)

# Путь к jar файлу с https://plantuml.com/ru/download
# Если файл не найдет - будет попытка генерить граф онлайн
PLANTUML_JAR_PATH = "C:\\java\\plantuml-1.2025.2.jar"


# Лимиты текста для красоты
LOC_LIMIT = 40
DESC_LIMIT = 50
BTN_LIMIT = 30

import sublime
import sublime_plugin
import os, sys
import re
import subprocess
import string
import base64
import zlib
import urllib.request
import urllib.error

# Константы стилей PlantUML - как будет выглядеть граф
PHANTOM_NODE = """state "//phantom" as PHANTOM_NODE_URQ #ffcccb {
  PHANTOM_NODE_URQ: (Ссылка на несуществующую локацию)
}
"""
# !define PLANTUML_LIMIT_SIZE 8192
SKIN_PARAMS = """skinparam stateArrowColor #606060
skinparam state {
    BackgroundColor #F0F8FF
    BorderColor #A9A9A9
    FontColor #303030
    ArrowFontColor #404040
}
"""

# Цвета для разных типов состояний
CYCLE_COLOR = "#ffffcc"  # Желтый для зацикленных локаций
DOUBLE_COLOR = "#ffcccb"  # Красный для дубликатов и фантомов
END_COLOR = "#d0f0d0"  # Зеленый для концовок
START_LOC = "[*] --> 0\n"

# Шаблоны форматирования - чтобы не писать одно и то же

AUTO_FORMAT = "{0} -[dotted]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : [{1}]\n"
BTN_FORMAT = "{0} --> {1} : {2}\n" 
GOTO_FORMAT = "{0} --> {1} : [{2}]\n"
STATE_FORMAT = 'state "{0}" as {1}'
DOUBLE_STATE_FORMAT = 'state "{0}" as {1} {2}'
STATE_DESC_FORMAT = '{0}: {1}\n'
LOST_DESC_FORMAT = '{0}: [Дубликат метки, строка {1}]\\n\\n{2}\n'
PROC_FORMAT = "{1} --> {0} : [proc]\n{0} -[dotted]-> {1}\n"  # стелка туда и обратно для proc

# Кэшированные регулярки - компилируем один раз, используем много
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
END_PATTERN = re.compile(r'^\s*\bend\b', re.MULTILINE | re.IGNORECASE)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.MULTILINE | re.IGNORECASE)
PROC_PATTERN = re.compile(r'^\s*\bproc\b', re.MULTILINE | re.IGNORECASE)
PLN_PATTERN = re.compile(r'pln\s+([^.\n]+)')
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', re.MULTILINE | re.IGNORECASE)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.MULTILINE | re.IGNORECASE)
PROC_CMD_PATTERN = re.compile(r'^\s*\bproc\s+(.+)', re.MULTILINE | re.IGNORECASE)
PLN_NEWLINE_PATTERN = re.compile(r'[\s\t]*\n[\s\t]*pln\b', re.IGNORECASE) # для удаления \n*pln

class PlantumlGenerator:
    """Класс для генерации диаграмм через онлайн сервис PlantUML"""
    def __init__(self, server_url="http://www.plantuml.com/plantuml/"):
        self.server_url = server_url
        # Алфавиты для кодирования - магия PlantUML
        self.p_alpha = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        self.b64_alpha = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
        self.b64_to_p = str.maketrans(self.b64_alpha, self.p_alpha)

    def _req(self, type, text):
        """Отправляет запрос на сервер PlantUML"""
        # Сжимаем и кодируем текст по протоколу PlantUML
        enc = zlib.compress(text.encode('utf-8'))[2:-4]
        enc_b64 = base64.b64encode(enc).decode().translate(self.b64_to_p)
        url = "{}{}/{}".format(self.server_url, type, enc_b64)
        h = {'User-Agent': 'Sublime URQ2PUML'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                if resp.getcode() == 200:
                    return resp.read()
                # Если что-то пошло не так
                err_body = resp.read().decode(errors='replace') or "(empty)"
                err_msg = "HTTP Error {}: {}. Body: {}".format(resp.getcode(), resp.reason, err_body)
                print("Online Gen Error Details: " + err_msg)
                raise urllib.error.HTTPError(url, resp.getcode(), err_msg, resp.headers, None)
        except urllib.error.HTTPError as e_http:
            print("Online Gen HTTPError: {} {}".format(e_http.code, e_http.reason))
            raise
        except Exception as e_gen:
            raise RuntimeError("Сервер PlantUML ({}) ошибка: {}".format(type(e_gen).__name__, e_gen))

    def generate_png(self, plantuml_text):
        """Генерирует PNG через онлайн сервис"""
        return self._req("img", plantuml_text)

    def generate_svg(self, plantuml_text):
        """Генерирует SVG через онлайн сервис"""
        return self._req("svg", plantuml_text)

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    """Основная команда плагина"""
    def run(self, edit, png=False, svg=False, net=False):
        current_file = self.view.file_name()

        # Проверяем, что файл URQ
        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Файл должен быть URQ (.qst)")
            return

        # Автопереключение на сетевой режим если jar потерялся
        if not net and not os.path.exists(PLANTUML_JAR_PATH):
            net = True
            print("URQ to PlantUML: JAR не найден, переключение на сетевой режим")

        self.view.window().status_message("Конвертация URQ в PlantUML...")
        self.warnings = []  # Собираем все предупреждения

        try:
            # Парсим URQ файл
            result = self._parse_urq_file(current_file)
            if not result:
                return
            
            locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids = result

            # Генерируем PlantUML
            puml_file = os.path.splitext(current_file)[0] + '.puml'
            puml_content = self._generate_plantuml(locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids, puml_file)
            
            if os.path.exists(puml_file):
                # !!! не открывать лишний раз puml файл
                if not png and not svg:
                    self.view.window().open_file(puml_file)
                
                status_parts = ["Конвертация URQ в PlantUML: .puml файл сгенерирован"]
                
                # Генерируем PNG если нужно
                if png:
                    if net:
                        png_success = self._generate_png_online(puml_content, puml_file)
                    else:
                        png_success = self._generate_png_from_puml(puml_file)
                    
                    if png_success:
                        status_parts.append(".png файл создан" + (" онлайн" if net else "") + " и открыт")
                    else:
                        status_parts.append(".png не создан (см. предупреждения)")
                
                # Генерируем SVG если нужно
                if svg:
                    if net:
                        svg_success = self._generate_svg_online(puml_content, puml_file)
                    else:
                        svg_success = self._generate_svg_from_puml(puml_file)
                    
                    if svg_success:
                        status_parts.append(".svg файл создан" + (" онлайн" if net else ""))
                        
                        svg_file_path = os.path.splitext(puml_file)[0] + '.svg'
                        # if sublime.yes_no_cancel_dialog("Вы хотите открыть svg файл в программе по умолчанию?") == sublime.DIALOG_YES:
                        if not self._open_file_in_default_program(svg_file_path):
                            sublime.error_message("Не удалось открыть SVG файл в программе по умолчанию")
                    else:
                        status_parts.append(".svg не создан (см. предупреждения)")

                self.view.window().status_message(". ".join(status_parts) + ".")
            else:
                msg = "URQ to PlantUML Error: Файл .puml не был создан."
                self.warnings.append(msg)
                print(msg)

        except Exception as e:
            self._add_warning("Critical Error: Произошла ошибка при конвертации: {}".format(e))
        finally:
            self._print_warnings()


    def _prep_content(self, content):
        """Предобработка контента: удаление комментариев, объединение строк, токенизация"""
        # 1. Удаляем /* */ комментарии (C-style)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # 2. Удаляем ; комментарии (до конца строки)
        content = re.sub(r';[^\n]*', '', content)
        
        # 3. Объединяем строки: удаляем \n + пробелы/табы + _
        content = re.sub(r'\n\s*_', '', content)
        
        # 4. Разбиваем if/then/else конструкции ДО разбивки по &
        lines = []
        for line in content.split('\n'):
            if re.match(r'^\s*if\b', line, re.IGNORECASE):
                # Разбиваем по 'then' и 'else', сохраняем части
                parts = re.split(r'\b(then|else)\b', line, flags=re.IGNORECASE)
                for part in parts:
                    part = part.strip()
                    if part and part.lower() not in ('then', 'else'):
                        lines.append(part)
            else:
                lines.append(line)
        
        content = '\n'.join(lines)
        
        # 5. Наконец разбиваем по & и очищаем
        parts = content.split('&')
        content = '\n'.join(part.strip() for part in parts if part.strip())
        
        return content

    def _parse_urq_file(self, file_path):
        """Парсит URQ файл и извлекает локации и связи"""
        # Сначала читаем файл с определением кодировки
        encoding = self._detect_encoding(file_path)
        if not encoding:
            return None
            
        content = self._read_file_with_encoding(file_path, encoding)
        if not content:
            return None

        # Предобрабатываем контент
        content = self._prep_content(content)

        # Ищем все метки локаций
        matches = list(LOC_PATTERN.finditer(content))
        
        if not matches:
            self._add_warning("В файле {} не найдено ни одной метки".format(os.path.basename(file_path)))
            return None

        locs = {}  # Основные локации {name: [desc, id]}
        all_locs = {}  # Все локации включая дубликаты {id: [name, desc, line_num, is_duplicate]}
        btn_links = []
        auto_links = []
        goto_links = []
        proc_links = []
        cycle_ids = set()  # ID локаций с циклами
        loc_counter = 0
        name_counts = {}  # Счетчик дубликатов
        
        # Парсим все локации включая дубликаты
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            line_number = content[:match.start()].count('\n') + 1
            loc_content = content[start_pos:end_pos].lstrip()
            desc = self._extract_description(loc_content)
            
            loc_id = str(loc_counter)
            is_duplicate = name in name_counts
            
            # Первая встреча имени - основная локация
            if not is_duplicate:
                locs[name] = [desc, loc_id]
                name_counts[name] = 0
            else:
                name_counts[name] += 1
                self._add_warning("Найден дубликат метки: '{}' на строке {}".format(name, line_number))
            
            all_locs[loc_id] = [name, desc, line_number, is_duplicate]
            
            # Определяем следующую локацию по ID, не по имени
            next_loc_id = str(loc_counter + 1) if i + 1 < len(matches) else None
            self._extract_links(name, loc_content, btn_links, auto_links, goto_links, proc_links, loc_id, next_loc_id, cycle_ids)
            loc_counter += 1

        return locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids


    def _detect_encoding(self, file_path):
        """Определяет кодировку файла, читая небольшую порцию"""
        if not os.path.exists(file_path):
            self._add_warning("Файл не найден: {}".format(file_path))
            return None
        
        try:
            # Читаем первые 1024 байта для определения кодировки
            with open(file_path, 'rb') as f:
                sample = f.read(8)
            
            # Пробуем UTF-8
            try:
                sample.decode('utf-8')
                return 'utf-8'
            except UnicodeDecodeError:
                pass
            
            # Пробуем CP1251
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
        """Читает файл с указанной кодировкой"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except IOError as e:
            self._add_warning("Ошибка чтения файла {}: {}".format(os.path.basename(file_path), e))
            return None

    def _extract_description(self, content):
        """Извлекает описание локации из команды pln"""
        pln_match = PLN_PATTERN.search(content)
        return pln_match.group(1).strip() if pln_match else "Нет описания"

    def _extract_links(self, loc_name, content, btn_links, auto_links, goto_links, proc_links, loc_id, next_loc_id, cycle_ids):
        """Извлекает все типы связей из локации"""
        has_end = END_PATTERN.search(content)
        has_goto = GOTO_PATTERN.search(content)
        has_proc = PROC_PATTERN.search(content)
        
        # Автосвязь к следующей локации если нет end/goto/proc
        if not has_end and not has_goto and not has_proc and next_loc_id is not None:
            auto_links.append((loc_id, next_loc_id, "auto"))

        # Парсим btn команды (кнопки)
        for match in BTN_PATTERN.finditer(content):
            target, label = match.group(1).strip(), match.group(2).strip()
            if target:
                # Проверяем на цикл
                if target == loc_name:
                    cycle_ids.add(loc_id)
                btn_links.append((loc_id, target, label))
            else:
                self._add_warning("Пустая цель btn из '{}', кнопка '{}'".format(loc_name, label))

        # Парсим goto команды (переходы)
        for match in GOTO_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                # Проверяем на цикл
                if target == loc_name:
                    cycle_ids.add(loc_id)
                goto_links.append((loc_id, target, "goto"))
            else:
                self._add_warning("Пустая цель goto из '{}'".format(loc_name))

        # Парсим proc команды (процедуры)
        for match in PROC_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                # Проверяем на цикл
                if target == loc_name:
                    cycle_ids.add(loc_id)
                proc_links.append((loc_id, target, "proc"))
            else:
                self._add_warning("Пустая цель proc из '{}'".format(loc_name))


    def _generate_plantuml(self, locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids, output_file):
        """Генерирует содержимое PlantUML файла"""
        # Создаем reverse lookup для оптимизации
        id_to_name = {loc_id: name for name, (_, loc_id) in locs.items()}
        name_to_id = {name: loc_id for name, (_, loc_id) in locs.items()}
        
        # Находим исходящие локации для определения конечных
        source_ids = set()
        for s, _, _ in btn_links + auto_links + goto_links + proc_links:
            source_ids.add(s)
        
        # Строим PlantUML эффективно
        parts = ["@startuml\n", PHANTOM_NODE, SKIN_PARAMS]
        
        # Генерируем основные локации
        for name, (desc, loc_id) in sorted(locs.items(), key=lambda x: int(x[1][1])):
            clean_name = self._sanitize(name, LOC_LIMIT)
            clean_desc = self._sanitize(desc, DESC_LIMIT)
            
            state_line = STATE_FORMAT.format(clean_name, loc_id)
            # Определяем цвет: цикл > конечная локация
            if loc_id in cycle_ids:
                state_line += " {}".format(CYCLE_COLOR)
            elif loc_id not in source_ids:
                state_line += " {}".format(END_COLOR)
            
            parts.extend([state_line + "\n", STATE_DESC_FORMAT.format(loc_id, clean_desc)])

        # Генерируем дубликаты локаций (красные)
        for loc_id, (name, desc, line_num, is_duplicate) in all_locs.items():
            if is_duplicate:
                clean_name = self._sanitize(name, LOC_LIMIT)
                clean_desc = self._sanitize(desc, DESC_LIMIT)
                
                state_line = DOUBLE_STATE_FORMAT.format(clean_name, loc_id, DOUBLE_COLOR)
                parts.extend([state_line + "\n", LOST_DESC_FORMAT.format(loc_id, line_num, clean_desc)])

        # Стартовая локация
        if any(loc_id == '0' for _, (_, loc_id) in locs.items()) or '0' in all_locs:
            parts.append(START_LOC)

        # Добавляем все типы связей
        parts.extend([
            self._add_btn_links(btn_links, name_to_id, all_locs, id_to_name),
            self._add_auto_links(auto_links),
            self._add_goto_links(goto_links, name_to_id, all_locs, id_to_name),
            self._add_proc_links(proc_links, name_to_id, all_locs, id_to_name),
            "@enduml\n"
        ])
        
        content = ''.join(parts)
        
        # Записываем файл
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("URQ to PlantUML: Файл создан: {}".format(output_file))
        except Exception as e:
            raise Exception("Ошибка записи файла {}: {}".format(output_file, e))
        
        return content

    def _add_proc_links(self, proc_links, name_to_id, all_locs, id_to_name):
        """Добавляет связи через proc"""
        parts = []
        for source_id, target, _ in proc_links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                parts.append(PROC_FORMAT.format(source_id, target_id))
            else:
                # Создаем фантомную связь если цель не найдена
                phantom_label = self._sanitize(target, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning("Локация '{}' для proc из '{}' не найдена".format(target, loc_name))
        return ''.join(parts)

    def _generate_svg_from_puml(self, puml_file):
        """Генерирует SVG файл из PUML через локальный PlantUML"""
        return self._generate_from_puml(puml_file, 'svg', '-tsvg')

    def _generate_png_from_puml(self, puml_file):
        """Генерирует PNG файл из PUML через локальный PlantUML"""
        success = self._generate_from_puml(puml_file, 'png', '-tpng')
        if success:
            png_file = os.path.splitext(puml_file)[0] + '.png'
            # self.view.window().open_file(png_file)
            if not self._open_file_in_default_program(png_file):
                sublime.error_message("Не удалось открыть PNG файл в программе по умолчанию")
        return success

    def _generate_from_puml(self, puml_file, file_type, type_flag):
        """Универсальный метод генерации файлов через локальный PlantUML"""
        if not os.path.exists(PLANTUML_JAR_PATH):
            self._add_warning("PlantUML JAR файл не найден по пути: {}".format(PLANTUML_JAR_PATH))
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning("PUML файл не найден: {}".format(puml_file))
            return False
        
        self.view.window().status_message("{} файл генерируется...".format(file_type.upper()))
        print("URQ to PlantUML: {} файл генерируется...".format(file_type.upper()))
        
        # Команда для запуска PlantUML
        cmd = [
            'java', 
            '-Dfile.encoding=UTF-8',
            '-jar', PLANTUML_JAR_PATH,
            type_flag,
            '-charset', 'UTF-8',
            puml_file
        ]
        
        try:
            # Настройки для скрытия окна на Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(puml_file),
                universal_newlines=True,
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()
            returncode = process.returncode
        except FileNotFoundError:
            self._add_warning("Java не найдена в системе. Убедитесь, что Java установлена и добавлена в PATH")
            return False
        except Exception as e:
            self._add_warning("Ошибка выполнения команды PlantUML для {}: {}".format(file_type.upper(), e))
            return False
        
        if returncode == 0:
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            if os.path.exists(output_file):
                print("URQ to PlantUML: {} файл создан: {}".format(file_type.upper(), output_file))
                return True
            else:
                self._add_warning("{} файл не был создан, хотя PlantUML завершился успешно".format(file_type.upper()))
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning("Ошибка PlantUML при создании {}: {}".format(file_type.upper(), error_msg))
            return False

    def _generate_png_online(self, puml_content, puml_file):
        """Генерирует PNG через онлайн сервис PlantUML"""
        return self._generate_online(puml_content, puml_file, 'png', lambda gen, content: gen.generate_png(content), True)

    def _generate_svg_online(self, puml_content, puml_file):
        """Генерирует SVG через онлайн сервис PlantUML"""
        return self._generate_online(puml_content, puml_file, 'svg', lambda gen, content: gen.generate_svg(content), False)

    def _generate_online(self, puml_content, puml_file, file_type, generate_func, open_file):
        """Универсальный метод для онлайн генерации"""
        try:
            self.view.window().status_message("{} файл генерируется онлайн...".format(file_type.upper()))
            print("URQ to PlantUML: {} файл генерируется онлайн...".format(file_type.upper()))
            
            generator = PlantumlGenerator()
            data = generate_func(generator, puml_content)
            
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            with open(output_file, 'wb') as f:
                f.write(data)
            
            print("URQ to PlantUML: {} файл создан онлайн: {}".format(file_type.upper(), output_file))
            if open_file:
                # self.view.window().open_file(output_file)
                self._open_file_in_default_program(output_file)
            return True
            
        except Exception as e:
            self._add_warning("Ошибка создания {} онлайн: {}".format(file_type.upper(), e))
            return False

    def _add_btn_links(self, links, name_to_id, all_locs, id_to_name):
        """Добавляет связи через кнопки"""
        parts = []
        for source_id, target, label in links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                clean_label = self._sanitize(label, BTN_LIMIT)
                parts.append(BTN_FORMAT.format(source_id, target_id, clean_label))
            else:
                # Создаем фантомную связь если цель не найдена
                phantom_label = self._sanitize(label, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning("Локация '{}' для btn из '{}' не найдена".format(target, loc_name))
        return ''.join(parts)

    def _add_auto_links(self, auto_links):
        """Добавляет автоматические связи"""
        parts = []
        for source_id, target_id, _ in auto_links:
            # target_id уже является ID, не нужно резолвить
            parts.append(AUTO_FORMAT.format(source_id, target_id))
        return ''.join(parts)

    def _add_goto_links(self, goto_links, name_to_id, all_locs, id_to_name):
        """Добавляет связи через goto"""
        parts = []
        for source_id, target, _ in goto_links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                parts.append(GOTO_FORMAT.format(source_id, target_id, "goto"))
            else:
                # Создаем фантомную связь если цель не найдена
                phantom_label = self._sanitize(target, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning("Локация '{}' для goto из '{}' не найдена".format(target, loc_name))
        return ''.join(parts)

    def _resolve_target(self, target_name, name_to_id, all_locs):
        """Находит ID целевой локации по имени (приоритет основным локациям)"""
        # Сначала ищем в основных локациях
        if target_name in name_to_id:
            return name_to_id[target_name]
        
        # Потом среди дубликатов
        for loc_id, (name, _, _, is_duplicate) in all_locs.items():
            if name == target_name and is_duplicate:
                return loc_id
        
        return None

    def _open_file_in_default_program(self, file_path):
        """Открывает файл в программе по умолчанию"""
        try:
            if sys.platform.startswith('win'):
                # Windows
                os.startfile(file_path)
            elif sys.platform.startswith('darwin'):
                # macOS
                subprocess.call(['open', file_path])
            else:
                # Linux
                subprocess.call(['xdg-open', file_path])
            return True
        except Exception as e:
            self._add_warning("Не удалось открыть файл {}: {}".format(file_path, e))
            return False


    def _sanitize(self, text, max_len=BTN_LIMIT):
        """Очищает текст от проблемных символов и обрезает по длине"""
        if not text:
            return ""
        # Убираем pln
        text = PLN_NEWLINE_PATTERN.sub(' ', text)

        # Обрезаем если слишком длинно
        if len(text) > max_len:
            text = text[:max_len].strip() + "..."

        # Заменяем кавычки на безопасные
        return text.replace('"', "''")

    def _add_warning(self, message):
        """Добавляет предупреждение в список"""
        full_msg = "URQ to PlantUML Warning: {}".format(message)
        self.warnings.append(full_msg)
        print(full_msg)

    def _print_warnings(self):
        """Выводит все накопленные предупреждения"""
        if self.warnings:
            print("\n" + "=" * 20 + " URQ to PlantUML Warnings " + "=" * 20)
            for warning in self.warnings:
                print(warning)
            print("=" * 61 + "\n")