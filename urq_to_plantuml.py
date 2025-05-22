PLANTUML_JAR_PATH = "C:\\java\\plantuml-1.2025.2.jar"

import sublime
import sublime_plugin
import os
import re
import subprocess

# Константы стилей PlantUML
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

END_COLOR = "#d0f0d0"
LOST_COLOR = "" # Серый цвет для потерянных локаций
START_LOC = "[*] --> 0\n"

# Шаблоны форматирования
AUTO_FORMAT = "{0} -[#CD5C5C,dotted]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : [{1}]\n"
BTN_FORMAT = "{0} --> {1} : {2}\n"
GOTO_FORMAT = "{0} --> {1} : [{2}]\n"
STATE_FORMAT = 'state "{0}" as {1}'
LOST_STATE_FORMAT = 'state "{0}" as {1} {2}'  # Потерянные локации с dotted border
STATE_DESC_FORMAT = '{0}: {1}\n'
LOST_DESC_FORMAT = '{0}: Дубликат локации, строчка {1}. {2}\n'  # Новый шаблон для потерянных локаций

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        current_file = self.view.file_name()

        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Файл должен быть URQ (.qst)")
            return

        self.view.window().status_message("Конвертация URQ в PlantUML...")
        self.warnings = []

        try:
            locations, lost_locations, transitions, auto_trans, goto_trans = self._parse_urq_file(current_file)
            
            if not locations:
                return

            puml_file = os.path.splitext(current_file)[0] + '.puml'
            self._generate_plantuml(locations, lost_locations, transitions, auto_trans, goto_trans, puml_file)
            
            # Проверяем, что PUML файл создан перед продолжением
            if os.path.exists(puml_file):
                self.view.window().open_file(puml_file)
                
                # Генерация PNG файла
                png_success = self._generate_png_from_puml(puml_file)
                
                if png_success:
                    self.view.window().status_message("Конвертация URQ в PlantUML: .puml и .png файлы сгенерированы.")
                else:
                    self.view.window().status_message("Конвертация URQ в PlantUML: .puml файл сгенерирован. PNG не создан (см. предупреждения).")
            else:
                # Это может произойти, если _generate_plantuml вернул пустой код или была ошибка записи без исключения
                msg = "URQ to PlantUML Error: Файл .puml не был создан."
                self.warnings.append(msg)
                print(msg)

        except Exception as e:
            self._add_warning("Critical Error: Произошла ошибка при конвертации: {}".format(e))
        finally:
            self._print_warnings()

    def _parse_urq_file(self, file_path):
        # Парсит URQ файл, возвращает локации, потерянные локации и переходы.
        content = self._read_file(file_path)
        if not content:
            return {}, {}, [], [], []

        # Разбиваем содержимое на строки для подсчета номеров строк
        lines = content.split('\n')

        # Поиск меток локаций
        loc_pattern = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
        matches = list(loc_pattern.finditer(content))
        
        if not matches:
            self._add_warning("В файле {} не найдено ни одной метки локации".format(os.path.basename(file_path)))
            return {}, {}, [], [], []

        locations = {}  # имя -> (описание, номер)
        lost_locations = {}  # потерянные дубли локаций -> (описание, номер_строки, оригинальное_имя)
        transitions = []  # (источник, цель, метка, тип)
        location_counter = 0  # общий счетчик для всех локаций
        
        # Обработка каждой локации
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            # Вычисляем номер строки локации
            line_number = content[:match.start()].count('\n') + 1
            
            # Извлечение содержимого и описания
            loc_content = content[start_pos:end_pos].lstrip()
            desc = self._extract_description(loc_content)
            
            if name not in locations:
                # Первое вхождение - обычная локация
                locations[name] = [desc, str(location_counter)]
                location_counter += 1
                
                # Извлечение переходов только для первой локации
                self._extract_transitions(name, loc_content, transitions, matches, i)
            else:
                # Дубликат - потерянная локация с обычным порядковым номером
                lost_key = str(location_counter)
                lost_locations[lost_key] = [desc, line_number, name]  # сохраняем описание, номер строки и оригинальное имя
                location_counter += 1
                self._add_warning("Найдена потерянная локация (дубликат): '{}' на строке {}".format(name, line_number))

        # Разделение переходов по типам
        btn_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "btn"]
        auto_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "auto"]
        goto_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "goto"]
        
        return locations, lost_locations, btn_trans, auto_trans, goto_trans

    def _read_file(self, file_path):
        # Read file content with encoding fallback.
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='cp1251') as f:
                    return f.read()
            except UnicodeDecodeError:
                self._add_warning("Не удалось определить кодировку файла {}".format(os.path.basename(file_path)))
                return None

    def _extract_description(self, content):
        # Извлекаем текст (описание локации) из pln 
        pln_match = re.search(r'pln\s+([^.\n]+)', content)
        return pln_match.group(1).strip() if pln_match else "Нет описания"

    def _extract_transitions(self, loc_name, content, transitions, all_matches, current_index):
        """Извлекает все переходы из содержимого локации."""
        has_end = re.search(r'^\s*\bend\b', content, re.MULTILINE | re.IGNORECASE)
        has_goto = re.search(r'^\s*\bgoto\b', content, re.MULTILINE | re.IGNORECASE)
        
        # Автопереход (если нет end/goto и не последняя локация)
        if not has_end and not has_goto and current_index + 1 < len(all_matches):
            next_name = all_matches[current_index + 1].group(1).strip()
            transitions.append((loc_name, next_name, "auto", "auto"))

        # Переходы по кнопкам
        for match in re.finditer(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', content, re.MULTILINE | re.IGNORECASE):
            target, label = match.group(1).strip(), match.group(2).strip()
            if target:
                transitions.append((loc_name, target, label, "btn"))
            else:
                self._add_warning("Пустая цель btn из '{}', кнопка '{}'".format(loc_name, label))

        # Переходы goto
        for match in re.finditer(r'^\s*\bgoto\s+(.+)', content, re.MULTILINE | re.IGNORECASE):
            target = match.group(1).strip()
            if target:
                transitions.append((loc_name, target, "goto", "goto"))
            else:
                self._add_warning("Пустая цель goto из '{}'".format(loc_name))

    def _generate_plantuml(self, locations, lost_locations, btn_trans, auto_trans, goto_trans, output_file):
        # Генерирует код PlantUML.
        code = "@startuml\n"
        code += PHANTOM_NODE
        code += SKIN_PARAMS
        
        # Определение конечных локаций (без исходящих переходов)
        source_locs = set()
        for s, _, _ in btn_trans + auto_trans + goto_trans:
            source_locs.add(s)
        end_locs = set(name for name in locations if name not in source_locs)
        
        # Генерация определений обычных локаций
        sorted_locs = sorted(locations.items(), key=lambda x: int(x[1][1]))
        
        for name, (desc, num) in sorted_locs:
            clean_name = self._sanitize(name, 40)
            clean_desc = self._sanitize(desc, 50)
            
            state_line = STATE_FORMAT.format(clean_name, num)
            if name in end_locs:
                state_line += " {}".format(END_COLOR)
            
            code += state_line + "\n"
            code += STATE_DESC_FORMAT.format(num, clean_desc)

        # Генерация потерянных локаций (в конце)
        if lost_locations:
            for lost_key, (desc, line_number, original_name) in lost_locations.items():
                clean_name = self._sanitize(original_name, 40)
                clean_desc = self._sanitize(desc, 50)
                
                state_line = LOST_STATE_FORMAT.format(clean_name, lost_key, LOST_COLOR)
                code += state_line + "\n"
                code += LOST_DESC_FORMAT.format(lost_key, line_number, clean_desc)

        # Добавление стартовой локации
        if any(num == '0' for _, (_, num) in locations.items()) or '0' in lost_locations:
            code += START_LOC

        # Добавление переходов
        code += self._add_btn_transitions(btn_trans, locations)
        code += self._add_auto_transitions(auto_trans, locations)
        code += self._add_goto_transitions(goto_trans, locations)
        
        code += "@enduml\n"
        
        # Write file
        try:
            # Сохраняем в UTF-8 с BOM для лучшей совместимости с PlantUML
            with open(output_file, 'w', encoding='utf-8-sig') as f:
                f.write(code)
            print("URQ to PlantUML: Файл создан: {}".format(output_file))
        except Exception as e:
            raise Exception("Ошибка записи файла {}: {}".format(output_file, e))

    def _generate_png_from_puml(self, puml_file):
        """
        Генерирует PNG файл из PUML файла используя PlantUML.
        Возвращает True если успешно, False если произошла ошибка.
        """
        try:
            # Проверяем существование JAR файла
            if not os.path.exists(PLANTUML_JAR_PATH):
                self._add_warning("PlantUML JAR файл не найден по пути: {}".format(PLANTUML_JAR_PATH))
                return False
            
            # Проверяем существование PUML файла
            if not os.path.exists(puml_file):
                self._add_warning("PUML файл не найден: {}".format(puml_file))
                return False
            
            # Показываем индикатор прогресса
            self.view.window().status_message("PNG файл генерируется...")
            print("URQ to PlantUML: PNG файл генерируется...")
            
            # Команда для генерации PNG
            cmd = [
                'java', 
                '-Dfile.encoding=UTF-8',  # Устанавливаем кодировку для Java
                '-jar', PLANTUML_JAR_PATH,
                '-tpng',  # генерация PNG
                '-charset', 'UTF-8',  # кодировка для PlantUML
                puml_file
            ]
            
            # Выполняем команду
            try:
                # Используем Popen для совместимости со старыми версиями Python
                # CREATE_NO_WINDOW скрывает окно консоли на Windows
                startupinfo = None
                if os.name == 'nt':  # Windows
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
            except Exception as e:
                self._add_warning("Ошибка выполнения команды PlantUML: {}".format(e))
                return False
            
            if returncode == 0:
                png_file = os.path.splitext(puml_file)[0] + '.png'
                if os.path.exists(png_file):
                    print("URQ to PlantUML: PNG файл создан: {}".format(png_file))
                    # Открываем PNG файл в Sublime Text
                    self.view.window().open_file(png_file)
                    return True
                else:
                    self._add_warning("PNG файл не был создан, хотя PlantUML завершился успешно")
                    return False
            else:
                error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
                self._add_warning("Ошибка PlantUML при создании PNG: {}".format(error_msg))
                return False
                
        except FileNotFoundError:
            self._add_warning("Java не найдена в системе. Убедитесь, что Java установлена и добавлена в PATH")
            return False
        except Exception as e:
            self._add_warning("Ошибка при создании PNG файла: {}".format(e))
            return False

    def _add_btn_transitions(self, transitions, locations):
        """Add button transitions to PlantUML code."""
        code = ""
        for source, target, label in transitions:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num is None:
                self._add_warning("Локация '{}' для btn не найдена".format(source))
                continue
                
            if target_num is not None:
                clean_label = self._sanitize(label, 30)
                code += BTN_FORMAT.format(source_num, target_num, clean_label)
            else:
                # Фантомные переходы
                phantom_label = self._sanitize(label, 30)
                code += PHANTOM_FORMAT.format(source_num, phantom_label)
                self._add_warning("Локация '{}' для btn из '{}' не найдена".format(target, source))
        return code

    def _add_auto_transitions(self, auto_trans, locations):
        # Добавление авто-переходов
        code = ""
        for source, target, _ in auto_trans:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num and target_num:
                code += AUTO_FORMAT.format(source_num, target_num)
            else:
                missing = source if source_num is None else target
                self._add_warning("Локация '{}' для авто-перехода не найдена".format(missing))
        return code

    def _add_goto_transitions(self, goto_trans, locations):
        # Добавление goto-переходов
        code = ""
        for source, target, _ in goto_trans:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num is None:
                self._add_warning("Локация '{}' для goto не найдена".format(source))
                continue
                
            if target_num is not None:
                code += GOTO_FORMAT.format(source_num, target_num, "goto")
            else:
                # Фантомные переходы
                phantom_label = self._sanitize(target, 30)
                code += PHANTOM_FORMAT.format(source_num, phantom_label)
                self._add_warning("Локация '{}' для goto из '{}' не найдена".format(target, source))
        return code

    def _get_location_num(self, name, locations):
        # Получить номер локации из имени
        return locations.get(name, [None, None])[1]

    def _sanitize(self, text, max_len=30):
        # Делаем строки, которые скушает PlantUML
        if not text:
            return ""
        
        if len(text) > max_len:
            text = text[:max_len] + "..."
        
        return text.replace('"', "''")

    def _add_warning(self, message):
        # Add warning message.
        full_msg = "URQ to PlantUML Warning: {}".format(message)
        self.warnings.append(full_msg)
        print(full_msg)

    def _print_warnings(self):
        # Print all collected warnings.
        if self.warnings:
            print("\n" + "=" * 20 + " URQ to PlantUML Warnings " + "=" * 20)
            for warning in self.warnings:
                print(warning)
            print("=" * 61 + "\n")