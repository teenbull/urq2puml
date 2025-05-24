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
STATE_FORMAT = 'state "{}" as {}'
DOUBLE_STATE_FORMAT = 'state "{}" as {} {}'
STATE_DESC_FORMAT = '{}: {}\n'
LOST_DESC_FORMAT = '{}: [Дубликат метки, строка {}]\\n\\n{}\n'
PROC_FORMAT = "{} --> {} : [proc]\n{} -[dotted]-> {}\n"
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

    def generate_puml(self, locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids, output_file):
        """Генерирует PUML файл"""
        # Lookup таблицы
        id_to_name = {loc_id: name for name, (_, loc_id) in locs.items()}
        name_to_id = {name: loc_id for name, (_, loc_id) in locs.items()}
        
        # Исходящие локации
        source_ids = {s for s, _, _ in btn_links + auto_links + goto_links + proc_links}
        
        self.has_phantom_links = False
        content_parts = []
        
        # Основные локации
        for name, (desc, loc_id) in sorted(locs.items(), key=lambda x: int(x[1][1])):
            clean_name = self._limit_text(name, LOC_LIMIT)
            clean_desc = self._limit_text(desc, DESC_LIMIT)
            
            state_line = STATE_FORMAT.format(clean_name, loc_id)
            if loc_id in cycle_ids:
                state_line += f" {CYCLE_COLOR}"
            elif loc_id not in source_ids:
                state_line += f" {END_COLOR}"
            
            content_parts.extend([state_line + "\n", STATE_DESC_FORMAT.format(loc_id, clean_desc)])

        # Дубликаты
        for loc_id, (name, desc, line_num, is_duplicate) in all_locs.items():
            if is_duplicate:
                clean_name = self._limit_text(name, LOC_LIMIT)
                clean_desc = self._limit_text(desc, DESC_LIMIT)
                
                state_line = DOUBLE_STATE_FORMAT.format(clean_name, loc_id, DOUBLE_COLOR)
                content_parts.extend([state_line + "\n", LOST_DESC_FORMAT.format(loc_id, line_num, clean_desc)])

        # Старт
        if any(loc_id == '0' for _, (_, loc_id) in locs.items()) or '0' in all_locs:
            content_parts.append(START_LOC)

        # Связи
        content_parts.extend([
            self._add_links(btn_links, name_to_id, all_locs, id_to_name, BTN_FORMAT, "btn"),
            self._add_auto_links(auto_links),
            self._add_links(goto_links, name_to_id, all_locs, id_to_name, GOTO_FORMAT, "goto"),
            self._add_proc_links(proc_links, name_to_id, all_locs, id_to_name)
        ])
        
        # Финальная сборка
        final_parts = ["@startuml\n"]
        if self.has_phantom_links:
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
            
    def _add_links(self, links, name_to_id, all_locs, id_to_name, fmt, link_type):
        """Универсальный метод добавления связей"""
        parts = []
        for link_data in links:
            # Защита от неполных данных
            if len(link_data) < 3:
                continue
            source_id, target, label = link_data
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                if link_type == "btn":
                    if label == "":  # Пустая - синяя стрелка
                        parts.append(f"{source_id} -[{BLUE_COLOR}]-> {target_id}\n")
                    else:  # С текстом - обычная
                        clean_label = self._limit_text(label, BTN_LIMIT)
                        parts.append(fmt.format(source_id, target_id, clean_label))
                else:  # goto
                    parts.append(fmt.format(source_id, target_id, "goto"))
            else:
                self.has_phantom_links = True
                phantom_label = self._limit_text(label if link_type == "btn" and label else target, BTN_LIMIT)
                if phantom_label == "":
                    parts.append(f"{source_id} -[{BLUE_COLOR},dotted]-> PHANTOM_NODE_URQ\n")
                else:
                    parts.append(f"{source_id} -[{PHANTOM_ARROW_COLOR},dotted]-> PHANTOM_NODE_URQ : ({phantom_label})\n")
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning(f"Локация '{target}' для {link_type} из '{loc_name}' не найдена")
        return ''.join(parts)

    def _add_auto_links(self, auto_links):
        """Добавляет автосвязи"""
        return ''.join(AUTO_FORMAT.format(source_id, target_id) for source_id, target_id, _ in auto_links)

    def _add_proc_links(self, proc_links, name_to_id, all_locs, id_to_name):
        """Добавляет proc связи"""
        parts = []
        for source_id, target, _ in proc_links:
            target_id = self._resolve_target(target, name_to_id, all_locs)
            
            if target_id is not None:
                # Fixed: Now providing 4 arguments to match PROC_FORMAT (source->target, target->source dotted)
                parts.append(PROC_FORMAT.format(source_id, target_id, target_id, source_id))
            else:
                self.has_phantom_links = True
                phantom_label = self._limit_text(target, BTN_LIMIT)
                parts.append(f"{source_id} -[{PHANTOM_ARROW_COLOR},dotted]-> PHANTOM_NODE_URQ : ({phantom_label})\n")
                loc_name = id_to_name.get(source_id, "неизвестная")
                self._add_warning(f"Локация '{target}' для proc из '{loc_name}' не найдена")
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
        if not text or len(text) <= max_len:
            return text or ""
        return text[:max_len].strip() + "..."

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"PlantUML Gen Warning: {message}")

    def get_warnings(self):
        """Возвращает предупреждения"""
        return self.warnings