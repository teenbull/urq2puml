# This is Sublime Text plugin, it supports Python 3.3 only (no f-strings)

PLANTUML_JAR_PATH = "C:\\java\\plantuml-1.2025.2.jar"

# Лимиты текста
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
LOST_COLOR = ""
START_LOC = "[*] --> 0\n"

# Шаблоны форматирования
AUTO_FORMAT = "{0} -[#CD5C5C,dotted]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : [{1}]\n"
BTN_FORMAT = "{0} --> {1} : {2}\n"
GOTO_FORMAT = "{0} --> {1} : [{2}]\n"
STATE_FORMAT = 'state "{0}" as {1}'
LOST_STATE_FORMAT = 'state "{0}" as {1} {2}'
STATE_DESC_FORMAT = '{0}: {1}\n'
LOST_DESC_FORMAT = '{0}: Дубликат локации, строчка {1}. {2}\n'

# Кэшированные регулярные выражения
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
END_PATTERN = re.compile(r'^\s*\bend\b', re.MULTILINE | re.IGNORECASE)
GOTO_PATTERN = re.compile(r'^\s*\bgoto\b', re.MULTILINE | re.IGNORECASE)
PLN_PATTERN = re.compile(r'pln\s+([^.\n]+)')
BTN_PATTERN = re.compile(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', re.MULTILINE | re.IGNORECASE)
GOTO_CMD_PATTERN = re.compile(r'^\s*\bgoto\s+(.+)', re.MULTILINE | re.IGNORECASE)

class PlantumlGenerator:
    def __init__(self, server_url="http://www.plantuml.com/plantuml/"):
        self.server_url = server_url
        self.p_alpha = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        self.b64_alpha = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
        self.b64_to_p = str.maketrans(self.b64_alpha, self.p_alpha)

    def _req(self, type, text):
        enc = zlib.compress(text.encode())[2:-4]
        enc_b64 = base64.b64encode(enc).decode().translate(self.b64_to_p)
        url = "{}{}/{}".format(self.server_url, type, enc_b64)
        h = {'User-Agent': 'Sublime URQ2PUML'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                if resp.getcode() == 200:
                    return resp.read()
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
        return self._req("img", plantuml_text)

    def generate_svg(self, plantuml_text):
        return self._req("svg", plantuml_text)

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit, png=False, svg=False, net=False):
        current_file = self.view.file_name()

        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Файл должен быть URQ (.qst)")
            return

        # Автопереключение на сетевой режим если jar не найден
        if not net and not os.path.exists(PLANTUML_JAR_PATH):
            net = True
            print("URQ to PlantUML: JAR не найден, переключение на сетевой режим")            

        self.view.window().status_message("Конвертация URQ в PlantUML...")
        self.warnings = []

        try:
            locations, lost_locations, transitions, auto_trans, goto_trans = self._parse_urq_file(current_file)
            
            if not locations:
                return

            puml_file = os.path.splitext(current_file)[0] + '.puml'
            puml_content = self._generate_plantuml(locations, lost_locations, transitions, auto_trans, goto_trans, puml_file)
            
            if os.path.exists(puml_file):
                self.view.window().open_file(puml_file)
                
                status_parts = ["Конвертация URQ в PlantUML: .puml файл сгенерирован"]
                
                if png:
                    if net:
                        png_success = self._generate_png_online(puml_content, puml_file)
                    else:
                        png_success = self._generate_png_from_puml(puml_file)
                    
                    if png_success:
                        status_parts.append(".png файл создан" + (" онлайн" if net else "") + " и открыт")
                    else:
                        status_parts.append(".png не создан (см. предупреждения)")
                
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
        content = self._read_file(file_path)
        if not content:
            return {}, {}, [], [], []

        matches = list(LOC_PATTERN.finditer(content))
        
        if not matches:
            self._add_warning("В файле {} не найдено ни одной метки локации".format(os.path.basename(file_path)))
            return {}, {}, [], [], []

        locations = {}
        lost_locations = {}
        transitions = []
        location_counter = 0
        
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            line_number = content[:match.start()].count('\n') + 1
            
            loc_content = content[start_pos:end_pos].lstrip()
            desc = self._extract_description(loc_content)
            
            if name not in locations:
                locations[name] = [desc, str(location_counter)]
                location_counter += 1
                
                self._extract_transitions(name, loc_content, transitions, matches, i)
            else:
                lost_key = str(location_counter)
                lost_locations[lost_key] = [desc, line_number, name]
                location_counter += 1
                self._add_warning("Найдена потерянная локация (дубликат): '{}' на строке {}".format(name, line_number))

        btn_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "btn"]
        auto_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "auto"]
        goto_trans = [(s, t, l) for s, t, l, typ in transitions if typ == "goto"]
        
        return locations, lost_locations, btn_trans, auto_trans, goto_trans

    def _read_file(self, file_path):
        if not os.path.exists(file_path):
            self._add_warning("Файл не найден: {}".format(file_path))
            return None
            
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
        except IOError as e:
            self._add_warning("Ошибка чтения файла {}: {}".format(os.path.basename(file_path), e))
            return None

    def _extract_description(self, content):
        pln_match = PLN_PATTERN.search(content)
        return pln_match.group(1).strip() if pln_match else "Нет описания"

    def _extract_transitions(self, loc_name, content, transitions, all_matches, current_index):
        has_end = END_PATTERN.search(content)
        has_goto = GOTO_PATTERN.search(content)
        
        if not has_end and not has_goto and current_index + 1 < len(all_matches):
            next_name = all_matches[current_index + 1].group(1).strip()
            transitions.append((loc_name, next_name, "auto", "auto"))

        for match in BTN_PATTERN.finditer(content):
            target, label = match.group(1).strip(), match.group(2).strip()
            if target:
                transitions.append((loc_name, target, label, "btn"))
            else:
                self._add_warning("Пустая цель btn из '{}', кнопка '{}'".format(loc_name, label))

        for match in GOTO_CMD_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target:
                transitions.append((loc_name, target, "goto", "goto"))
            else:
                self._add_warning("Пустая цель goto из '{}'".format(loc_name))

    def _generate_plantuml(self, locations, lost_locations, btn_trans, auto_trans, goto_trans, output_file):
        parts = ["@startuml\n", PHANTOM_NODE, SKIN_PARAMS]
        
        source_locs = set()
        for s, _, _ in btn_trans + auto_trans + goto_trans:
            source_locs.add(s)
        end_locs = set(name for name in locations if name not in source_locs)
        
        sorted_locs = sorted(locations.items(), key=lambda x: int(x[1][1]))
        
        for name, (desc, num) in sorted_locs:
            clean_name = self._sanitize(name, LOC_LIMIT)
            clean_desc = self._sanitize(desc, DESC_LIMIT)
            
            state_line = STATE_FORMAT.format(clean_name, num)
            if name in end_locs:
                state_line += " {}".format(END_COLOR)
            
            parts.append(state_line + "\n")
            parts.append(STATE_DESC_FORMAT.format(num, clean_desc))

        if lost_locations:
            for lost_key, (desc, line_number, original_name) in lost_locations.items():
                clean_name = self._sanitize(original_name, LOC_LIMIT)
                clean_desc = self._sanitize(desc, DESC_LIMIT)
                
                state_line = LOST_STATE_FORMAT.format(clean_name, lost_key, LOST_COLOR)
                parts.append(state_line + "\n")
                parts.append(LOST_DESC_FORMAT.format(lost_key, line_number, clean_desc))

        if any(num == '0' for _, (_, num) in locations.items()) or '0' in lost_locations:
            parts.append(START_LOC)

        parts.append(self._add_btn_transitions(btn_trans, locations))
        parts.append(self._add_auto_transitions(auto_trans, locations))
        parts.append(self._add_goto_transitions(goto_trans, locations))
        parts.append("@enduml\n")
        
        content = ''.join(parts)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("URQ to PlantUML: Файл создан: {}".format(output_file))
        except Exception as e:
            raise Exception("Ошибка записи файла {}: {}".format(output_file, e))
        
        return content

    def _generate_svg_from_puml(self, puml_file):
        """
        Генерирует SVG файл из PUML файла используя PlantUML.
        Возвращает True если успешно, False если произошла ошибка.
        """
        if not os.path.exists(PLANTUML_JAR_PATH):
            self._add_warning("PlantUML JAR файл не найден по пути: {}".format(PLANTUML_JAR_PATH))
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning("PUML файл не найден: {}".format(puml_file))
            return False
        
        self.view.window().status_message("SVG файл генерируется...")
        print("URQ to PlantUML: SVG файл генерируется...")
        
        cmd = [
            'java', 
            '-Dfile.encoding=UTF-8',
            '-jar', PLANTUML_JAR_PATH,
            '-tsvg',
            '-charset', 'UTF-8',
            puml_file
        ]
        
        try:
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
            self._add_warning("Ошибка выполнения команды PlantUML для SVG: {}".format(e))
            return False
        
        if returncode == 0:
            svg_file = os.path.splitext(puml_file)[0] + '.svg'
            if os.path.exists(svg_file):
                print("URQ to PlantUML: SVG файл создан: {}".format(svg_file))
                return True
            else:
                self._add_warning("SVG файл не был создан, хотя PlantUML завершился успешно")
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning("Ошибка PlantUML при создании SVG: {}".format(error_msg))
            return False

    def _generate_png_online(self, puml_content, puml_file):
        """Генерирует PNG через онлайн сервис PlantUML"""
        try:
            self.view.window().status_message("PNG файл генерируется онлайн...")
            print("URQ to PlantUML: PNG файл генерируется онлайн...")
            
            generator = PlantumlGenerator()
            png_data = generator.generate_png(puml_content)
            
            png_file = os.path.splitext(puml_file)[0] + '.png'
            with open(png_file, 'wb') as f:
                f.write(png_data)
            
            print("URQ to PlantUML: PNG файл создан онлайн: {}".format(png_file))
            self.view.window().open_file(png_file)
            return True
            
        except Exception as e:
            self._add_warning("Ошибка создания PNG онлайн: {}".format(e))
            return False

    def _generate_svg_online(self, puml_content, puml_file):
        """Генерирует SVG через онлайн сервис PlantUML"""
        try:
            self.view.window().status_message("SVG файл генерируется онлайн...")
            print("URQ to PlantUML: SVG файл генерируется онлайн...")
            
            generator = PlantumlGenerator()
            svg_data = generator.generate_svg(puml_content)
            
            svg_file = os.path.splitext(puml_file)[0] + '.svg'
            with open(svg_file, 'wb') as f:
                f.write(svg_data)
            
            print("URQ to PlantUML: SVG файл создан онлайн: {}".format(svg_file))
            return True
            
        except Exception as e:
            self._add_warning("Ошибка создания SVG онлайн: {}".format(e))
            return False

    def _generate_png_from_puml(self, puml_file):
        if not os.path.exists(PLANTUML_JAR_PATH):
            self._add_warning("PlantUML JAR файл не найден по пути: {}".format(PLANTUML_JAR_PATH))
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning("PUML файл не найден: {}".format(puml_file))
            return False
        
        self.view.window().status_message("PNG файл генерируется...")
        print("URQ to PlantUML: PNG файл генерируется...")
        
        cmd = [
            'java', 
            '-Dfile.encoding=UTF-8',
            '-jar', PLANTUML_JAR_PATH,
            '-tpng',
            '-charset', 'UTF-8',
            puml_file
        ]
        
        try:
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
            self._add_warning("Ошибка выполнения команды PlantUML: {}".format(e))
            return False
        
        if returncode == 0:
            png_file = os.path.splitext(puml_file)[0] + '.png'
            if os.path.exists(png_file):
                print("URQ to PlantUML: PNG файл создан: {}".format(png_file))
                self.view.window().open_file(png_file)
                return True
            else:
                self._add_warning("PNG файл не был создан, хотя PlantUML завершился успешно")
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning("Ошибка PlantUML при создании PNG: {}".format(error_msg))
            return False

    def _add_btn_transitions(self, transitions, locations):
        parts = []
        for source, target, label in transitions:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num is None:
                self._add_warning("Локация '{}' для btn не найдена".format(source))
                continue
                
            if target_num is not None:
                clean_label = self._sanitize(label, BTN_LIMIT)
                parts.append(BTN_FORMAT.format(source_num, target_num, clean_label))
            else:
                phantom_label = self._sanitize(label, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_num, phantom_label))
                self._add_warning("Локация '{}' для btn из '{}' не найдена".format(target, source))
        return ''.join(parts)

    def _add_auto_transitions(self, auto_trans, locations):
        parts = []
        for source, target, _ in auto_trans:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num and target_num:
                parts.append(AUTO_FORMAT.format(source_num, target_num))
            else:
                missing = source if source_num is None else target
                self._add_warning("Локация '{}' для авто-перехода не найдена".format(missing))
        return ''.join(parts)

    def _add_goto_transitions(self, goto_trans, locations):
        parts = []
        for source, target, _ in goto_trans:
            source_num = self._get_location_num(source, locations)
            target_num = self._get_location_num(target, locations)
            
            if source_num is None:
                self._add_warning("Локация '{}' для goto не найдена".format(source))
                continue
                
            if target_num is not None:
                parts.append(GOTO_FORMAT.format(source_num, target_num, "goto"))
            else:
                phantom_label = self._sanitize(target, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_num, phantom_label))
                self._add_warning("Локация '{}' для goto из '{}' не найдена".format(target, source))
        return ''.join(parts)

    def _get_location_num(self, name, locations):
        return locations.get(name, [None, None])[1]

    def _sanitize(self, text, max_len=BTN_LIMIT):
        if not text:
            return ""
        
        if len(text) > max_len:
            text = text[:max_len] + "..."
        
        return text.replace('"', "''")

    def _add_warning(self, message):
        full_msg = "URQ to PlantUML Warning: {}".format(message)
        self.warnings.append(full_msg)
        print(full_msg)

    def _print_warnings(self):
        if self.warnings:
            print("\n" + "=" * 20 + " URQ to PlantUML Warnings " + "=" * 20)
            for warning in self.warnings:
                print(warning)
            print("=" * 61 + "\n")