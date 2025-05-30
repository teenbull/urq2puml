# PlantUML Generator - создает PlantUML диаграммы и файлы
import sublime
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
BTN_MENU_COLOR = "dotted" # для кнопок-меню
BTN_LOCAL_COLOR = "#cccccc,bold" # для локальных кнопок
DOT_COLOR = "#828282" # серый для стартовой точки
# Цвета для технических локаций
TECH_COLOR = "#7692AD"  # светло-серый фон
TECH_FONT_COLOR = "#FFFFFF"  # белый текст
ORPHAN_COLOR = "#ffcccb"  # красный фон для сироток

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
skinparam state<<tech>> {{
    BackgroundColor {TECH_COLOR}
    FontColor {TECH_FONT_COLOR}
}}
skinparam state<<orphan>> {{
    BackgroundColor {ORPHAN_COLOR}
    FontColor {FONT_COLOR}
}}
sprite $menu_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8.2 11.2">
  <path d="M0 0v11.2l3-2.9.1-.1h5.1L0 0z" fill="#3D3D3D"/>
</svg>
sprite $local_icon <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 12">
  <path d="M1.2 0 C0.4 0 0 0.4 0 1.2 L0 12 L4 9 L8 12 L8 1.2 C8 0.4 7.6 0 6.8 0 Z" fill="#CD5C5C" />
