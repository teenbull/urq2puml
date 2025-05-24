# PlantUML Generator - создает PlantUML диаграммы и файлы
import os
import subprocess
import string
import base64
import zlib
import urllib.request
import urllib.error

# ----------------------------------------------------------------------
# Лимиты
LOC_LIMIT = 40
DESC_LIMIT = 50
BTN_LIMIT = 30

# Цвета
PHANTOM_COLOR = "#ffcccb"
STATE_BG_COLOR = "#F0F8FF"
BORDER_COLOR = "#A9A9A9"
FONT_COLOR = "#303030"
ARROW_COLOR = "#606060"
ARROW_FONT_COLOR = "#404040"
CYCLE_COLOR = "#ffffcc"
DOUBLE_COLOR = "#ffcccb"
END_COLOR = "#d0f0d0"
BLUE_COLOR = "#6fb4d4"
PHANTOM_ARROW_COLOR = "#CD5C5C"

# PlantUML элементы
PHANTOM_NODE = f"""state "//phantom" as PHANTOM_NODE_URQ {PHANTOM_COLOR} {{
  PHANTOM_NODE_URQ: (Ссылка на несуществующую локацию)
}}
"""

SKIN_PARAMS = f"""skinparam stateArrowColor {ARROW_COLOR}
skinparam state {{
    BackgroundColor {STATE_BG_COLOR}
    BorderColor {BORDER_COLOR}
    FontColor {FONT_COLOR}
    ArrowFontColor {ARROW_FONT_COLOR}
}}
"""

START_LOC = "[*] --> 0\n"

