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
import os
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

SKIN_PARAMS = """skinparam stateArrowColor #606060
skinparam state {
    BackgroundColor #F0F8FF
    BorderColor #A9A9A9
    FontColor #303030
    ArrowFontColor #404040
}
"""

# Цвета для разных типов состояний
END_COLOR = "#d0f0d0"  # Зеленый для конецовок
LOST_COLOR = "#ffcccb"  # Красный для дубликатов и фантомов
START_LOC = "[*] --> 0\n"

# Шаблоны форматирования - чтобы не писать одно и то же
AUTO_FORMAT = "{0} -[#CD5C5C,dotted]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : [{1}]\n"
BTN_FORMAT = "{0} --> {1} : {2}\n"
GOTO_FORMAT = "{0} --> {1} : [{2}]\n"
STATE_FORMAT = 'state "{0}" as {1}'
LOST_STATE_FORMAT = 'state "{0}" as {1} {2}'
STATE_DESC_FORMAT = '{0}: {1}\n'
LOST_DESC_FORMAT = '{0}: [Дубликат метки, строка {1}]\\n\\n{2}\n'

# Кэшированные регулярки - компилируем один раз, используем много
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
END_PATTERN = re.compile(r'^\s*\bend\b', re.MULTILINE | re.IGNORECASE)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.MULTILINE | re.IGNORECASE)
PLN_PATTERN = re.compile(r'pln\s+([^.\n]+)')
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', re.MULTILINE | re.IGNORECASE)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.MULTILINE | re.IGNORECASE)

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
            locs, all_locs, links, auto_links, goto_links = self._parse_urq_file(current_file)
            
            if not locs:
                return

            # Генерируем PlantUML
            puml_file = os.path.splitext(current_file)[0] + '.puml'
            puml_content = self._generate_plantuml(locs, all_locs, links, auto_links, goto_links, puml_file)
            
            if os.path.exists(puml_file):
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

    def _parse_urq_file(self, file_path):
        """Парсит URQ файл и извлекает локации и связи"""
        content = self._read_file(file_path)
        if not content:
            return {}, {}, [], [], []

        # Ищем все метки локаций
        matches = list(LOC_PATTERN.finditer(content))
        
        if not matches:
            self._add_warning("В файле {} не найдено ни одной метки".format(os.path.basename(file_path)))
            return {}, {}, [], [], []

        locs = {}  # Основные локации {name: [desc, id]}
        all_locs = {}  # Все локации включая дубликаты {id: [name, desc, line_num, is_duplicate]}
        links = []
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
            self._extract_links(name, loc_content, links, loc_id, next_loc_id)
            loc_counter += 1

        # Разделяем типы связей для разного форматирования
        btn_links = [(s, t, l) for s, t, l, typ in links if typ == "btn"]
        auto_links = [(s, t, l) for s, t, l, typ in links if typ == "auto"]
        goto_links = [(s, t, l) for s, t, l, typ in links if typ == "goto"]
        
        return locs, all_locs, btn_links, auto_links, goto_links

    def _read_file(self, file_path):
        """Читает файл с попыткой определить кодировку"""
        if not os.path.exists(file_path):
            self._add_warning("Файл не найден: {}".format(file_path))
            return None
            
        try:
            # Сначала пробуем UTF-8
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                # Потом CP1251 (старая русская кодировка)
                with open(file_path, 'r', encoding='cp1251') as f:
                    return f.read()
            except UnicodeDecodeError:
                self._add_warning("Не удалось определить кодировку файла {}".format(os.path.basename(file_path)))
                return None
        except IOError as e:
            self._add_warning("Ошибка чтения файла {}: {}".format(os.path.basename(file_path), e))
            return None

    def _extract_description(self, content):
        """Извлекает описание локации из команды pln"""
        pln_match = PLN_PATTERN.search(content)
        return pln_match.group(1).strip() if pln_match else "Нет описания"

    def _extract_links(self, loc_name, content, links, loc_id, next_loc_id):
        """Извлекает все типы связей из локации"""
        has_end = END_PATTERN.search(content)
        has_goto = GOTO_PATTERN.search(content)
        
        # Автосвязь к следующей локации если нет end/goto
        if not has_end and not has_goto and next_loc_id is not None:
            links.append((loc_id, next_loc_id, "auto", "auto"))

        # Парсим btn команды (кнопки)
        for match in BTN_PATTERN.finditer(content):
            target, label = match.group(1).strip(), match.group(2).strip()
            if target:
                links.append((loc_id, target, label, "btn"))
            else:
                self._add_warning("Пустая цель btn из '{}', кнопка '{}'".format(loc_name, label))

        # Парсим goto команды (переходы)
        for match in GOTO_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                links.append((loc_id, target, "goto", "goto"))
            else:
                self._add_warning("Пустая цель goto из '{}'".format(loc_name))

    def _generate_plantuml(self, locs, all_locs, btn_links, auto_links, goto_links, output_file):
        """Генерирует содержимое PlantUML файла"""
        parts = ["@startuml\n", PHANTOM_NODE, SKIN_PARAMS]
        
        # Находим исходящие локации для определения конечных
        source_ids = set()
        for s, _, _ in btn_links + auto_links + goto_links:
            source_ids.add(s)
        
        # Генерируем основные локации
        for name, (desc, loc_id) in sorted(locs.items(), key=lambda x: int(x[1][1])):
            clean_name = self._sanitize(name, LOC_LIMIT)
            clean_desc = self._sanitize(desc, DESC_LIMIT)
            
            state_line = STATE_FORMAT.format(clean_name, loc_id)
            # Конечные локации подкрашиваем зеленым
            if loc_id not in source_ids:
                state_line += " {}".format(END_COLOR)
            
            parts.append(state_line + "\n")
            parts.append(STATE_DESC_FORMAT.format(loc_id, clean_desc))

        # Генерируем дубликаты локаций (красные)
        for loc_id, (name, desc, line_num, is_duplicate) in all_locs.items():
            if is_duplicate:
                clean_name = self._sanitize(name, LOC_LIMIT)
                clean_desc = self._sanitize(desc, DESC_LIMIT)
                
                state_line = LOST_STATE_FORMAT.format(clean_name, loc_id, LOST_COLOR)
                parts.append(state_line + "\n")
                parts.append(LOST_DESC_FORMAT.format(loc_id, line_num, clean_desc))

        # Стартовая локация
        if any(loc_id == '0' for _, (_, loc_id) in locs.items()) or '0' in all_locs:
            parts.append(START_LOC)

        # Добавляем все типы связей
        parts.append(self._add_btn_links(btn_links, locs, all_locs))
        parts.append(self._add_auto_links(auto_links, locs, all_locs))
        parts.append(self._add_goto_links(goto_links, locs, all_locs))
        parts.append("@enduml\n")
        
        content = ''.join(parts)
        
        # Записываем файл
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("URQ to PlantUML: Файл создан: {}".format(output_file))
        except Exception as e:
            raise Exception("Ошибка записи файла {}: {}".format(output_file, e))
        
        return content

    def _generate_svg_from_puml(self, puml_file):
        """Генерирует SVG файл из PUML через локальный PlantUML"""
        return self._generate_from_puml(puml_file, 'svg', '-tsvg')

    def _generate_png_from_puml(self, puml_file):
        """Генерирует PNG файл из PUML через локальный PlantUML"""
        success = self._generate_from_puml(puml_file, 'png', '-tpng')
        if success:
            png_file = os.path.splitext(puml_file)[0] + '.png'
            self.view.window().open_file(png_file)
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
                self.view.window().open_file(output_file)
            return True
            
        except Exception as e:
            self._add_warning("Ошибка создания {} онлайн: {}".format(file_type.upper(), e))
            return False

    def _add_btn_links(self, links, locs, all_locs):
        """Добавляет связи через кнопки"""
        parts = []
        for source_id, target, label in links:
            target_id = self._resolve_target(target, locs, all_locs)
            
            if target_id is not None:
                clean_label = self._sanitize(label, BTN_LIMIT)
                parts.append(BTN_FORMAT.format(source_id, target_id, clean_label))
            else:
                # Создаем фантомную связь если цель не найдена
                phantom_label = self._sanitize(label, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                self._add_warning("Локация '{}' для btn из '{}' не найдена".format(target, self._get_loc_name_by_id(source_id, locs, all_locs)))
        return ''.join(parts)

    def _add_auto_links(self, auto_links, locs, all_locs):
        """Добавляет автоматические связи"""
        parts = []
        for source_id, target_id, _ in auto_links:
            # target_id уже является ID, не нужно резолвить
            parts.append(AUTO_FORMAT.format(source_id, target_id))
        return ''.join(parts)

    def _add_goto_links(self, goto_links, locs, all_locs):
        """Добавляет связи через goto"""
        parts = []
        for source_id, target, _ in goto_links:
            target_id = self._resolve_target(target, locs, all_locs)
            
            if target_id is not None:
                parts.append(GOTO_FORMAT.format(source_id, target_id, "goto"))
            else:
                # Создаем фантомную связь если цель не найдена
                phantom_label = self._sanitize(target, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                self._add_warning("Локация '{}' для goto из '{}' не найдена".format(target, self._get_loc_name_by_id(source_id, locs, all_locs)))
        return ''.join(parts)

    def _resolve_target(self, target_name, locs, all_locs):
        """Находит ID целевой локации по имени (приоритет основным локациям)"""
        # Сначала ищем в основных локациях
        if target_name in locs:
            return locs[target_name][1]
        
        # Потом среди дубликатов
        for loc_id, (name, _, _, is_duplicate) in all_locs.items():
            if name == target_name and is_duplicate:
                return loc_id
        
        return None

    def _get_loc_name_by_id(self, loc_id, locs, all_locs):
        """Получает имя локации по ID (для сообщений об ошибках)"""
        # Ищем в основных локациях
        for name, (_, stored_id) in locs.items():
            if stored_id == loc_id:
                return name
        
        # Ищем среди всех локаций
        if loc_id in all_locs:
            return all_locs[loc_id][0]
        
        return "неизвестная"

    def _sanitize(self, text, max_len=BTN_LIMIT):
        """Очищает текст от проблемных символов и обрезает по длине"""
        if not text:
            return ""
        
        # Обрезаем если слишком длинно
        if len(text) > max_len:
            text = text[:max_len] + "..."
        
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