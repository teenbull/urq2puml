# PlantUML Generator - создает PlantUML диаграммы и файлы
import os
import subprocess
import string
import base64
import zlib
import urllib.request
import urllib.error
# print("Package name:", os.path.basename(os.path.dirname(__file__)))

# ----------------------------------------------------------------------
# Лимиты и константы
LOC_LIMIT = 40
DESC_LIMIT = 50
BTN_LIMIT = 30

# PlantUML стили
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

# Цвета состояний
CYCLE_COLOR = "#ffffcc"
DOUBLE_COLOR = "#ffcccb"
END_COLOR = "#d0f0d0"
START_LOC = "[*] --> 0\n"

# Форматы
AUTO_FORMAT = "{0} -[dotted]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : {1}\n"
BTN_FORMAT = "{0} --> {1} : {2}\n" 
GOTO_FORMAT = "{0} --> {1} : [{2}]\n"
STATE_FORMAT = 'state "{0}" as {1}'
DOUBLE_STATE_FORMAT = 'state "{0}" as {1} {2}'
STATE_DESC_FORMAT = '{0}: {1}\n'
LOST_DESC_FORMAT = '{0}: [Дубликат метки, строка {1}]\\n\\n{2}\n'
PROC_FORMAT = "{0} --> {1} : [proc]\n{1} -[dotted]-> {0}\n"

EMPTY_BTN_FORMAT = "{0} -[#6fb4d4]-> {1}\n"
PHANTOM_FORMAT = "{0} -[#CD5C5C,dotted]-> PHANTOM_NODE_URQ : {1}\n"
PHANTOM_EMPTY_FORMAT = "{0} -[#6fb4d4,dotted]-> PHANTOM_NODE_URQ\n"
# ----------------------------------------------------------------------

class PlantumlOnlineGen:
    """Онлайн генератор PlantUML"""
    def __init__(self, server_url="http://www.plantuml.com/plantuml/"):
        self.server_url = server_url
        self.p_alpha = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        self.b64_alpha = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
        self.b64_to_p = str.maketrans(self.b64_alpha, self.p_alpha)

    def _req(self, type, text):
        """Запрос к серверу PlantUML"""
        enc = zlib.compress(text.encode('utf-8'))[2:-4]
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
        """Генерирует PNG"""
        return self._req("img", plantuml_text)

    def generate_svg(self, plantuml_text):
        """Генерирует SVG"""
        return self._req("svg", plantuml_text)