</svg>
"""

START_LOC = f"[*] {DOT_COLOR} --> 0 \n"

# Форматы связей
AUTO_FMT = "{} -[dotted]-> {}\n"

BTN_FMT = "{} --> {} : ({})\n" 

# PHANTOM_EMPTY_FMT = f"{{}} -[{BLUE_COLOR},dashed]-> PHANTOM_NODE_URQ : ({{}})\n"
PHANTOM_FMT = f"{{}} -[{PHANTOM_ARROW_COLOR},dashed]-> PHANTOM_NODE_URQ : ({{}})\n"
BTN_MENU = f"{{}} -[{BTN_MENU_COLOR}]-> {{}} : ({{}}) <$menu_icon> \n"
BTN_LOCAL = f"{{}} -[{BTN_LOCAL_COLOR}]-> {{}} : ({{}}) <$local_icon> \n"

DOUBLE_FMT = '{}: [Дубликат метки, строка {}]\\n\\n{}\n'

GOTO_FMT = "{} --> {} : [goto]\n"
PROC_FMT = "{} --> {} : [proc]\n{} -[dotted]-> {}\n"

STATE_FMT = 'state "{}" as {}'
STATE_CYCLE_FMT = f'state "{{}}" as {{}} {CYCLE_COLOR}' # For cycle states
STATE_END_FMT = f'state "{{}}" as {{}} {END_COLOR}'   # For end states
STATE_DESC_FMT = '{}: {}\n'
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

    def _group_by_prefix(self, locs):
        """Группирует локации по префиксам рекурсивно (до _ или пробела)"""
        def build_tree(locs_list, depth=0):
            if depth > 3 or len(locs_list) < 2:  # Лимит глубины и минимум локаций
                return locs_list, {}
            
            groups = {}
            ungrouped = []
            
            for loc in locs_list:
                # Проверяем что это объект локации, не строка
                if not hasattr(loc, 'id') or not hasattr(loc, 'name'):
                    print(f"DEBUG: Invalid loc object: {type(loc)} = {loc}")
                    ungrouped.append(loc)
                    continue
                    
                if hasattr(loc, 'dup') and loc.dup:
                    ungrouped.append(loc)
                    continue
                    
                name_parts = loc.name.lower().replace(' ', '_').split('_')
                if len(name_parts) > depth + 1:
                    prefix = name_parts[depth]
                    if len(prefix) > 1:  # Минимум 2 символа
                        if prefix not in groups:
                            groups[prefix] = []
                        groups[prefix].append(loc)
                    else:
                        ungrouped.append(loc)
                else:
                    ungrouped.append(loc)
            
            # Рекурсивно группируем подгруппы
            final_groups = {}
            for prefix, group_locs in groups.items():
                if len(group_locs) >= 2:
                    sub_ungrouped, sub_groups = build_tree(group_locs, depth + 1)
                    final_groups[prefix] = (sub_ungrouped, sub_groups)
                else:
                    ungrouped.extend(group_locs)
            
            return ungrouped, final_groups
        
        # Фильтруем только валидные объекты локаций
        valid_locs = [loc for loc in locs if hasattr(loc, 'id') and hasattr(loc, 'name')]
        if len(valid_locs) != len(locs):
            print(f"DEBUG: Filtered {len(locs) - len(valid_locs)} invalid locations")
        return build_tree(valid_locs)

    def _render_location(self, loc, indent=""):
        """Рендерит одну локацию"""
        # Проверяем валидность объекта
        if not hasattr(loc, 'id') or not hasattr(loc, 'name'):
            print(f"DEBUG: Invalid loc in render: {type(loc)} = {loc}")
            return []
            
        clean_name = self._limit_text(loc.name, LOC_LIMIT)
        clean_desc = self._limit_text(getattr(loc, 'desc', ''), DESC_LIMIT)
        
        state_line_fmt = STATE_FMT
        stereotype = ""
        
        if hasattr(loc, 'tech') and loc.tech:
            stereotype = "<<tech>>"
        elif hasattr(loc, 'orphan') and loc.orphan:
            stereotype = "<<orphan>>"
        elif hasattr(loc, 'cycle') and loc.cycle:
            state_line_fmt = STATE_CYCLE_FMT
        elif hasattr(loc, 'end') and loc.end:
            state_line_fmt = STATE_END_FMT

        if stereotype:
            state_line = f'{indent}{STATE_FMT.format(clean_name, loc.id)} {stereotype}'
        else:
            state_line = f'{indent}{state_line_fmt.format(clean_name, loc.id)}'
            
        return [state_line + "\n", f"{indent}{STATE_DESC_FMT.format(loc.id, clean_desc)}"]

    def _render_groups(self, groups, ungrouped, indent=""):
        """Рендерит группы рекурсивно"""
        parts = []
        
        # Обычные локации
        for loc in ungrouped:
            if not hasattr(loc, 'id') or not hasattr(loc, 'name'):
                print(f"DEBUG: Invalid loc in ungrouped: {type(loc)} = {loc}")
                continue
            try:
                loc_id = int(loc.id)
            except (ValueError, AttributeError):
                print(f"DEBUG: Invalid loc.id: {loc.id}")
                continue
            if not (hasattr(loc, 'dup') and loc.dup):
                parts.extend(self._render_location(loc, indent))
        
        # Сортируем ungrouped отдельно для безопасности
        valid_ungrouped = [loc for loc in ungrouped 
                          if hasattr(loc, 'id') and hasattr(loc, 'name') 
                          and not (hasattr(loc, 'dup') and loc.dup)]
        try:
            sorted_ungrouped = sorted(valid_ungrouped, key=lambda x: int(x.id))
            parts = []
            for loc in sorted_ungrouped:
                parts.extend(self._render_location(loc, indent))
        except Exception as e:
            print(f"DEBUG: Sort error: {e}")
            # Fallback без сортировки
            parts = []
            for loc in valid_ungrouped:
                parts.extend(self._render_location(loc, indent))
        
        # Группы
        for prefix, (sub_ungrouped, sub_groups) in sorted(groups.items()):
            group_name = prefix.capitalize()
            parts.append(f"{indent}state {group_name} {{\n")
            parts.extend(self._render_groups(sub_groups, sub_ungrouped, indent + "    "))
            parts.append(f"{indent}}}\n")
        
        return parts

    def generate_puml(self, locs, output_file):
        """Генерирует PUML файл с группировкой по префиксам"""
        has_phantom = any(any(len(link) > 4 and link[4] for link in loc.links) for loc in locs)
        content_parts = []
        
        # Группируем локации
        ungrouped, groups = self._group_by_prefix(locs)
        
        # Рендерим все группы и локации
        content_parts.extend(self._render_groups(groups, ungrouped))

        # Дубликаты
        for loc in locs:
            if loc.dup:
                clean_name = self._limit_text(loc.name, LOC_LIMIT)
                clean_desc = self._limit_text(loc.desc, DESC_LIMIT)
                
                state_line = f'state "{clean_name}" as {loc.id} {DOUBLE_COLOR}'
                content_parts.extend([state_line + "\n", DOUBLE_FMT.format(loc.id, loc.line, clean_desc)])

        # Старт
        if any(loc.id == '0' for loc in locs):
            content_parts.append(START_LOC)

        # Связи
        content_parts.append(self._add_all_links(locs))
        
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

    def _add_all_links(self, locs):
        """Добавляет все связи (группировка не влияет на связи)"""
        parts = []
        
        for loc in locs:
            for link in loc.links:
                target_id, target_name, link_type, label, is_phantom, is_menu, is_local = link
                
                if is_phantom:
                    parts.append(self._format_phantom_link(loc.id, target_name, link_type, label))
                    self._add_warning(f"Локация '{target_name}' для {link_type} из '{loc.name}' не найдена")
                else:
                    parts.append(self._format_link(loc.id, target_id, link_type, label, is_menu, is_local))
        
        return ''.join(parts)

    def _format_link(self, source_id, target_id, link_type, label, is_menu=False, is_local=False):
        """Форматирует обычные связи, включая спец. цвета для меню и локальных кнопок"""

        if link_type == "auto":            
            return AUTO_FMT.format(source_id, target_id)
        elif link_type == "btn":
            clean_label = self._limit_text(label, BTN_LIMIT)
            if is_menu:
                return BTN_MENU.format(source_id, target_id, clean_label)
            elif is_local:
                return BTN_LOCAL.format(source_id, target_id, clean_label)
            else:
                return BTN_FMT.format(source_id, target_id, clean_label)
        elif link_type == "goto":
            return GOTO_FMT.format(source_id, target_id)
        elif link_type == "proc":
            return PROC_FMT.format(source_id, target_id, target_id, source_id)
        
        return ""

    def _format_phantom_link(self, source_id, target_name, link_type, label):
        """Форматирует phantom связь"""
        # if link_type == "btn" and label.strip() == "":
            # return PHANTOM_EMPTY_FMT.format(source_id, label)
        
        label = self._limit_text(label if link_type == "btn" and label else target_name, BTN_LIMIT)
        return PHANTOM_FMT.format(source_id, label)

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
            sublime.error_message("Java не найдена в PATH, попробуйте установить и прописать.")
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
            sublime.error_message("Ошибка при попытке онлайн генерации. Возможно, файл слишком велик - попробуйте оффлайн способ (см. readme.md).")
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