# Форматы связей
AUTO_FORMAT = "{} -[dotted]-> {}\n"
BTN_FORMAT = "{} --> {} : ({})\n" 
GOTO_FORMAT = "{} --> {} : [{}]\n"
PROC_FORMAT = "{} --> {} : [proc]\n{} -[dotted]-> {}\n"
STATE_FORMAT = 'state "{}" as {}'
STATE_DESC_FORMAT = '{}: {}\n'
LOST_DESC_FORMAT = '{}: [Дубликат метки, строка {}]\\n\\n{}\n'
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
        url = f"{self.server_url}{type}/{enc_b64}"
        h = {'User-Agent': 'Sublime URQ2PUML'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                if resp.getcode() == 200:
                    return resp.read()
                err_body = resp.read().decode(errors='replace') or "(empty)"
                err_msg = f"HTTP Error {resp.getcode()}: {resp.reason}. Body: {err_body}"
                print(f"Online Gen Error Details: {err_msg}")
                raise urllib.error.HTTPError(url, resp.getcode(), err_msg, resp.headers, None)
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            raise RuntimeError(f"Сервер PlantUML ({type(e).__name__}) ошибка: {e}")

    def generate_png(self, puml_text):
        """Генерирует PNG"""
        return self._req("img", puml_text)

    def generate_svg(self, puml_text):
        """Генерирует SVG"""
        return self._req("svg", puml_text)

class PlantumlGen:
    """Генератор PlantUML диаграмм"""
    def __init__(self, jar_path=None):
        self.jar_path = jar_path
        self.warnings = []

    def generate_puml(self, locs, name_to_id, output_file):
        """Генерирует PUML файл"""
        has_phantom = any(any(len(link) > 3 and link[3] for link in loc.links) for loc in locs)
        content_parts = []
        
        # Основные локации
        for loc in sorted(locs, key=lambda x: int(x.id)):
            if not loc.dup:
                clean_name = self._limit_text(loc.name, LOC_LIMIT)
                clean_desc = self._limit_text(loc.desc, DESC_LIMIT)
                
                state_line = STATE_FORMAT.format(clean_name, loc.id)
                if loc.cycle:
                    state_line += f" {CYCLE_COLOR}"
                elif loc.end:
                    state_line += f" {END_COLOR}"
                
                content_parts.extend([state_line + "\n", STATE_DESC_FORMAT.format(loc.id, clean_desc)])

        # Дубликаты
        for loc in locs:
            if loc.dup:
                clean_name = self._limit_text(loc.name, LOC_LIMIT)
                clean_desc = self._limit_text(loc.desc, DESC_LIMIT)
                
                state_line = f'state "{clean_name}" as {loc.id} {DOUBLE_COLOR}'
                content_parts.extend([state_line + "\n", LOST_DESC_FORMAT.format(loc.id, loc.line, clean_desc)])

        # Старт
        if any(loc.id == '0' for loc in locs):
            content_parts.append(START_LOC)

        # Связи
        content_parts.append(self._add_all_links(locs, name_to_id))
        
        # Финальная сборка
        final_parts = ["@startuml\n"]
        if has_phantom:
            final_parts.append(PHANTOM_NODE)
        final_parts.append(SKIN_PARAMS)
        final_parts.extend(content_parts)
        final_parts.append("@enduml\n")
        
        content = ''.join(final_parts)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"PlantUML Gen: Файл создан: {output_file}")
        except Exception as e:
            raise Exception(f"Ошибка записи файла {output_file}: {e}")
        
        return content

    def _add_all_links(self, locs, name_to_id):
        """Добавляет все связи"""
        parts = []
        
        for loc in locs:
            for link in loc.links:
                target, link_type, label = link[:3]
                is_phantom = len(link) > 3 and link[3]
                
                if is_phantom:
                    parts.append(self._format_phantom_link(loc.id, target, link_type, label))
                    self._add_warning(f"Локация '{target}' для {link_type} из '{loc.name}' не найдена")
                else:
                    if link_type == "auto":
                        parts.append(self._format_link(loc.id, target, link_type, label))
                    else:
                        target_id = self._get_target_id(target, name_to_id, locs)
                        parts.append(self._format_link(loc.id, target_id, link_type, label))
        
        return ''.join(parts)

    def _get_target_id(self, target_name, name_to_id, locs):
        """Находит ID цели"""
        # Основные локации
        if target_name in name_to_id:
            return name_to_id[target_name]
        
        # Дубликаты
        for loc in locs:
            if loc.name == target_name and loc.dup:
                return loc.id
        
        return None

    def _format_link(self, source_id, target_id, link_type, label):
        """Форматирует обычную связь"""
        if link_type == "auto":            
            return AUTO_FORMAT.format(source_id, target_id)
        elif link_type == "btn":
            if label == "":  # Пустая - синяя стрелка
                return f"{source_id} -[{BLUE_COLOR}]-> {target_id}\n"
            else:  # С текстом - обычная
                clean_label = self._limit_text(label, BTN_LIMIT)
                return BTN_FORMAT.format(source_id, target_id, clean_label)
        elif link_type == "goto":
            return GOTO_FORMAT.format(source_id, target_id, "goto")
        elif link_type == "proc":
            return PROC_FORMAT.format(source_id, target_id, target_id, source_id)
        
        return ""

    def _format_phantom_link(self, source_id, target, link_type, label):
        """Форматирует phantom связь"""
        if link_type == "btn" and label == "":
            return f"{source_id} -[{BLUE_COLOR},dotted]-> PHANTOM_NODE_URQ\n"
        
        phantom_label = self._limit_text(label if link_type == "btn" and label else target, BTN_LIMIT)
        return f"{source_id} -[{PHANTOM_ARROW_COLOR},dotted]-> PHANTOM_NODE_URQ : ({phantom_label})\n"

    def generate_local(self, puml_file, file_type):
        """Генерирует файл через локальный PlantUML"""
        if not self.jar_path or not os.path.exists(self.jar_path):
            self._add_warning(f"PlantUML JAR не найден: {self.jar_path}")
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning(f"PUML файл не найден: {puml_file}")
            return False
        
        type_flags = {'png': '-tpng', 'svg': '-tsvg'}
        if file_type not in type_flags:
            self._add_warning(f"Неподдерживаемый тип файла: {file_type}")
            return False
        
        print(f"PlantUML Gen: {file_type.upper()} файл генерируется...")
        
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
            self._add_warning(f"Ошибка PlantUML для {file_type.upper()}: {e}")
            return False
        
        if returncode == 0:
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            if os.path.exists(output_file):
                print(f"PlantUML Gen: {file_type.upper()} создан: {output_file}")
                return True
            else:
                self._add_warning(f"{file_type.upper()} файл не создан")
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning(f"PlantUML ошибка {file_type.upper()}: {error_msg}")
            return False

    def generate_online(self, puml_content, puml_file, file_type):
        """Генерирует файл через онлайн сервис"""
        try:
            print(f"PlantUML Gen: {file_type.upper()} генерируется онлайн...")
            
            gen = PlantumlOnlineGen()
            data = gen.generate_png(puml_content) if file_type == 'png' else gen.generate_svg(puml_content)
            
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            with open(output_file, 'wb') as f:
                f.write(data)
           
            print(f"PlantUML Gen: {file_type.upper()} создан онлайн: {output_file}")
            return True
            
        except Exception as e:
            self._add_warning(f"Онлайн ошибка {file_type.upper()}: {e}")
            return False

    def _limit_text(self, text, max_len):
        """Ограничивает длину текста для диаграммы"""
        if not text or len(text) <= max_len:
            return text or ""
        return text[:max_len].strip() + "..."

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"PlantUML Gen Warning: {message}")

    def get_warnings(self):
        """Возвращает предупреждения"""
        return self.warnings