class PlantumlGen:
    """Генератор PlantUML диаграмм"""
    def __init__(self, jar_path=None):
        self.jar_path = jar_path
        self.warnings = []

    def generate_puml(self, locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids, output_file):
        """Генерирует PUML файл"""
        # Создаем lookup таблицы
        id_to_name = {loc_id: name for name, (_, loc_id) in locs.items()}
        name_to_id = {name: loc_id for name, (_, loc_id) in locs.items()}
        
        # Находим исходящие локации
        source_ids = set()
        for s, _, _ in btn_links + auto_links + goto_links + proc_links:
            source_ids.add(s)
        
        # Строим PlantUML
        parts = ["@startuml\n", PHANTOM_NODE, SKIN_PARAMS]
        
        # Основные локации
        for name, (desc, loc_id) in sorted(locs.items(), key=lambda x: int(x[1][1])):
            clean_name = self._limit_text(name, LOC_LIMIT)
            clean_desc = self._limit_text(desc, DESC_LIMIT)
            
            state_line = STATE_FORMAT.format(clean_name, loc_id)
            if loc_id in cycle_ids:
                state_line += " {}".format(CYCLE_COLOR)
            elif loc_id not in source_ids:
                state_line += " {}".format(END_COLOR)
            
            parts.extend([state_line + "\n", STATE_DESC_FORMAT.format(loc_id, clean_desc)])

        # Дубликаты
        for loc_id, (name, desc, line_num, is_duplicate) in all_locs.items():
            if is_duplicate:
                clean_name = self._limit_text(name, LOC_LIMIT)
                clean_desc = self._limit_text(desc, DESC_LIMIT)
                
                state_line = DOUBLE_STATE_FORMAT.format(clean_name, loc_id, DOUBLE_COLOR)
                parts.extend([state_line + "\n", LOST_DESC_FORMAT.format(loc_id, line_num, clean_desc)])

        # Стартовая локация
        if any(loc_id == '0' for _, (_, loc_id) in locs.items()) or '0' in all_locs:
            parts.append(START_LOC)

        # Связи
        parts.extend([
            self._add_links(btn_links, name_to_id, all_locs, id_to_name, BTN_FORMAT, "btn"),
            self._add_auto_links(auto_links),
            self._add_links(goto_links, name_to_id, all_locs, id_to_name, GOTO_FORMAT, "goto"),
            self._add_proc_links(proc_links, name_to_id, all_locs, id_to_name),
            "@enduml\n"
        ])
        
        content = ''.join(parts)
        
        # Записываем файл
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("PlantUML Gen: Файл создан: {}".format(output_file))
        except Exception as e:
            raise Exception("Ошибка записи файла {}: {}".format(output_file, e))
        
        return content

    def generate_local(self, puml_file, file_type):
        """Генерирует файл через локальный PlantUML"""
        if not self.jar_path or not os.path.exists(self.jar_path):
            self._add_warning("PlantUML JAR не найден: {}".format(self.jar_path))
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning("PUML файл не найден: {}".format(puml_file))
            return False
        
        type_flags = {'png': '-tpng', 'svg': '-tsvg'}
        if file_type not in type_flags:
            self._add_warning("Неподдерживаемый тип файла: {}".format(file_type))
            return False
        
        print("PlantUML Gen: {} файл генерируется...".format(file_type.upper()))
        
        cmd = [
            'java', 
            '-Dfile.encoding=UTF-8',
            '-jar', self.jar_path,
            type_flags[file_type],
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
            self._add_warning("Java не найдена в PATH")
            return False
        except Exception as e:
            self._add_warning("Ошибка PlantUML для {}: {}".format(file_type.upper(), e))
            return False
        
        if returncode == 0:
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            if os.path.exists(output_file):
                print("PlantUML Gen: {} создан: {}".format(file_type.upper(), output_file))
                return True
            else:
                self._add_warning("{} файл не создан".format(file_type.upper()))
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning("PlantUML ошибка {}: {}".format(file_type.upper(), error_msg))
            return False

    def generate_online(self, puml_content, puml_file, file_type):
        """Генерирует файл через онлайн сервис"""
        try:
            print("PlantUML Gen: {} генерируется онлайн...".format(file_type.upper()))
            
            generator = PlantumlOnlineGen()
            if file_type == 'png':
                data = generator.generate_png(puml_content)
            elif file_type == 'svg':
                data = generator.generate_svg(puml_content)
            else:
                self._add_warning("Неподдерживаемый онлайн тип: {}".format(file_type))
                return False
            
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            with open(output_file, 'wb') as f:
                f.write(data)
            
            print("PlantUML Gen: {} создан онлайн: {}".format(file_type.upper(), output_file))
            return True
            
        except Exception as e:
            self._add_warning("Онлайн ошибка {}: {}".format(file_type.upper(), e))
            return False
            
    def _add_links(self, links, name_to_id, all_locs, id_to_name, format_str, link_type):
        """Универсальный метод добавления связей"""
        parts = []
        for source_id, target, label in links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                if link_type == "btn":
                    if label == "":  # Совсем пустая - синяя стрелка без текста
                        parts.append(EMPTY_BTN_FORMAT.format(source_id, target_id))
                    else:  # Есть текст (включая пробелы) - обычная стрелка
                        clean_label = self._limit_text(label, BTN_LIMIT)
                        parts.append(format_str.format(source_id, target_id, clean_label))
                else:  # goto
                    parts.append(format_str.format(source_id, target_id, link_type))
            else:
                phantom_label = self._limit_text(label if link_type == "btn" and label else target, BTN_LIMIT)
                # Use appropriate phantom format based on label content
                if phantom_label == "":
                    parts.append(PHANTOM_EMPTY_FORMAT.format(source_id))
                else:
                    parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning("Локация '{}' для {} из '{}' не найдена".format(target, link_type, loc_name))
        return ''.join(parts)

    def _add_auto_links(self, auto_links):
        """Добавляет автосвязи"""
        parts = []
        for source_id, target_id, _ in auto_links:
            parts.append(AUTO_FORMAT.format(source_id, target_id))
        return ''.join(parts)

    def _add_proc_links(self, proc_links, name_to_id, all_locs, id_to_name):
        """Добавляет proc связи"""
        parts = []
        for source_id, target, _ in proc_links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                parts.append(PROC_FORMAT.format(source_id, target_id))
            else:
                phantom_label = self._limit_text(target, BTN_LIMIT)
                parts.append(PHANTOM_FORMAT.format(source_id, phantom_label))
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning("Локация '{}' для proc из '{}' не найдена".format(target, loc_name))
        return ''.join(parts)

    def _resolve_target(self, target_name, name_to_id, all_locs):
        """Находит ID цели"""
        # Основные локации сначала
        if target_name in name_to_id:
            return name_to_id[target_name]
        
        # Дубликаты
        for loc_id, (name, _, _, is_duplicate) in all_locs.items():
            if name == target_name and is_duplicate:
                return loc_id
        
        return None

    def _limit_text(self, text, max_len):
        """Ограничивает длину текста для диаграммы"""
        if not text:
            return ""
        
        if len(text) > max_len:
            return text[:max_len].strip() + "..."
        
        return text

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append("PlantUML Gen Warning: {}".format(message))

    def get_warnings(self):
        """Возвращает предупреждения"""
        return self.warnings